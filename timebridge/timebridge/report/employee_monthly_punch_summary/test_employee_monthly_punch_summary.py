# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for Employee Monthly Punch Summary report."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_datetime, get_last_day, now_datetime

from timebridge.timebridge.report.employee_monthly_punch_summary.employee_monthly_punch_summary import (
	execute,
)


class TestEmployeeMonthlyPunchSummary(FrappeTestCase):

	MACHINE_ID = "TB-EMPS-1"

	def setUp(self):
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		machine = frappe.db.get_value("TimeBridge Machine", {"machine_id": self.MACHINE_ID})
		if machine:
			for mu in frappe.get_all(
				"TimeBridge Machine User",
				filters={"machine": machine},
				pluck="name",
			):
				frappe.delete_doc("TimeBridge Machine User", mu, force=True)
			for pl in frappe.get_all(
				"TimeBridge Punch Log",
				filters={"machine": machine},
				pluck="name",
			):
				frappe.delete_doc("TimeBridge Punch Log", pl, force=True)
			frappe.delete_doc("TimeBridge Machine", machine, force=True)
		frappe.db.commit()

	def _make_machine(self):
		return frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": self.MACHINE_ID,
				"machine_name": "Employee monthly punch summary test",
				"device_brand": "ZKTeco",
				"ip_address": "192.168.99.61",
				"port": 4370,
				"sdk_type": "PyZK",
			}
		).insert(ignore_permissions=True)

	def _make_machine_user(self, machine, user_id, user_name):
		return frappe.get_doc(
			{
				"doctype": "TimeBridge Machine User",
				"machine": machine,
				"user_id": user_id,
				"user_name": user_name,
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

	def test_execute_requires_filters(self):
		columns, rows = execute({})
		self.assertEqual(rows, [])
		self.assertTrue(columns)
		self.assertFalse(any(col["fieldname"] == "user_name" for col in columns))

	def test_execute_returns_month_rows(self):
		machine = self._make_machine()
		machine_user = self._make_machine_user(machine.name, "9", "Report Monthly User")
		punch_day = now_datetime().replace(day=12, hour=8, minute=0, second=0, microsecond=0)
		month_start = punch_day.replace(day=1)

		self._make_punch(machine.name, "9", punch_day)

		columns, rows = execute(
			{"machine_user": machine_user.name, "month": month_start.date()}
		)
		self.assertFalse(any(col["fieldname"] == "user_name" for col in columns))
		self.assertEqual(len(rows), get_last_day(month_start).day)
		punch_rows = [row for row in rows if row["punches"]]
		self.assertEqual(len(punch_rows), 1)
		self.assertEqual(punch_rows[0]["punches"], 1)
