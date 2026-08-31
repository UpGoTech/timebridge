# Spec 007: Employee Monthly Punch Summary report.

import frappe

from timebridge.timebridge.services.workspace_sync import sync_app_workspaces


def execute():
	sync_app_workspaces(force=True)

	ws = frappe.get_doc("Workspace", "TimeBridge")

	card_breaks = {row.label: row.link_count for row in ws.links if row.type == "Card Break"}
	if card_breaks.get("Reports") != 3:
		frappe.throw("Reports card must list Device Roll, Daily Punch Summary, and Employee Monthly Punch Summary")

	_links = {row.link_to: row for row in ws.links if row.type == "Link"}
	for link_to in (
		"Device Roll",
		"daily-punch-summary",
		"employee-monthly-punch-summary",
	):
		if link_to not in _links:
			frappe.throw(f"Workspace missing link: {link_to}")

	if _links["Device Roll"].is_query_report != 1:
		frappe.throw("Device Roll workspace link must be a query report")
	if _links["daily-punch-summary"].link_type != "Page":
		frappe.throw("Daily Punch Summary workspace link must be a Page")
	if _links["employee-monthly-punch-summary"].link_type != "Page":
		frappe.throw("Employee Monthly Punch Summary workspace link must be a Page")
