# Spec 008: ADMS Request Log DocType + workspace link.

import frappe

from timebridge.timebridge.services.workspace_sync import (
	sync_app_workspaces,
	workspace_link_exists,
)


def execute():
	sync_app_workspaces(force=True)

	if not workspace_link_exists("TimeBridge", "TimeBridge ADMS Request Log"):
		frappe.throw("TimeBridge ADMS Request Log workspace link missing after workspace sync")
