import json

import frappe


def execute():
	_fill_full_name()
	_remap_list_sort()


def _fill_full_name():
	if not frappe.db.has_column("TimeBridge Employee", "employee"):
		return
	frappe.db.sql(
		"""
		UPDATE `tabTimeBridge Employee`
		SET employee = TRIM(CONCAT_WS(' ',
			NULLIF(first_name, ''),
			NULLIF(middle_name, ''),
			NULLIF(last_name, '')
		))
		WHERE IFNULL(employee, '') = ''
		"""
	)


def _remap_list_sort():
	rows = frappe.db.sql(
		"""
		SELECT `user`, `doctype`, `data`
		FROM `__UserSettings`
		WHERE `doctype` = 'TimeBridge Employee'
		""",
		as_dict=True,
	)
	for row in rows:
		try:
			data = json.loads(row.data or "{}")
		except (TypeError, ValueError):
			continue
		changed = False
		for view in ("List", "Report"):
			settings = data.get(view)
			if not isinstance(settings, dict):
				continue
			if settings.get("sort_by") in ("employee_name", "first_name"):
				settings["sort_by"] = "employee"
				changed = True
		if not changed:
			continue
		frappe.db.sql(
			"UPDATE `__UserSettings` SET `data` = %(data)s WHERE `user` = %(user)s AND `doctype` = %(doctype)s",
			{"data": json.dumps(data), "user": row.user, "doctype": row.doctype},
		)
		frappe.cache.hset("_user_settings", f"{row.doctype}::{row.user}", None)
