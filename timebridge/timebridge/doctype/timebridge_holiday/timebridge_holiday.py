# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe

from frappe.model.document import Document


class TimeBridgeHoliday(Document):
	pass


def holidays_between(from_date, to_date):
	"""
	Dates that should not count as working days, as {date: name}.

	Only active rows. Attendance uses this to write Holiday instead of Absent,
	so a public holiday does not appear as everybody skipping work.
	"""

	rows = frappe.get_all(
		"TimeBridge Holiday",
		filters={
			"is_active": 1,
			"holiday_date": ["between", [from_date, to_date]],
		},
		fields=["holiday_date", "holiday_name"],
		limit=10000,
	)

	return {row.holiday_date: row.holiday_name for row in rows}
