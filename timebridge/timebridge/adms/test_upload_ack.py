# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""
Tests for how a data upload is acknowledged.

This is the protocol detail that had a real device re-sending the same 128
punches hundreds of times: the Attendance PUSH spec answers a POST with
"OK: <records processed>", and a bare "OK" reads as a failure, so the firmware
keeps the batch and pushes it again on every cycle.

The handlers commit, so frappe.db.commit is patched out to keep each test inside
the transaction the test case rolls back.
"""

from unittest.mock import patch

import frappe

from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms import api

ATTLOG_ARGS = {"table": "ATTLOG", "Stamp": "9999"}
OPERLOG_ARGS = {"table": "OPERLOG", "OpStamp": "9999"}


class TestADMSUploadAck(FrappeTestCase):

    def test_ack_names_the_record_count(self):
        self.assertEqual(api.ack(9), "OK: 9")
        self.assertEqual(api.ack(0), "OK: 0")

    def test_attlog_ack_counts_every_record(self):
        machine, serial = self._make_machine("ACK-001")
        body = self._punches(serial_offset=0, count=3)

        reply = self._post(serial, ATTLOG_ARGS, body)

        self.assertEqual(reply, "OK: 3")

    def test_attlog_ack_counts_duplicates_not_just_new_rows(self):
        """A re-sent batch was still processed. "OK: 0" would restart the loop."""

        machine, serial = self._make_machine("ACK-002")
        body = self._punches(serial_offset=10, count=4)

        first = self._post(serial, ATTLOG_ARGS, body)
        second = self._post(serial, ATTLOG_ARGS, body)

        self.assertEqual(first, "OK: 4")
        self.assertEqual(second, "OK: 4")

    def test_attlog_ack_counts_unparseable_lines(self):
        """An unreadable line can never be parsed, so it must not be retried."""

        machine, serial = self._make_machine("ACK-003")
        body = self._punches(serial_offset=20, count=1) + "garbage\n"

        self.assertEqual(self._post(serial, ATTLOG_ARGS, body), "OK: 2")

    def test_operlog_of_operation_rows_only_is_acknowledged(self):
        machine, serial = self._make_machine("ACK-004")
        body = (
            "OPLOG 4\t1\t2026-08-31 09:19:01\t0\t0\t0\t\n"
            "OPLOG 6\t1\t2026-08-31 09:19:02\t0\t0\t0\t\n"
        )

        self.assertEqual(self._post(serial, OPERLOG_ARGS, body), "OK: 2")

    def test_operlog_of_operation_rows_only_records_the_stamp(self):
        """Leaving this inside "if records" is what made the device loop."""

        machine, serial = self._make_machine("ACK-005")
        args = dict(OPERLOG_ARGS, OpStamp="4455")
        body = "OPLOG 4\t1\t2026-08-31 09:19:01\t0\t0\t0\t\n"

        self._post(serial, args, body)

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_op_stamp"),
            "4455",
        )

    def test_empty_operlog_advances_operlog_stamp(self):
        """Placeholder Stamp=9999 + empty body must still move OPERLOGStamp."""

        machine, serial = self._make_machine("ACK-009")

        self.assertEqual(self._post(serial, OPERLOG_ARGS, ""), "OK: 1")

        stored = frappe.db.get_value("TimeBridge Machine", machine, "adms_op_stamp")
        self.assertTrue(stored)
        self.assertNotEqual(stored, "9999")

    def test_empty_operlog_skips_sync_and_machine_log(self):
        """Empty heartbeats must not flood Sync Log / Machine Log every 200 ms."""

        machine, serial = self._make_machine("ACK-012")

        self.assertEqual(self._post(serial, OPERLOG_ARGS, ""), "OK: 1")

        self.assertFalse(
            frappe.db.exists(
                "TimeBridge Machine Log",
                {"machine": machine, "event": "Upload"},
            )
        )
        self.assertFalse(
            frappe.db.exists(
                "TimeBridge Sync Log",
                {"machine": machine, "sync_type": "Users"},
            )
        )

    def test_operlog_op_rows_fallback_stamp_when_placeholder(self):
        machine, serial = self._make_machine("ACK-010")
        body = "OPLOG 4\t1\t2026-08-31 09:19:01\t0\t0\t0\t\n"

        self._post(serial, OPERLOG_ARGS, body)

        self.assertEqual(
            frappe.db.get_value("TimeBridge Machine", machine, "adms_op_stamp"),
            "2026-08-31 09:19:01",
        )

    def test_operlog_garbage_body_is_heartbeat(self):
        """Unparseable body lines must not bypass the empty-heartbeat path."""

        machine, serial = self._make_machine("ACK-013")
        body = "OK\n"

        self.assertEqual(self._post(serial, OPERLOG_ARGS, body), "OK: 1")

        self.assertFalse(
            frappe.db.exists(
                "TimeBridge Machine Log",
                {"machine": machine, "event": "Upload"},
            )
        )

    def test_operlog_with_op_rows_is_logged(self):
        """OPERLOG with OPLOG rows leaves Machine Log and Sync Log rows."""

        machine, serial = self._make_machine("ACK-008")
        body = "OPLOG 4\t1\t2026-08-31 09:19:01\t0\t0\t0\t\n"

        self.assertEqual(self._post(serial, OPERLOG_ARGS, body), "OK: 1")

        self.assertTrue(
            frappe.db.exists(
                "TimeBridge Machine Log",
                {"machine": machine, "event": "Upload"},
            )
        )
        self.assertTrue(
            frappe.db.exists(
                "TimeBridge Sync Log",
                {"machine": machine, "sync_type": "Users", "status": "Success"},
            )
        )

    def test_duplicate_attlog_writes_sync_log(self):
        """Re-sent batches still appear in Sync Log — ingest ran, duplicates count."""

        machine, serial = self._make_machine("ACK-011")
        body = self._punches(serial_offset=30, count=2)

        self._post(serial, ATTLOG_ARGS, body)
        self._post(serial, ATTLOG_ARGS, body)

        sync_logs = frappe.get_all(
            "TimeBridge Sync Log",
            filters={"machine": machine, "sync_type": "Attendance"},
            fields=["records_fetched", "records_created", "records_skipped"],
            order_by="creation asc",
        )
        self.assertEqual(len(sync_logs), 2)
        self.assertEqual(sync_logs[0]["records_created"], 2)
        self.assertEqual(sync_logs[1]["records_created"], 0)
        self.assertEqual(sync_logs[1]["records_skipped"], 2)

    def test_operlog_with_users_is_acknowledged(self):
        machine, serial = self._make_machine("ACK-006")
        body = "USER PIN=1\tName=Asha\tPri=0\nUSER PIN=2\tName=Manali\tPri=0\n"

        self.assertEqual(self._post(serial, OPERLOG_ARGS, body), "OK: 2")

    def test_handshake_carries_the_transmit_cycle_options(self):
        machine, serial = self._make_machine("ACK-007")
        reply = api.build_handshake(serial, machine)

        self.assertIn("TransInterval=1", reply)
        self.assertIn("TransTimes=", reply)
        self.assertIn("TimeZone=", reply)

    def test_transflag_enables_user_enrolment_and_change(self):
        """
        Attendance PUSH digits: 5 is EnrollUser and 7 is ChgUser. The Security
        PUSH ordering put them at 4 and 5, and following it switched both off.
        """

        for flag in (api.TRANSFLAG_PUNCHES_ONLY, api.TRANSFLAG_WITH_PHOTOS):
            self.assertEqual(flag[0], "1", "AttLog")
            self.assertEqual(flag[1], "0", "OpLog audit channel disabled")
            self.assertEqual(flag[2], "1", "AttPhoto")
            self.assertEqual(flag[4], "1", "EnrollUser")
            self.assertEqual(flag[6], "1", "ChgUser")

        self.assertEqual(api.TRANSFLAG_WITH_PHOTOS[8], "1", "FACE")
        self.assertEqual(api.TRANSFLAG_WITH_PHOTOS[9], "1", "UserPic")
        self.assertEqual(api.TRANSFLAG_PUNCHES_ONLY[8:], "00")

    def test_timezone_option_uses_minutes_for_half_hour_offsets(self):
        with patch("frappe.utils.get_system_timezone", return_value="Asia/Kolkata"):
            self.assertEqual(api.server_timezone_option(), "330")

        with patch("frappe.utils.get_system_timezone", return_value="UTC"):
            self.assertEqual(api.server_timezone_option(), "0")

    def _post(self, serial, args, body):
        with patch.object(frappe.db, "commit"):
            return api.handle_cdata(serial, dict(args, SN=serial), body, "POST")

    def _punches(self, serial_offset, count):
        return "".join(
            f"5\t2026-08-31 10:{serial_offset + i:02d}:00\t0\t15\t0\t0\n"
            for i in range(count)
        )

    def _make_machine(self, serial):
        doc = frappe.get_doc(
            {
                "doctype": "TimeBridge Machine",
                "machine_id": serial,
                "machine_name": serial,
                "device_brand": "ZKTeco",
                "serial_number": serial,
                "ip_address": "10.0.0.2",
                "port": 4370,
                "sdk_type": "ADMS",
            }
        )
        doc.insert(ignore_permissions=True)
        return doc.name, serial
