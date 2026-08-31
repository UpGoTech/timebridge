# Spec 004: push TimeBridge workspace JSON (incl. Machine Log link) to existing sites.

import frappe

from timebridge.timebridge.services.workspace_sync import (
	sync_app_workspaces,
	workspace_link_exists,
)


def execute():
	sync_app_workspaces(force=True)

	if not workspace_link_exists("TimeBridge", "TimeBridge Machine Log"):
		frappe.throw("TimeBridge Machine Log workspace link missing after workspace sync")
