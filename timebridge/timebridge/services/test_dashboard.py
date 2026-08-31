# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for workspace dashboard distinct-user counting."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, get_last_day, getdate, now_datetime, today
from datetime import date

from timebridge.timebridge.services.dashboard import (
	build_daily_punch_summary_rows,
	build_employee_monthly_punch_summary_rows,
	get_active_users_per_day_chart,
	get_daily_punch_summary_list,
	get_employee_monthly_punch_summary_list,
	get_users_punched_today,
	_format_monthly_summary_date,
)


class TestDashboard(FrappeTestCase):

	MACHINE_A = "TB-DASH-A"
	MACHINE_B = "TB-DASH-B"

	def setUp(self):
		self._cleanup()

	def tearDown(self):
		self._cleanup()

	def _cleanup(self):
		for machine_id in (self.MACHINE_A, self.MACHINE_B):
			name = frappe.db.get_value("TimeBridge Machine", {"machine_id": machine_id})
			if name:
				for pl in frappe.get_all(
					"TimeBridge Punch Log",
					filters={"machine": name},
					pluck="name",
				):
					frappe.delete_doc("TimeBridge Punch Log", pl, force=True)
				frappe.delete_doc("TimeBridge Machine", name, force=True)
		frappe.db.commit()

	def _make_machine(self, machine_id):
		return frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": machine_id,
				"machine_name": f"Dashboard test {machine_id}",
				"device_brand": "ZKTeco",
				"ip_address": "192.168.99.50",
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

	def test_users_punched_today_counts_distinct_machine_user_pairs(self):
		machine_a = self._make_machine(self.MACHINE_A)
		machine_b = self._make_machine(self.MACHINE_B)
		punch_day = now_datetime().replace(hour=9, minute=0, second=0)

		before = get_users_punched_today()["value"]

		self._make_punch(machine_a.name, "1", punch_day)
		self._make_punch(machine_a.name, "1", punch_day.replace(hour=18))
		self._make_punch(machine_a.name, "2", punch_day)
		self._make_punch(machine_b.name, "1", punch_day)

		after = get_users_punched_today()["value"]
		self.assertEqual(after - before, 3)

	def test_same_device_user_id_on_two_machines_counts_as_two(self):
		machine_a = self._make_machine(self.MACHINE_A)
		machine_b = self._make_machine(self.MACHINE_B)
		punch_day = now_datetime().replace(hour=10, minute=0, second=0)

		before = get_users_punched_today()["value"]

		self._make_punch(machine_a.name, "4", punch_day)
		self._make_punch(machine_b.name, "4", punch_day)

		after = get_users_punched_today()["value"]
		self.assertEqual(after - before, 2)

	def test_users_punched_today_opens_daily_punch_summary(self):
		result = get_users_punched_today()
		self.assertIn("value", result)
		self.assertEqual(result["route"], "daily-punch-summary")
		self.assertEqual(result["route_options"]["date"], str(getdate(today())))

	def test_daily_punch_summary_list_api(self):
		machine_a = self._make_machine(self.MACHINE_A)
		punch_day = now_datetime().replace(hour=9, minute=0, second=0)
		self._make_punch(machine_a.name, "1", punch_day)

		rows = [
			row
			for row in get_daily_punch_summary_list(getdate(punch_day), machine_a.name)
			if row["machine"] == machine_a.name
		]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["punches"], 1)
		self.assertTrue(rows[0]["punched_in_display"])

	def test_daily_punch_summary_rows(self):
		machine_a = self._make_machine(self.MACHINE_A)
		machine_b = self._make_machine(self.MACHINE_B)
		punch_day = now_datetime().replace(hour=9, minute=0, second=0)

		self._make_punch(machine_a.name, "1", punch_day)
		self._make_punch(
			machine_a.name,
			"1",
			punch_day.replace(hour=18, minute=30),
			punch_direction="Out",
		)
		self._make_punch(machine_a.name, "2", punch_day.replace(hour=10, minute=0))
		self._make_punch(machine_b.name, "1", punch_day.replace(hour=11, minute=0))

		rows = [
			row
			for row in build_daily_punch_summary_rows(getdate(punch_day))
			if row["machine"] in (machine_a.name, machine_b.name)
		]
		self.assertEqual(len(rows), 3)

		by_device = {(r["machine"], r["device_user_id"]): r for r in rows}
		self.assertEqual(by_device[(machine_a.name, "1")]["punches"], 2)
		self.assertEqual(
			by_device[(machine_a.name, "1")]["punched_in"].strftime("%H:%M:%S"),
			"09:00:00",
		)
		self.assertEqual(
			by_device[(machine_a.name, "1")]["punched_out"].strftime("%H:%M:%S"),
			"18:30:00",
		)
		self.assertEqual(by_device[(machine_a.name, "1")]["working_hours"], 9.5)
		self.assertEqual(by_device[(machine_a.name, "1")]["working_hours_display"], "9:30")
		self.assertEqual(by_device[(machine_a.name, "2")]["working_hours_display"], "")
		self.assertEqual(rows[0]["machine"], machine_b.name)

	def test_active_users_per_day_chart(self):
		machine = self._make_machine(self.MACHINE_A)
		punch_day = now_datetime().replace(hour=8, minute=0, second=0)
		yesterday = add_to_date(punch_day, days=-1, as_datetime=True)

		self._make_punch(machine.name, "10", punch_day)
		self._make_punch(machine.name, "10", punch_day.replace(hour=17))
		self._make_punch(machine.name, "11", punch_day)
		self._make_punch(machine.name, "20", yesterday)

		if not frappe.db.exists("Dashboard Chart", "TimeBridge Active Users Per Day"):
			frappe.get_doc(
				{
					"doctype": "Dashboard Chart",
					"chart_name": "TimeBridge Active Users Per Day",
					"name": "TimeBridge Active Users Per Day",
					"chart_type": "Custom",
					"source": "TimeBridge Active Users Per Day",
					"timeseries": 1,
					"timespan": "Last Month",
					"time_interval": "Daily",
					"type": "Line",
					"filters_json": "[]",
					"module": "TimeBridge",
					"is_public": 1,
					"is_standard": 1,
				}
			).insert(ignore_permissions=True)

		chart = get_active_users_per_day_chart(
			chart_name="TimeBridge Active Users Per Day",
			timespan="Last Week",
			time_interval="Daily",
		)
		values = chart["datasets"][0]["values"]
		self.assertGreaterEqual(sum(values), 3)

	def test_employee_monthly_punch_summary_rows(self):
		machine_a = self._make_machine(self.MACHINE_A)
		machine_b = self._make_machine(self.MACHINE_B)
		machine_user = self._make_machine_user(machine_a.name, "42", "Monthly Test User")
		punch_day = now_datetime().replace(day=15, hour=9, minute=0, second=0, microsecond=0)
		other_day = punch_day.replace(day=16, hour=10, minute=0)
		month_start = punch_day.replace(day=1)

		self._make_punch(machine_a.name, "42", punch_day)
		self._make_punch(
			machine_a.name,
			"42",
			punch_day.replace(hour=18, minute=30),
			punch_direction="Out",
		)
		self._make_punch(machine_b.name, "42", punch_day.replace(hour=8, minute=45))
		self._make_punch(machine_a.name, "42", other_day)

		rows = build_employee_monthly_punch_summary_rows(machine_user.name, month_start)
		self.assertEqual(len(rows), get_last_day(month_start).day)

		day_15 = next(row for row in rows if getdate(row["date"]).day == 15)
		self.assertEqual(day_15["punches"], 3)
		self.assertEqual(day_15["working_hours"], 9.75)
		self.assertEqual(day_15["working_hours_display"], "9:45")
		self.assertEqual(day_15["punched_in_display"], "08:45:00")

		day_16 = next(row for row in rows if getdate(row["date"]).day == 16)
		self.assertEqual(day_16["punches"], 1)
		self.assertEqual(day_16["working_hours_display"], "")

		blank_day = next(row for row in rows if getdate(row["date"]).day == 1)
		self.assertEqual(blank_day["punches"], 0)
		self.assertEqual(blank_day["punched_in_display"], "")

	def test_employee_monthly_punch_summary_list_api(self):
		machine = self._make_machine(self.MACHINE_A)
		machine_user = self._make_machine_user(machine.name, "55", "API Monthly User")
		punch_day = now_datetime().replace(day=10, hour=9, minute=0, second=0, microsecond=0)

		self._make_punch(machine.name, "55", punch_day)

		rows = get_employee_monthly_punch_summary_list(
			machine_user.name, punch_day.replace(day=1)
		)
		self.assertEqual(len(rows), get_last_day(punch_day).day)
		with_punches = [row for row in rows if row["punches"]]
		self.assertEqual(len(with_punches), 1)
		self.assertEqual(with_punches[0]["punches"], 1)

	def test_format_monthly_summary_date(self):
		self.assertEqual(_format_monthly_summary_date(date(2026, 8, 5)), "05-Aug-2026 (Wed)")

