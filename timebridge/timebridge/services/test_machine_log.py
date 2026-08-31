# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for per-machine diagnostic logging."""

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.services.machine_log import (
	clear_old_machine_logs,
	write_machine_log,
)

DOCTYPE = "TimeBridge Machine Log"


class TestMachineLog(FrappeTestCase):

	def setUp(self):
		self.machine_id = "TB-ML-TEST-001"
		self._old_silence = frappe.conf.get("timebridge_silence_device_logs")
		frappe.conf.timebridge_silence_device_logs = 0
		self._cleanup()

	def tearDown(self):
		if self._old_silence is None:
			frappe.conf.pop("timebridge_silence_device_logs", None)
		else:
			frappe.conf.timebridge_silence_device_logs = self._old_silence
		self._cleanup()

	def _cleanup(self):
		for name in frappe.get_all(
			DOCTYPE,
			filters={"message": ["like", "TB-ML-TEST%"]},
			pluck="name",
		):
			frappe.delete_doc(DOCTYPE, name, force=True)

		if frappe.db.exists("TimeBridge Machine", {"machine_id": self.machine_id}):
			frappe.delete_doc(
				"TimeBridge Machine",
				frappe.db.get_value("TimeBridge Machine", {"machine_id": self.machine_id}),
				force=True,
			)

		frappe.db.commit()

	def _make_machine(self):
		doc = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": self.machine_id,
				"machine_name": "TB-ML-TEST Machine",
				"device_brand": "ZKTeco",
				"ip_address": "192.168.99.99",
				"port": 4370,
				"sdk_type": "PyZK",
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		return doc.name

	def test_write_machine_log_inserts_row(self):
		machine = self._make_machine()

		name = write_machine_log(
			machine=machine,
			level="Error",
			event="Pull",
			message="TB-ML-TEST pull failed",
			details="traceback here",
		)

		self.assertTrue(name)
		row = frappe.get_doc(DOCTYPE, name)
		self.assertEqual(row.machine, machine)
		self.assertEqual(row.level, "Error")
		self.assertEqual(row.event, "Pull")

	def test_heartbeat_info_skipped_without_debug(self):
		machine = self._make_machine()
		frappe.db.set_single_value("TimeBridge Settings", "enable_debug_log", 0)

		name = write_machine_log(
			machine=machine,
			level="Info",
			event="Heartbeat",
			message="TB-ML-TEST heartbeat",
		)

		self.assertIsNone(name)
		self.assertFalse(
			frappe.db.exists(DOCTYPE, {"machine": machine, "event": "Heartbeat"})
		)

	def test_heartbeat_info_written_with_debug(self):
		machine = self._make_machine()
		frappe.db.set_single_value("TimeBridge Settings", "enable_debug_log", 1)

		name = write_machine_log(
			machine=machine,
			level="Info",
			event="Heartbeat",
			message="TB-ML-TEST heartbeat debug",
		)

		self.assertTrue(name)

	def test_write_machine_log_never_raises(self):
		with patch(
			"frappe.get_doc",
			side_effect=RuntimeError("insert failed"),
		):
			result = write_machine_log(message="TB-ML-TEST should not raise")

		self.assertIsNone(result)

	@patch("timebridge.timebridge.services.pull_sync.probe_socket", return_value=(False, "timeout"))
	def test_pull_unreachable_writes_machine_log(self, _mock_probe):
		from timebridge.timebridge.services.pull_sync import pull_all_data

		machine = self._make_machine()

		result = pull_all_data(machine, days=1)

		self.assertEqual(result["status"], "failed")
		self.assertTrue(
			frappe.db.exists(
				DOCTYPE,
				{"machine": machine, "level": "Error", "event": "Pull"},
			)
		)

	def test_clear_old_machine_logs(self):
		machine = self._make_machine()
		name = write_machine_log(
			machine=machine,
			level="Warning",
			event="Other",
			message="TB-ML-TEST old row",
		)
		frappe.db.set_value(DOCTYPE, name, "creation", "2020-01-01 00:00:00")
		frappe.db.commit()

		deleted = clear_old_machine_logs()

		self.assertGreaterEqual(deleted, 1)
		self.assertFalse(frappe.db.exists(DOCTYPE, name))
