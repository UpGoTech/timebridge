# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Keep Desk workspaces in the database identical to the app's workspace JSON files.

Frappe only re-imports workspace JSON on migrate when the file hash or timestamp
beats the database row. Editing JSON alone does not update sites that already
have the workspace — call sync_app_workspaces() from after_install and from a
post_model_sync patch whenever links change.
"""

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def workspace_json_paths(app_name="timebridge"):
	"""Yield absolute paths to every workspace JSON shipped by the app."""

	base = os.path.join(frappe.get_app_path(app_name), app_name, "workspace")

	if not os.path.isdir(base):
		return

	for folder in sorted(os.listdir(base)):
		path = os.path.join(base, folder, f"{folder}.json")
		if os.path.isfile(path):
			yield path


def sync_app_workspaces(app_name="timebridge", force=True):
	"""
	Force-import all app workspace JSON files.

	Returns the list of workspace names synced. Safe on fresh install (creates)
	and on existing sites (overwrites app-owned public workspace from JSON).
	"""

	synced = []

	for path in workspace_json_paths(app_name):
		import_file_by_path(path, force=force, ignore_version=True)
		synced.append(os.path.splitext(os.path.basename(path))[0])

	if synced:
		frappe.db.commit()

	return synced


def ensure_workspace_link(
	workspace_name,
	*,
	label,
	link_to,
	link_type="DocType",
	card_break=None,
	is_query_report=0,
):
	"""
	Idempotent helper for patches that add a single link without reimporting
	the whole workspace. Prefer sync_app_workspaces() when many fields change.
	"""

	if not frappe.db.exists("Workspace", workspace_name):
		sync_app_workspaces()
		return

	ws = frappe.get_doc("Workspace", workspace_name)

	for row in ws.links:
		if row.type == "Link" and row.link_to == link_to and row.link_type == link_type:
			return

	if card_break:
		for row in ws.links:
			if row.type == "Card Break" and row.label == card_break:
				row.link_count = (row.link_count or 0) + 1
				break

	ws.append(
		"links",
		{
			"type": "Link",
			"label": label,
			"link_to": link_to,
			"link_type": link_type,
			"is_query_report": is_query_report,
			"hidden": 0,
			"onboard": 0,
		},
	)

	ws.save(ignore_permissions=True)
	frappe.db.commit()


def workspace_link_exists(workspace_name, link_to, link_type="DocType"):
	if not frappe.db.exists("Workspace", workspace_name):
		return False

	return bool(
		frappe.db.exists(
			"Workspace Link",
			{
				"parent": workspace_name,
				"parenttype": "Workspace",
				"link_to": link_to,
				"link_type": link_type,
			},
		)
	)
