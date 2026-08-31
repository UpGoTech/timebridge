# Spec 006: Daily Punch Summary report + Today's Punch Summary card rename.

import json

import frappe

from timebridge.timebridge.services.workspace_sync import sync_app_workspaces

OLD_NUMBER_CARD = "TimeBridge Users Punched Today"
NEW_NUMBER_CARD = "TimeBridge Today's Punch Summary"


def execute():
	if frappe.db.exists("Number Card", OLD_NUMBER_CARD):
		frappe.rename_doc("Number Card", OLD_NUMBER_CARD, NEW_NUMBER_CARD, force=True)
	elif frappe.db.exists("Number Card", NEW_NUMBER_CARD):
		frappe.db.set_value("Number Card", NEW_NUMBER_CARD, "label", "Today's Punch Summary")

	sync_app_workspaces(force=True)

	ws = frappe.get_doc("Workspace", "TimeBridge")

	card_names = {row.number_card_name for row in ws.number_cards}
	if NEW_NUMBER_CARD not in card_names:
		frappe.throw(f"Workspace must include number card {NEW_NUMBER_CARD!r}")

	card_breaks = {row.label: row.link_count for row in ws.links if row.type == "Card Break"}
	if card_breaks.get("Reports") != 2:
		frappe.throw("Reports card must list Device Roll and Daily Punch Summary")

	_links = {row.link_to: row for row in ws.links if row.type == "Link"}
	for link_to in ("Device Roll", "Daily Punch Summary"):
		if link_to not in _links:
			frappe.throw(f"Workspace missing report link: {link_to}")
		if not _links[link_to].is_query_report:
			frappe.throw(f"{link_to} workspace link must be a query report")

	number_card_labels = {row.label for row in ws.number_cards}
	for block in json.loads(ws.content):
		if block["type"] == "number_card":
			name = block["data"]["number_card_name"]
			if name not in number_card_labels:
				frappe.throw(
					f"Workspace content number_card_name {name!r} must match a number card label"
				)

	if "Today's Punch Summary" not in number_card_labels:
		frappe.throw("Workspace must label the today's punch card as Today's Punch Summary")
