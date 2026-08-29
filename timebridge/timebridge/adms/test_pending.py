# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""
Tests for ADMS pending device signal capture.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms import pending


class TestADMSPending(FrappeTestCase):

    def setUp(self):
        self.serial = "TB-TEST-SERIAL-001"
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        for name in frappe.get_all(
            "TimeBridge Pending Device Signal",
            filters={"serial_number": self.serial},
            pluck="name",
        ):
            frappe.delete_doc("TimeBridge Pending Device Signal", name, force=True)

        for name in frappe.get_all(
            "TimeBridge Machine",
            filters={"serial_number": self.serial},
            pluck="name",
        ):
            frappe.delete_doc("TimeBridge Machine", name, force=True)

        frappe.db.commit()

    def test_record_signal_creates_pending_row(self):
        pending.record_signal(self.serial, "cdata", "GET", {"SN": self.serial, "options": "all"})

        row = frappe.get_doc("TimeBridge Pending Device Signal", self.serial)
        self.assertEqual(row.status, "Pending")
        self.assertEqual(row.signal_type, "Handshake")
        self.assertEqual(row.hit_count, 1)

    def test_record_signal_increments_on_heartbeat(self):
        pending.record_signal(self.serial, "cdata", "GET", {})
        pending.record_signal(self.serial, "getrequest", "GET", {})

        row = frappe.get_doc("TimeBridge Pending Device Signal", self.serial)
        self.assertEqual(row.hit_count, 2)
        self.assertEqual(row.signal_type, "Heartbeat")

    def test_register_machine_closes_pending_row(self):
        pending.record_signal(self.serial, "cdata", "GET", {})

        result = pending.register_machine(
            self.serial,
            "GATE-TEST-1",
            "Test Gate",
            "ZKTeco",
            "192.168.1.50",
        )

        self.assertTrue(frappe.db.exists("TimeBridge Machine", result["machine"]))
        row = frappe.get_doc("TimeBridge Pending Device Signal", self.serial)
        self.assertEqual(row.status, "Registered")
        self.assertEqual(row.registered_machine, result["machine"])

    def test_unlink_machine_reopens_pending_signal(self):
        pending.record_signal(self.serial, "cdata", "GET", {})

        result = pending.register_machine(
            self.serial,
            "GATE-TEST-2",
            "Test Gate 2",
            "ZKTeco",
            "192.168.1.51",
        )

        pending.unlink_machine(result["machine"])
        frappe.db.commit()

        row = frappe.get_doc("TimeBridge Pending Device Signal", self.serial)
        self.assertEqual(row.status, "Pending")
        self.assertFalse(row.registered_machine)

        frappe.delete_doc("TimeBridge Machine", result["machine"], force=True)
        frappe.db.commit()

    def test_dismissed_signal_reopens_on_new_contact(self):
        pending.record_signal(self.serial, "cdata", "GET", {})
        pending.dismiss_signal(self.serial)

        row = frappe.get_doc("TimeBridge Pending Device Signal", self.serial)
        self.assertEqual(row.status, "Dismissed")

        pending.record_signal(self.serial, "getrequest", "GET", {})
        row.reload()
        self.assertEqual(row.status, "Pending")

    def test_classify_signal(self):
        self.assertEqual(pending.classify_signal("cdata", "GET"), "Handshake")
        self.assertEqual(pending.classify_signal("getrequest", "GET"), "Heartbeat")
        self.assertEqual(pending.classify_signal("cdata", "POST"), "Upload")
        self.assertEqual(pending.classify_signal("ping", "GET"), "Ping")
