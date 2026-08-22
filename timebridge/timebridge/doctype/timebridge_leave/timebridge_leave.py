# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Recorded leave, and whether it is inside the employee's quota.

Attendance reads this so a day off stops being counted as absence. The quota
decision is made here, once, at save time rather than every time a report runs
— so a leave that was paid when it was approved stays paid, even if the quota
is changed later.
"""

import frappe

from frappe.model.document import Document
from frappe.utils import cint, date_diff, flt, getdate

# Quotas live on TimeBridge Leave Type now, one per kind of leave. The single
# company-wide number that used to sit in TimeBridge Settings is gone: it made
# every type share one allowance, so a casual day could eat a sick day.


class TimeBridgeLeave(Document):

	def validate(self):
		self.set_dates()
		self.set_total_days()
		self.check_overlap()
		self.set_paid_from_quota()

	def set_dates(self):

		if not self.to_date:
			self.to_date = self.from_date

		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw("To Date cannot be earlier than From Date.")

		if self.half_day and getdate(self.to_date) != getdate(self.from_date):
			frappe.throw("Half Day can only be set on a single-day leave.")

	def set_total_days(self):

		days = date_diff(self.to_date, self.from_date) + 1

		self.total_days = 0.5 if self.half_day else days

	def check_overlap(self):
		"""
		Two approved leaves covering the same day would be counted twice
		against the quota, and would fight over the same attendance row.
		"""

		clash = frappe.db.sql(
			"""
			SELECT name FROM `tabTimeBridge Leave`
			WHERE employee = %(employee)s
			  AND name != %(name)s
			  AND approval_status != 'Rejected'
			  AND from_date <= %(to_date)s
			  AND to_date >= %(from_date)s
			LIMIT 1
			""",
			{
				"employee": self.employee,
				"name": self.name or "",
				"from_date": self.from_date,
				"to_date": self.to_date,
			},
		)

		if clash:
			frappe.throw(
				f"This overlaps an existing leave for {self.employee_name or self.employee}: {clash[0][0]}"
			)

	def set_paid_from_quota(self):
		"""
		Paid while the employee is still inside this type's own quota.

		The arithmetic lives in leave_balance() so the panel on the form and
		the decision made here cannot disagree — a form that promises PAID and
		then saves UNPAID is worse than no panel at all.

		A manual tick is respected on an already-saved record, so an exception
		granted by hand is not undone on the next save.
		"""

		if not self.is_new() and self.get_db_value("is_paid") is not None:
			return

		balance = leave_balance(
			self.employee, self.leave_type, self.from_date,
			days=flt(self.total_days), exclude=self.name,
		)

		self.is_paid = 1 if balance["will_be_paid"] else 0

	def on_update(self):
		self.refresh_attendance()

	def on_trash(self):
		self.refresh_attendance()

	def refresh_attendance(self):
		"""
		Recalculate the days this leave covers so the change shows immediately
		rather than at the next scheduled run.
		"""

		from timebridge.timebridge.services import attendance_sync

		attendance_sync.rebuild_for_range(
			from_date=self.from_date, to_date=self.to_date, employee=self.employee
		)
		attendance_sync.mark_absentees(self.from_date, self.to_date, employee=self.employee)


def leaves_between(from_date, to_date, employee=None):
	"""
	Approved leave in a period, as {(employee, date): row}.

	Expanded to one entry per calendar day so attendance can look up a single
	day without repeating the range arithmetic.
	"""

	from frappe.utils import add_days

	filters = {
		"approval_status": "Approved",
		"from_date": ["<=", to_date],
		"to_date": [">=", from_date],
	}

	if employee:
		filters["employee"] = employee

	rows = frappe.get_all(
		"TimeBridge Leave",
		filters=filters,
		fields=["name", "employee", "leave_type", "from_date", "to_date",
		        "half_day", "is_paid"],
		limit=10000,
	)

	expanded = {}

	for row in rows:

		for offset in range(date_diff(row.to_date, row.from_date) + 1):

			day = getdate(add_days(row.from_date, offset))

			if getdate(from_date) <= day <= getdate(to_date):
				expanded[(row.employee, day)] = row

	return expanded


@frappe.whitelist()
def leave_balance(employee, leave_type, on_date, days=1, exclude=None):
	"""
	How much of this type's quota is left, and whether this leave would be paid.

	The single place that answers "will this be paid?". The form panel and the
	save-time decision both call it, so what the user is shown before saving is
	what actually happens.

	`exclude` keeps a leave from counting itself when an existing record is
	reopened — without it, editing any saved leave would always report the
	quota as spent.
	"""

	from timebridge.timebridge.doctype.timebridge_leave_type.timebridge_leave_type import (
		period_bounds,
		rules_for,
	)

	days = flt(days) or 1

	result = {
		"leave_type": leave_type,
		"days_requested": days,
		"quota": 0.0,
		"used": 0.0,
		"remaining": 0.0,
		"paid_days": 0.0,
		"unpaid_days": days,
		"will_be_paid": False,
		"period_label": "",
		"reason": "",
	}

	if not (employee and leave_type and on_date):
		result["reason"] = "not_enough_information"
		return result

	rules = rules_for(leave_type)

	if not cint(rules.is_paid):
		result["reason"] = "type_never_paid"
		return result

	if not flt(rules.quota):
		result["reason"] = "no_quota_set"
		return result

	start, end = period_bounds(leave_type, on_date)

	result["period_label"] = (
		getdate(start).strftime("%Y")
		if rules.quota_period == "Yearly"
		else getdate(start).strftime("%B %Y")
	)

	used = flt(
		frappe.db.sql(
			"""
			SELECT SUM(total_days) FROM `tabTimeBridge Leave`
			WHERE employee = %(employee)s
			  AND leave_type = %(leave_type)s
			  AND approval_status = 'Approved'
			  AND is_paid = 1
			  AND name != %(exclude)s
			  AND from_date BETWEEN %(start)s AND %(end)s
			""",
			{
				"employee": employee,
				"leave_type": leave_type,
				"exclude": exclude or "",
				"start": start,
				"end": end,
			},
		)[0][0]
	)

	quota = flt(rules.quota)
	remaining = max(quota - used, 0)

	result.update({
		"quota": quota,
		"used": used,
		"remaining": remaining,
		# All or nothing: a leave is one record with one is_paid flag, so a
		# request longer than the remaining quota cannot be half paid. The
		# split is reported anyway, because that is what the user needs to see
		# before deciding to split it into two records themselves.
		"paid_days": min(days, remaining),
		"unpaid_days": max(days - remaining, 0),
		"will_be_paid": (used + days) <= quota,
		"reason": "ok" if (used + days) <= quota else "quota_exhausted",
	})

	return result


@frappe.whitelist()
def create_bulk_leaves(leave_type, rows):
	"""
	Record one leave per row, and say plainly what happened to each.

	Entering a month of sick days one form at a time is the kind of chore that
	gets abandoned halfway. This takes a list of (employee, date) pairs and
	makes an ordinary TimeBridge Leave out of each — the same document the form
	makes, through the same validation, so quota, overlap and the paid decision
	behave identically. Nothing here is a second implementation of those rules.

	Rows are handled independently. One bad date does not cost the other
	nineteen, and every skipped row comes back with the reason, because a bulk
	tool that silently drops work is worse than no bulk tool.
	"""

	rows = frappe.parse_json(rows) or []

	if not leave_type:
		frappe.throw("Pick a leave type.")

	created = []
	skipped = []

	for row in rows:

		employee = (row or {}).get("employee")
		date = (row or {}).get("leave_date")

		if not (employee and date):
			# A half-filled row is the user's place-marker, not an error worth
			# reporting back at them.
			continue

		name = frappe.db.get_value("Employee", employee, "employee_name") or employee

		# A day the person actually punched is almost always a mistyped date.
		# Refusing it protects attendance that was built from real evidence —
		# the one thing in this system that is not a guess.
		punches = frappe.db.count(
			"TimeBridge Punch Log",
			{"employee": employee, "timestamp": ["between", [f"{date} 00:00:00", f"{date} 23:59:59"]]},
		)

		if punches:
			skipped.append({
				"employee_name": name,
				"date": date,
				"reason": f"{punches} punch(es) recorded that day — check the date",
			})
			continue

		try:
			doc = frappe.get_doc({
				"doctype": "TimeBridge Leave",
				"employee": employee,
				"leave_type": leave_type,
				"from_date": date,
				"to_date": date,
				"approval_status": "Approved",
			}).insert(ignore_permissions=True)

			created.append({
				"employee_name": name,
				"date": date,
				"is_paid": cint(doc.is_paid),
				"name": doc.name,
			})

		except Exception as exc:
			# Overlaps and anything else validate() objects to land here. The
			# message is already written for a human, so it is passed through.
			skipped.append({
				"employee_name": name,
				"date": date,
				"reason": frappe.utils.strip_html(str(exc)).strip() or "could not be saved",
			})

	frappe.db.commit()

	return {"created": created, "skipped": skipped}
