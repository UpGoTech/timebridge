# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.services.workspace_sync import (
	sync_app_workspaces,
	workspace_link_exists,
)


class TestWorkspaceSync(FrappeTestCase):

	def test_sync_app_workspaces_includes_machine_log_link(self):
		sync_app_workspaces(force=True)

		self.assertTrue(
			workspace_link_exists("TimeBridge", "TimeBridge Machine Log"),
			"TimeBridge Machine Log must appear on the TimeBridge workspace after sync",
		)

	def test_sync_app_workspaces_is_idempotent(self):
		first = sync_app_workspaces(force=True)
		second = sync_app_workspaces(force=True)

		self.assertEqual(first, second)
		self.assertTrue(workspace_link_exists("TimeBridge", "TimeBridge Sync Log"))
