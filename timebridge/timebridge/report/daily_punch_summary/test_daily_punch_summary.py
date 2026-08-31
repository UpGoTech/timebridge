# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for Daily Punch Summary report."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime

from timebridge.timebridge.report.daily_punch_summary.daily_punch_summary import execute


class TestDailyPunchSummary(FrappeTestCase):

	MACHINE_ID = "TB-DPS-1"

	def setUp(self):
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		name = frappe.db.get_value("TimeBridge Machine", {"machine_id": self.MACHINE_ID})
		if name:
			for pl in frappe.get_all(
				"TimeBridge Punch Log",
				filters={"machine": name},
				pluck="name",
			):
				frappe.delete_doc("TimeBridge Punch Log", pl, force=True)
			frappe.delete_doc("TimeBridge Machine", name, force=True)
		frappe.db.commit()

	def _make_machine(self):
		return frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": self.MACHINE_ID,
				"machine_name": "Daily punch summary test",
				"device_brand": "ZKTeco",
				"ip_address": "192.168.99.60",
				"port": 4370,
				"sdk_type": "PyZK",
			}
		).insert(ignore_permissions=True)

	def _make_punch(self, machine, device_user_id, timestamp, punch_direction="In"):
		ts = get_datetime(timestamp)
		punch_key = f"{machine}::{device_user_id}::{ts.isoformat()}::{punch_direction}"
		return frappe.get_doc(
			{
				"doctype": "TimeBridge Punch Log",
				"machine": machine,
				"device_user_id": device_user_id,
				"timestamp": ts,
				"punch_direction": punch_direction,
				"source": "PyZK Pull",
				"punch_key": punch_key,
			}
		).insert(ignore_permissions=True)

	def test_execute_requires_date(self):
		columns, rows = execute({})
		self.assertEqual(rows, [])
		self.assertTrue(columns)

	def test_execute_filters_by_date_and_machine(self):
		machine = self._make_machine()
		punch_day = now_datetime().replace(hour=8, minute=0, second=0)
		other_day = add_to_date(punch_day, days=-1, as_datetime=True)

		self._make_punch(machine.name, "7", punch_day)
		self._make_punch(machine.name, "8", other_day)

		all_columns, all_rows = execute({"date": getdate(punch_day)})
		self.assertTrue(any(col["fieldname"] == "machine" for col in all_columns))
		test_rows = [row for row in all_rows if row["machine"] == machine.name]
		self.assertEqual(len(test_rows), 1)
		self.assertEqual(test_rows[0]["device_user_id"], "7")

		machine_columns, machine_rows = execute(
			{"date": getdate(punch_day), "machine": machine.name}
		)
		self.assertFalse(any(col["fieldname"] == "machine" for col in machine_columns))
		self.assertEqual(len(machine_rows), 1)
