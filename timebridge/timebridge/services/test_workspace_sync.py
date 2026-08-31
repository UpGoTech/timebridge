# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import json

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
			"TimeBridge Active Users",
			"TimeBridge Today's Punch Summary",
			"TimeBridge Unmapped Punches",
		):
			self.assertIn(name, card_names, f"{name} must be on the TimeBridge workspace")

		chart_names = {row.chart_name for row in ws.charts}
		self.assertIn(
			"TimeBridge Active Users Per Day",
			chart_names,
			"Active Users Per Day chart must be on the workspace",
		)

		for row in ws.links:
			self.assertNotEqual(
				row.link_to,
				"add-machine",
				"Add Machine must not be a workspace link after spec 005",
			)

		self.assertFalse(ws.shortcuts, "TimeBridge workspace must have no shortcuts after spec 005")

	def test_sync_app_workspaces_link_cards(self):
		sync_app_workspaces(force=True)

		ws = frappe.get_doc("Workspace", "TimeBridge")
		card_breaks = {
			row.label: row.link_count for row in ws.links if row.type == "Card Break"
		}
		links = {row.link_to: row for row in ws.links if row.type == "Link"}

		self.assertEqual(card_breaks.get("Devices"), 2)
		self.assertEqual(card_breaks.get("Data"), 1)
		self.assertEqual(card_breaks.get("Logs"), 2)
		self.assertEqual(card_breaks.get("Reports"), 2)
		self.assertNotIn("Setup", card_breaks)

		for link_to in (
			"TimeBridge Machine",
			"TimeBridge Settings",
			"TimeBridge Machine User",
			"TimeBridge Sync Log",
			"TimeBridge Machine Log",
			"Device Roll",
			"Daily Punch Summary",
		):
			self.assertIn(link_to, links)

		self.assertEqual(links["Device Roll"].is_query_report, 1)
		self.assertEqual(links["Daily Punch Summary"].is_query_report, 1)

	def test_sync_app_workspaces_content_matches_widget_labels(self):
		sync_app_workspaces(force=True)

		ws = frappe.get_doc("Workspace", "TimeBridge")
		number_card_labels = {row.label for row in ws.number_cards}
		chart_labels = {row.label for row in ws.charts}

		for block in json.loads(ws.content):
			if block["type"] == "number_card":
				self.assertIn(
					block["data"]["number_card_name"],
					number_card_labels,
					"content number_card_name must match a workspace number card label",
				)
			elif block["type"] == "chart":
				self.assertIn(
					block["data"]["chart_name"],
					chart_labels,
					"content chart_name must match a workspace chart label",
				)

	def test_sync_app_workspaces_chart_before_number_cards(self):
		sync_app_workspaces(force=True)

		ws = frappe.get_doc("Workspace", "TimeBridge")
		block_types = [
			block["type"]
			for block in json.loads(ws.content)
			if block["type"] in ("chart", "number_card")
		]
		chart_idx = block_types.index("chart")
		first_card_idx = block_types.index("number_card")
		self.assertLess(chart_idx, first_card_idx, "Chart must appear before number cards")
