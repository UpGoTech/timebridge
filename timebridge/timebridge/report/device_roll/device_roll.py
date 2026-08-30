# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Diagnostic: did this PIN punch in the selected period? Not HR attendance."""

import frappe

from frappe.utils import getdate


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = [
		{"label": "PIN", "fieldname": "user_id", "fieldtype": "Data", "width": 100},
		{"label": "Name", "fieldname": "user_name", "fieldtype": "Data", "width": 180},
		{
			"label": "Machine User",
			"fieldname": "machine_user",
			"fieldtype": "Link",
			"options": "TimeBridge Machine User",
			"width": 140,
		},
		{"label": "Punched", "fieldname": "punched", "fieldtype": "Data", "width": 90},
		{"label": "Punch count", "fieldname": "punch_count", "fieldtype": "Int", "width": 110},
		{
			"label": "Last punch",
			"fieldname": "last_punch",
			"fieldtype": "Datetime",
			"width": 160,
		},
	]
	if not filters.machine or not filters.from_date or not filters.to_date:
		return columns, []
	return columns, build_rows(filters.machine, filters.from_date, filters.to_date)


def build_rows(machine, from_date, to_date):
	from_date = getdate(from_date)
	to_date = getdate(to_date)

	users = frappe.get_all(
		"TimeBridge Machine User",
		filters={"machine": machine, "is_active": 1},
		fields=["name", "user_id", "user_name"],
		order_by="user_id",
	)

	stats = {}
	for row in frappe.db.sql(
		"""
		SELECT device_user_id,
		       COUNT(*) AS punch_count,
		       MAX(timestamp) AS last_punch
		FROM `tabTimeBridge Punch Log`
		WHERE machine = %(machine)s
		  AND DATE(timestamp) BETWEEN %(from_date)s AND %(to_date)s
		GROUP BY device_user_id
		""",
		{"machine": machine, "from_date": from_date, "to_date": to_date},
		as_dict=True,
	):
		stats[str(row.device_user_id)] = row

	out = []
	for user in users:
		hit = stats.get(str(user.user_id))
		out.append(
			{
				"user_id": user.user_id,
				"user_name": user.user_name,
				"machine_user": user.name,
				"punched": "Yes" if hit else "No",
				"punch_count": hit.punch_count if hit else 0,
				"last_punch": hit.last_punch if hit else None,
			}
		)
	return out
