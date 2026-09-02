# Spec 011: ADMS Command Lab workspace link.


def execute():
	from timebridge.timebridge.services.workspace_sync import sync_app_workspaces

	sync_app_workspaces()
