# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.services.device_mirror import (
	build_asset_status,
	compute_asset_status,
	compute_overall_status,
	window_bounds,
)


class TestDeviceMirror(FrappeTestCase):
	def test_compute_asset_status_in_sync(self):
		status, delta = compute_asset_status(10, 10)
		self.assertEqual(status, "In sync")
		self.assertEqual(delta, 0)

	def test_compute_asset_status_drift(self):
		status, delta = compute_asset_status(15, 10)
		self.assertEqual(status, "Drift")
		self.assertEqual(delta, 5)

	def test_compute_asset_status_ahead(self):
		status, delta = compute_asset_status(8, 12)
		self.assertEqual(status, "Ahead")
		self.assertEqual(delta, -4)

	def test_compute_asset_status_not_mirrored(self):
		status, delta = compute_asset_status(None, 5)
		self.assertEqual(status, "Not mirrored")
		self.assertIsNone(delta)

	def test_overall_status_drift_wins(self):
		assets = {
			"users": {"status": "In sync"},
			"punches": {"status": "Drift"},
		}
		self.assertEqual(compute_overall_status(assets), "Drift")

	def test_overall_status_ahead_only_is_sync(self):
		assets = {
			"users": {"status": "In sync"},
			"punches": {"status": "Ahead"},
		}
		self.assertEqual(compute_overall_status(assets), "In sync")

	def test_build_asset_status(self):
		result = build_asset_status(
			{"users": 5, "punches": 8},
			{"users": 5, "punches": 10},
		)
		self.assertEqual(result["users"]["status"], "In sync")
		self.assertEqual(result["punches"]["status"], "Ahead")

	def test_window_bounds_default_45_days(self):
		start, end, start_dt, end_dt = window_bounds(45)
		self.assertLessEqual((end - start).days, 45)
