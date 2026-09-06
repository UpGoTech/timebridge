# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for machine contact kind and workspace status board."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from timebridge.timebridge.iclock import commands
from timebridge.timebridge.services.device_status import get_machine_status_board


class TestMachineStatusBoard(FrappeTestCase):

	MACHINE_ID = "TB-STATUS-A"

	def setUp(self):
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		name = frappe.db.get_value("TimeBridge Machine", {"machine_id": self.MACHINE_ID})
		if name:
			frappe.cache().delete_value(commands.contact_key(name))
			frappe.delete_doc("TimeBridge Machine", name, force=True)
			frappe.db.commit()

	def _make_machine(self, sdk_type="ADMS", status="Disconnected"):
		return frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": self.MACHINE_ID,
				"machine_name": "Status board test",
				"device_brand": "ZKTeco",
				"ip_address": "192.168.99.60",
				"port": 4370,
				"sdk_type": sdk_type,
				"status": status,
				"serial_number": "SN-STATUS-A",
				"adms_status": "Registered" if sdk_type == "ADMS" else None,
			}
		).insert(ignore_permissions=True)

	def test_record_contact_persists_label(self):
		machine = self._make_machine()
		commands.record_contact(machine.name, "poll")
		frappe.db.commit()

		kind = frappe.db.get_value("TimeBridge Machine", machine.name, "last_contact_kind")
		self.assertEqual(kind, "Heartbeat")

		contact = commands.last_contact(machine.name)
		self.assertEqual(contact.get("kind"), "Heartbeat")
		self.assertTrue(contact.get("at"))

	def test_record_contact_attendance_label(self):
		machine = self._make_machine()
		commands.record_contact(machine.name, "attendance")
		self.assertEqual(
			frappe.db.get_value("TimeBridge Machine", machine.name, "last_contact_kind"),
			"Attendance",
		)

	def test_last_contact_falls_back_to_db_kind(self):
		machine = self._make_machine()
		commands.record_contact(machine.name, "handshake")
		frappe.cache().delete_value(commands.contact_key(machine.name))

		contact = commands.last_contact(machine.name)
		self.assertEqual(contact.get("kind"), "Handshake")
		self.assertTrue(contact.get("at"))

	def test_board_live_connected_for_recent_push_contact(self):
		machine = self._make_machine(status="Disconnected")
		commands.record_contact(machine.name, "poll")
		frappe.db.commit()

		board = get_machine_status_board()
		row = next(r for r in board["machines"] if r["name"] == machine.name)
		self.assertEqual(row["status"], "Connected")
		self.assertEqual(row["last_contact_kind"], "Heartbeat")

	def test_board_disconnected_when_push_silent(self):
		machine = self._make_machine(status="Connected")
		old = add_to_date(now_datetime(), minutes=-10)
		frappe.db.set_value(
			"TimeBridge Machine",
			machine.name,
			{
				"last_contact_at": old,
				"last_contact_kind": "Heartbeat",
			},
			update_modified=False,
		)
		frappe.cache().delete_value(commands.contact_key(machine.name))
		frappe.db.commit()

		board = get_machine_status_board()
		row = next(r for r in board["machines"] if r["name"] == machine.name)
		self.assertEqual(row["status"], "Disconnected")
		self.assertEqual(row["last_contact_kind"], "Heartbeat")

	def test_contact_kind_label_passthrough(self):
		self.assertEqual(commands.contact_kind_label("poll"), "Heartbeat")
		self.assertEqual(commands.contact_kind_label("Heartbeat"), "Heartbeat")
		self.assertEqual(commands.contact_kind_label("device_info"), "Device Info")
