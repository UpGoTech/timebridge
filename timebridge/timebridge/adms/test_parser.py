# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""
Tests for ADMS payload parsing.

These are pure-function tests: no device, no database. They pin down the
awkward parts of the protocol — malformed lines, missing trailing fields,
firmware variation in casing and field order.
"""

from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms.parser import (
    parse_attlog,
    parse_table_name,
    parse_userinfo,
)


class TestADMSParser(FrappeTestCase):

    def test_attlog_basic(self):
        body = "1\t2026-07-30 10:05:12\t0\t1\t0\t0\n2\t2026-07-30 19:02:44\t1\t15\t0\t0"
        records, skipped = parse_attlog(body)

        self.assertEqual(len(records), 2)
        self.assertEqual(skipped, [])

        self.assertEqual(records[0]["device_user_id"], "1")
        self.assertEqual(records[0]["timestamp"], "2026-07-30 10:05:12")
        self.assertEqual(records[0]["punch_direction"], "In")
        self.assertEqual(records[0]["verify_mode"], "Fingerprint")
        self.assertEqual(records[0]["device_status"], "0")

        self.assertEqual(records[1]["punch_direction"], "Out")
        self.assertEqual(records[1]["verify_mode"], "Face")

    def test_attlog_alternate_direction_codes(self):
        # 4 and 5 are entry/exit on some readers
        records, _ = parse_attlog("7\t2026-07-30 10:00:00\t4\n8\t2026-07-30 18:00:00\t5")
        self.assertEqual([r["punch_direction"] for r in records], ["In", "Out"])

    def test_attlog_unknown_status_is_not_guessed(self):
        records, _ = parse_attlog("9\t2026-07-30 10:00:00\t77")
        self.assertEqual(records[0]["punch_direction"], "Unknown")
        self.assertEqual(records[0]["device_status"], "77")

    def test_attlog_minimal_line_without_trailing_fields(self):
        records, skipped = parse_attlog("3\t2026-07-30 11:00:00")
        self.assertEqual(len(records), 1)
        self.assertEqual(skipped, [])
        self.assertEqual(records[0]["punch_direction"], "Unknown")
        self.assertIsNone(records[0]["verify_mode"])

    def test_attlog_malformed_lines_do_not_abort_batch(self):
        body = (
            "1\t2026-07-30 10:00:00\t0\n"
            "garbage-with-no-tabs\n"
            "\t2026-07-30 10:01:00\t0\n"
            "2\t\t0\n"
            "\n"
            "4\t2026-07-30 10:02:00\t1\n"
        )
        records, skipped = parse_attlog(body)

        self.assertEqual([r["device_user_id"] for r in records], ["1", "4"])
        self.assertEqual(len(skipped), 3)

    def test_attlog_empty_body(self):
        self.assertEqual(parse_attlog(""), ([], []))
        self.assertEqual(parse_attlog(None), ([], []))

    def test_userinfo_key_value_order_independent(self):
        body = "PIN=5\tName=Asha\tPri=0\tCard=99\tPasswd=\tGrp=1"
        records, skipped = parse_userinfo(body)

        self.assertEqual(skipped, [])
        self.assertEqual(records[0]["user_id"], "5")
        self.assertEqual(records[0]["user_name"], "Asha")
        self.assertEqual(records[0]["card_number"], "99")
        self.assertEqual(records[0]["privilege"], "User")

    def test_userinfo_reordered_and_prefixed(self):
        body = "USER Card=12\tPri=14\tPIN=6\tName=Ravi"
        records, _ = parse_userinfo(body)

        self.assertEqual(records[0]["user_id"], "6")
        self.assertEqual(records[0]["user_name"], "Ravi")
        self.assertEqual(records[0]["privilege"], "Admin")

    def test_userinfo_without_pin_is_skipped(self):
        records, skipped = parse_userinfo("Name=NoPin\tPri=0")
        self.assertEqual(records, [])
        self.assertEqual(len(skipped), 1)

    def test_userinfo_missing_name_gets_placeholder(self):
        records, _ = parse_userinfo("PIN=42\tPri=0")
        self.assertEqual(records[0]["user_name"], "User 42")
        self.assertIsNone(records[0]["card_number"])

    def test_table_name_normalisation(self):
        self.assertEqual(parse_table_name("ATTLOG"), "ATTLOG")
        self.assertEqual(parse_table_name("attlog"), "ATTLOG")
        self.assertEqual(parse_table_name(" ATTLOG Stamp=9999 "), "ATTLOG")
        self.assertIsNone(parse_table_name(""))
        self.assertIsNone(parse_table_name(None))
