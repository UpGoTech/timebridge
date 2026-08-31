# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Daily punch list for one calendar day — who punched, in/out, count."""

import frappe

from timebridge.timebridge.services.dashboard import build_daily_punch_summary_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = _columns()
	if not filters.get("date"):
		return columns, []
	return columns, build_daily_punch_summary_rows(filters.date, filters.get("machine"))


def _columns():
	return [
		{"label": "User Name", "fieldname": "user_name", "fieldtype": "Data", "width": 180},
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
