# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Daily punch list for one calendar day — who punched, in/out, count."""

import frappe

from timebridge.timebridge.services.dashboard import build_daily_punch_summary_rows


def execute(filters=None):
	filters = frappe._dict(filters or {})
	show_machine = not filters.get("machine")
	columns = _columns(show_machine)
	if not filters.get("date"):
		return columns, []
	return columns, build_daily_punch_summary_rows(filters.date, filters.get("machine"))


def _columns(show_machine):
	columns = []
	if show_machine:
		columns.append(
			{
				"label": "Machine",
				"fieldname": "machine",
				"fieldtype": "Link",
				"options": "TimeBridge Machine",
				"width": 140,
			}
		)
	columns.extend(
		[
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
			{"label": "Punches", "fieldname": "punches", "fieldtype": "Int", "width": 90},
		]
	)
	return columns
