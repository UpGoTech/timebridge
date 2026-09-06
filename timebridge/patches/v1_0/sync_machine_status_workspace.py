# Spec 012: Machine Status custom block + workspace embed.


def execute():
	from timebridge.timebridge.services.machine_status_block import sync_machine_status_block
	from timebridge.timebridge.services.workspace_sync import sync_app_workspaces

	sync_machine_status_block()
	sync_app_workspaces(force=True)
