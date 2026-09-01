# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe

from timebridge.timebridge.services.workspace_sync import sync_app_workspaces

DROPPED_DOCTYPES = [
	"TimeBridge Pending Device Signal",
	"TimeBridge ADMS Request Log",
]

DROPPED_PAGES = ["device-registration"]


def execute():
	frappe.flags.ignore_links = True

	for name in DROPPED_PAGES:
		if frappe.db.exists("Page", name):
			frappe.delete_doc(
				"Page", name, force=1, ignore_permissions=True, delete_permanently=True
			)

	for name in DROPPED_DOCTYPES:
		if frappe.db.exists("DocType", name):
			frappe.delete_doc(
				"DocType", name, force=1, ignore_permissions=True, delete_permanently=True
			)

	columns = frappe.db.get_table_columns("TimeBridge Machine")
	if "adms_status" in columns and "sdk_type" in columns:
		frappe.db.sql(
			"""
			UPDATE `tabTimeBridge Machine`
			SET adms_status = 'Registered'
			WHERE sdk_type = 'ADMS'
			AND (adms_status IS NULL OR adms_status = '')
			"""
		)

	sync_app_workspaces(force=True)
