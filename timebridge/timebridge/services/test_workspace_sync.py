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

	def test_sync_app_workspaces_dashboard_cards(self):
		sync_app_workspaces(force=True)

		ws = frappe.get_doc("Workspace", "TimeBridge")
		card_names = {row.number_card_name for row in ws.number_cards}

		for name in (
			"TimeBridge Registered Machines",
			"TimeBridge Connected Machines",
			"TimeBridge Active Users",
			"TimeBridge Archived Users",
			"TimeBridge Total Punch Logs",
			"TimeBridge Punches Today",
			"TimeBridge Unmapped Punches",
		):
			self.assertIn(name, card_names, f"{name} must be on the TimeBridge workspace")

		for row in ws.links:
			self.assertNotEqual(
				row.link_to,
				"add-machine",
				"Add Machine must not be a workspace link after spec 005",
			)

		self.assertFalse(ws.shortcuts, "TimeBridge workspace must have no shortcuts after spec 005")
