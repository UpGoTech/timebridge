# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Monthly punch list for one user — in/out per day for a calendar month."""

import frappe

from timebridge.timebridge.services.dashboard import build_employee_monthly_punch_summary_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = _columns()
	if not filters.get("machine_user") or not filters.get("month"):
		return columns, []
	return columns, build_employee_monthly_punch_summary_rows(
		filters.machine_user, filters.month
	)


def _columns():
	return [
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 110},
		{
			"label": "Punched In",
			"fieldname": "punched_in",
			"fieldtype": "Time",
			"width": 110,
		},
		{
			"label": "Punched Out",
			"fieldname": "punched_out",
			"fieldtype": "Time",
			"width": 110,
		},
		{
			"label": "Working Hrs",
			"fieldname": "working_hours_display",
			"fieldtype": "Data",
			"width": 100,
		},
		{"label": "Punches", "fieldname": "punches", "fieldtype": "Int", "width": 90},
	]
