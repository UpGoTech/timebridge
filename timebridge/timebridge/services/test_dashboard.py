# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for workspace dashboard distinct-user counting."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, getdate, now_datetime, today

from timebridge.timebridge.services.dashboard import (
	DAILY_PUNCH_SUMMARY_REPORT,
	build_daily_punch_summary_rows,
	get_active_users_per_day_chart,
	get_users_punched_today,
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

	def test_users_punched_today_routes_to_daily_punch_summary(self):
		result = get_users_punched_today()
		self.assertEqual(result["route"], ["query-report", DAILY_PUNCH_SUMMARY_REPORT])
		self.assertEqual(getdate(result["route_options"]["date"]), getdate(today()))

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
