# Copyright (c) 2026, UPGO and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase
import frappe

from timebridge.timebridge.adms import stamps
from timebridge.timebridge.adms.api import build_handshake


class TestADMSStamps(FrappeTestCase):

    def test_parse_upload_stamp_from_query(self):
        args = {"table": "ATTLOG", "Stamp": "82983982"}
        self.assertEqual(stamps.parse_upload_stamp(args, "ATTLOG"), "82983982")

    def test_parse_upload_stamp_from_compound_table(self):
        args = {"table": "ATTLOG Stamp=12345"}
        self.assertEqual(stamps.parse_upload_stamp(args, "ATTLOG"), "12345")

    def test_parse_opstamp_for_operlog(self):
        args = {"table": "OPERLOG", "OpStamp": "9238883"}
        self.assertEqual(stamps.parse_upload_stamp(args, "OPERLOG"), "9238883")

    def test_stamp_from_attlog_records(self):
        records = [
            {"timestamp": "2026-07-30 10:05:12"},
            {"timestamp": "2026-07-30 19:02:44"},
        ]
        self.assertEqual(
            stamps.stamp_from_attlog_records(records),
            "2026-07-30T19:02:44",
        )

    def test_handshake_defaults_without_machine(self):
        reply = build_handshake("SN123", machine=None)
        self.assertIn("Stamp=9999", reply)
        self.assertIn("OpStamp=9999", reply)
        self.assertIn("GET OPTION FROM: SN123", reply)

    def test_handshake_echoes_persisted_stamps(self):
        machine = self._make_machine("STAMP-001")

        frappe.db.set_value(
            "TimeBridge Machine",
            machine,
            {"adms_stamp": "111", "adms_op_stamp": "222"},
        )

        reply = build_handshake("STAMP-001", machine=machine)
        self.assertIn("Stamp=111", reply)
        self.assertIn("OpStamp=222", reply)

    def test_record_attlog_stamp_from_query(self):
        machine = self._make_machine("STAMP-002")
        args = {"table": "ATTLOG", "Stamp": "555666"}

        stamps.record_attlog_stamp(
            machine,
            args,
            "ATTLOG",
            [{"timestamp": "2026-07-30 10:00:00"}],
        )

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp"),
            "555666",
        )

    def test_record_attlog_stamp_falls_back_to_latest_punch(self):
        machine = self._make_machine("STAMP-003")
        args = {"table": "ATTLOG"}

        stamps.record_attlog_stamp(
            machine,
            args,
            "ATTLOG",
            [
                {"timestamp": "2026-07-30 10:05:12"},
                {"timestamp": "2026-07-30 19:02:44"},
            ],
        )

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp"),
            "2026-07-30T19:02:44",
        )

    def _make_machine(self, serial):
        doc = frappe.get_doc(
            {
                "doctype": "TimeBridge Machine",
                "machine_id": serial,
                "machine_name": serial,
                "device_brand": "ZKTeco",
                "serial_number": serial,
                "ip_address": "10.0.0.1",
                "port": 4370,
                "sdk_type": "ADMS",
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name
