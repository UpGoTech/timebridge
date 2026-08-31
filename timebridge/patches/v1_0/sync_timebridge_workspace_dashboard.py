# Spec 005 v2: slim dashboard + reorganized workspace link cards.

import json

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
	required_cards = {
		"TimeBridge Active Users",
		"TimeBridge Today's Punch Summary",
		"TimeBridge Unmapped Punches",
	}
	missing_cards = required_cards - card_names
	if missing_cards:
		frappe.throw(f"TimeBridge workspace missing number cards after sync: {missing_cards}")

	chart_names = {row.chart_name for row in ws.charts}
	if "TimeBridge Active Users Per Day" not in chart_names:
		frappe.throw("TimeBridge workspace must include Active Users Per Day chart")

	number_card_labels = {row.label for row in ws.number_cards}
	chart_labels = {row.label for row in ws.charts}
	for block in json.loads(ws.content):
		if block["type"] == "number_card":
			name = block["data"]["number_card_name"]
			if name not in number_card_labels:
				frappe.throw(
					f"Workspace content number_card_name {name!r} must match a number card label, not the Number Card doc name"
				)
		elif block["type"] == "chart":
			name = block["data"]["chart_name"]
			if name not in chart_labels:
				frappe.throw(
					f"Workspace content chart_name {name!r} must match a chart label, not the Dashboard Chart doc name"
				)

	_links = {row.link_to: row for row in ws.links if row.type == "Link"}
	card_breaks = {row.label: row.link_count for row in ws.links if row.type == "Card Break"}

	if card_breaks.get("Devices") != 2:
		frappe.throw("Devices card must list Machine and Settings")
	if card_breaks.get("Data") != 1:
		frappe.throw("Data card must list only Machine User")
	if card_breaks.get("Logs") != 2:
		frappe.throw("Logs card must list Sync Log and Machine Log")
	if card_breaks.get("Reports") != 2:
		frappe.throw("Reports card must list Device Roll and Daily Punch Summary")
	if "Setup" in card_breaks:
		frappe.throw("Setup card break must be removed from workspace")

	for link_to in (
		"TimeBridge Machine",
		"TimeBridge Settings",
		"TimeBridge Machine User",
		"TimeBridge Sync Log",
		"TimeBridge Machine Log",
		"Device Roll",
		"Daily Punch Summary",
	):
		if link_to not in _links:
			frappe.throw(f"Workspace missing link: {link_to}")

	if _links["Device Roll"].is_query_report != 1:
		frappe.throw("Device Roll workspace link must be a query report")
	if _links["Daily Punch Summary"].is_query_report != 1:
		frappe.throw("Daily Punch Summary workspace link must be a query report")
