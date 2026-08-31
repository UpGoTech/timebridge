# Spec 005: reorder sidebar link cards to Devices / Data / Reports / Logs.

from timebridge.timebridge.services.workspace_sync import sync_app_workspaces


def execute():
	sync_app_workspaces(force=True)
