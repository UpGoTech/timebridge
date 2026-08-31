# Spec 005: push dashboard number cards and remove Add Machine from workspace.

import frappe

from timebridge.timebridge.services.workspace_sync import sync_app_workspaces


def execute():
	sync_app_workspaces(force=True)

	ws = frappe.get_doc("Workspace", "TimeBridge")

	for row in ws.links:
		if row.type == "Link" and row.link_to == "add-machine":
			frappe.throw("Add Machine must not remain on the TimeBridge workspace after sync")

	if ws.shortcuts:
		frappe.throw("TimeBridge workspace shortcuts must be empty after spec 005 sync")

	card_names = {row.number_card_name for row in ws.number_cards}
	required = {
		"TimeBridge Registered Machines",
		"TimeBridge Connected Machines",
		"TimeBridge Active Users",
		"TimeBridge Archived Users",
		"TimeBridge Total Punch Logs",
		"TimeBridge Punches Today",
		"TimeBridge Unmapped Punches",
	}
	missing = required - card_names
	if missing:
		frappe.throw(f"TimeBridge workspace missing number cards after sync: {missing}")
