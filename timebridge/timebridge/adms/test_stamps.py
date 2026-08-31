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

    def test_parse_upload_stamp_from_attlogstamp(self):
        args = {"table": "ATTLOG", "AttLogStamp": "82983982", "Stamp": "9999"}
        self.assertEqual(stamps.parse_upload_stamp(args, "ATTLOG"), "82983982")

    def test_parse_upload_stamp_from_compound_table(self):
        args = {"table": "ATTLOG Stamp=12345"}
        self.assertEqual(stamps.parse_upload_stamp(args, "ATTLOG"), "12345")

    def test_parse_upload_stamp_ignores_placeholder(self):
        args = {"table": "ATTLOG", "Stamp": "9999"}
        self.assertIsNone(stamps.parse_upload_stamp(args, "ATTLOG"))

    def test_parse_upload_stamp_ignores_long_nine_placeholder(self):
        args = {"table": "ATTLOG", "Stamp": "99999999"}
        self.assertIsNone(stamps.parse_upload_stamp(args, "ATTLOG"))

    def test_record_attlog_stamp_ignores_placeholder_9999(self):
        machine = self._make_machine("STAMP-004")
        args = {"table": "ATTLOG", "Stamp": "9999"}

        stamps.record_attlog_stamp(
            machine,
            args,
            "ATTLOG",
            [
                {"timestamp": "2026-08-31 17:40:30"},
                {"timestamp": "2026-08-31 17:40:39"},
            ],
        )

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp"),
            "2026-08-31 17:40:39",
        )

    def test_handshake_ignores_persisted_placeholder(self):
        machine = self._make_machine("STAMP-005")

        frappe.db.set_value(
            "TimeBridge Machine",
            machine,
            {"adms_stamp": "9999", "adms_op_stamp": "9999"},
        )

        reply = build_handshake("STAMP-005", machine=machine)
        self.assertIn("ATTLOGStamp=9999", reply)
        self.assertIn("OPERLOGStamp=9999", reply)

        frappe.db.set_value("TimeBridge Machine", machine, "adms_stamp", "82983982")
        reply = build_handshake("STAMP-005", machine=machine)
        self.assertIn("Stamp=82983982", reply)
        self.assertIn("ATTLOGStamp=82983982", reply)

    def test_parse_opstamp_for_operlog(self):
        args = {"table": "OPERLOG", "OpStamp": "9238883"}
        self.assertEqual(stamps.parse_upload_stamp(args, "OPERLOG"), "9238883")

    def test_parse_operlogstamp_for_operlog(self):
        args = {"table": "OPERLOG", "OperLogStamp": "9238883", "OpStamp": "9999"}
        self.assertEqual(stamps.parse_upload_stamp(args, "OPERLOG"), "9238883")

    def test_stamp_from_attlog_records_attendance_datetime(self):
        records = [{"timestamp": "2026-07-30 19:02:44"}]
        self.assertEqual(
            stamps.stamp_from_attlog_records(records, stamps.STAMP_FORMAT_ATTLOG),
            "2026-07-30 19:02:44",
        )

    def test_stamp_from_attlog_records_unix(self):
        records = [
            {"timestamp": "2026-07-30 10:05:12"},
            {"timestamp": "2026-07-30 19:02:44"},
        ]
        stamp = stamps.stamp_from_attlog_records(records, stamps.STAMP_FORMAT_UNIX)
        self.assertTrue(stamp.isdigit())

    def test_stamp_from_attlog_records_iso(self):
        records = [{"timestamp": "2026-07-30 19:02:44"}]
        self.assertEqual(
            stamps.stamp_from_attlog_records(records, stamps.STAMP_FORMAT_ISO),
            "2026-07-30T19:02:44",
        )

    def test_stamp_from_attlog_records_compact(self):
        records = [{"timestamp": "2026-07-30 19:02:44"}]
        self.assertEqual(
            stamps.stamp_from_attlog_records(records, stamps.STAMP_FORMAT_COMPACT),
            "20260730190244",
        )

    def test_handshake_defaults_without_machine(self):
        reply = build_handshake("SN123", machine=None)
        self.assertIn("Stamp=9999", reply)
        self.assertIn("ATTLOGStamp=9999", reply)
        self.assertIn("OPERLOGStamp=9999", reply)
        self.assertIn("ATTPHOTOStamp=9999", reply)

    def test_handshake_echoes_persisted_stamps(self):
        machine = self._make_machine("STAMP-001")

        frappe.db.set_value(
            "TimeBridge Machine",
            machine,
            {"adms_stamp": "111", "adms_op_stamp": "222"},
        )

        reply = build_handshake("STAMP-001", machine=machine)
        self.assertIn("Stamp=111", reply)
        self.assertIn("ATTLOGStamp=111", reply)
        self.assertIn("OPERLOGStamp=222", reply)

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

        stored = frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp")
        self.assertEqual(stored, "2026-07-30 19:02:44")

    def test_record_attlog_stamp_respects_iso_format_setting(self):
        machine = self._make_machine("STAMP-006")
        frappe.db.set_value(
            "TimeBridge Machine",
            machine,
            "adms_stamp_format",
            stamps.STAMP_FORMAT_ISO,
        )

        stamps.record_attlog_stamp(
            machine,
            {"table": "ATTLOG", "Stamp": "9999"},
            "ATTLOG",
            [{"timestamp": "2026-08-31 17:40:39"}],
        )

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp"),
            "2026-08-31T17:40:39",
        )

    def test_persist_stamp_is_monotonic_for_numeric(self):
        machine = self._make_machine("STAMP-007")

        stamps._persist_stamp(machine, stamps.ATTLOG_FIELD, "900")
        stamps._persist_stamp(machine, stamps.ATTLOG_FIELD, "800")

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp"),
            "900",
        )

    def test_persist_stamp_advances_on_duplicate_batch(self):
        machine = self._make_machine("STAMP-008")
        frappe.db.set_value("TimeBridge Machine", machine, "adms_stamp", "2026-07-30 10:00:00")

        stamps.record_attlog_stamp(
            machine,
            {"table": "ATTLOG", "Stamp": "9999"},
            "ATTLOG",
            [
                {"timestamp": "2026-07-30 10:05:12"},
                {"timestamp": "2026-07-30 19:02:44"},
            ],
        )

        stored = frappe.db.get_value("TimeBridge Machine", machine, "adms_stamp")
        self.assertEqual(stored, "2026-07-30 19:02:44")
        self.assertNotEqual(stored, "2026-07-30 10:00:00")

    def test_infer_stamp_format_from_stored_value(self):
        self.assertEqual(stamps.infer_stamp_format("82983982"), stamps.STAMP_FORMAT_UNIX)
        self.assertEqual(
            stamps.infer_stamp_format("20260730190244"),
            stamps.STAMP_FORMAT_COMPACT,
        )
        self.assertEqual(
            stamps.infer_stamp_format("2026-08-31T17:40:39"),
            stamps.STAMP_FORMAT_ISO,
        )
        self.assertEqual(
            stamps.infer_stamp_format("2026-07-30 19:02:44"),
            stamps.STAMP_FORMAT_ATTLOG,
        )

    def test_record_operlog_stamp_falls_back_to_op_time(self):
        machine = self._make_machine("STAMP-009")

        stamps.record_operlog_stamp(
            machine,
            {"table": "OPERLOG", "Stamp": "9999"},
            "OPERLOG",
            op_rows=[{"op_time": "2026-08-31 09:19:01"}],
        )

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_op_stamp"),
            "2026-08-31 09:19:01",
        )

    def test_record_operlog_stamp_falls_back_to_now_when_empty(self):
        machine = self._make_machine("STAMP-010")

        stamps.record_operlog_stamp(
            machine,
            {"table": "OPERLOG", "Stamp": "9999"},
            "OPERLOG",
            op_rows=[],
        )

        stored = frappe.db.get_value("TimeBridge Machine", machine, "adms_op_stamp")
        self.assertTrue(stored)
        self.assertNotIn(stored, ("9999", "", None))

    def test_record_operlog_heartbeat_uses_unix_stamp(self):
        machine = self._make_machine("STAMP-011")

        stamps.record_operlog_stamp(
            machine,
            {"table": "OPERLOG", "OpStamp": "9999"},
            "OPERLOG",
            op_rows=[],
            heartbeat=True,
        )

        stored = frappe.db.get_value("TimeBridge Machine", machine, "adms_op_stamp")
        self.assertTrue(stored.isdigit())

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
