# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
One leave type and the rules that govern it.

Quotas used to be a single company-wide number shared by every kind of leave,
which meant a casual day taken on the 5th quietly turned a sick day on the 18th
unpaid. Each type now carries its own allowance, its own period, and its own
answer to whether anything unused rolls forward.

Keeping the rules here rather than in code means a new type — maternity,
bereavement, whatever comes up — is a record someone creates, not a change
someone has to ask a developer for.
"""

import frappe

from frappe.model.document import Document
from frappe.utils import cint, flt, get_first_day, get_last_day, getdate


class TimeBridgeLeaveType(Document):

	def validate(self):

		if flt(self.quota) < 0:
			frappe.throw("Quota cannot be negative.")

		# A type nobody is paid for has nothing to ration, and a quota sitting
		# on it would read as an entitlement that does not exist.
		if not cint(self.is_paid) and flt(self.quota):
			frappe.throw(
				f"{self.leave_type_name} is not paid, so it cannot carry a quota. "
				"Either tick Paid Leave or set the quota to zero."
			)


def period_bounds(leave_type, on_date):
	"""
	The window a quota is counted over, for a leave starting on this date.

	Returns (start, end). A yearly quota counts across the calendar year, a
	monthly one across that month alone.
	"""

	row = frappe.db.get_value(
		"TimeBridge Leave Type", leave_type, ["quota_period"], as_dict=True
	)

	on_date = getdate(on_date)

	if row and row.quota_period == "Yearly":
		return getdate(f"{on_date.year}-01-01"), getdate(f"{on_date.year}-12-31")

	return get_first_day(on_date), get_last_day(on_date)


def rules_for(leave_type):
	"""
	The quota rules for a type, or safe defaults when it has none.

	An unknown type is treated as unpaid rather than unlimited: guessing
	generously would put money on a payslip nobody authorised.
	"""

	row = frappe.db.get_value(
		"TimeBridge Leave Type",
		leave_type,
		["quota", "quota_period", "carry_forward", "is_paid", "is_active"],
		as_dict=True,
	)

	if not row:
		return frappe._dict(quota=0, quota_period="Monthly", carry_forward=0,
		                    is_paid=0, is_active=0)

	return row
