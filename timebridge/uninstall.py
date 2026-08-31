# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
App uninstall hooks.

Frappe's remove_app() deletes Workspace rows linked to this app's Module Def.
This hook is a belt-and-suspenders pass for app-owned public workspaces that
must not survive uninstall.
"""

import frappe


APP_WORKSPACES = ("TimeBridge",)


def before_uninstall():
	frappe.flags.ignore_links = True

	for name in APP_WORKSPACES:
		if frappe.db.exists("Workspace", name):
			frappe.delete_doc("Workspace", name, force=True, ignore_permissions=True)

	frappe.db.commit()
