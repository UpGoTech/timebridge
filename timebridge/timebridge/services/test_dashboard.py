# Copyright (c) 2026, UPGO and Contributors
# See license.txt

"""Tests for workspace dashboard distinct-user counting."""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, get_datetime, get_last_day, getdate, now_datetime, today
from datetime import date

from timebridge.timebridge.services.dashboard import (
	build_daily_punch_summary_html,
	build_daily_punch_summary_rows,
	build_employee_monthly_punch_summary_html,
	build_employee_monthly_punch_summary_rows,
	download_daily_punch_summary_pdf,
	ensure_default_expected_working_hours,
	get_active_users_per_day_chart,
	get_daily_punch_summary_list,
	get_employee_monthly_punch_summary_list,
	get_users_punched_today,
	resolve_expected_hours,
	_format_chart_day_label,
	_format_monthly_summary_date,
	_summarize_day_punches,
	DEFAULT_EXPECTED_WORKING_HOURS,
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
				for mu in frappe.get_all(
					"TimeBridge Machine User",
					filters={"machine": name},
					pluck="name",
				):
					frappe.delete_doc("TimeBridge Machine User", mu, force=True)
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

	def _make_machine_user(self, machine, user_id, user_name, expected_working_hours=None):
		doc = {
			"doctype": "TimeBridge Machine User",
			"machine": machine,
			"user_id": user_id,
			"user_name": user_name,
		}
		if expected_working_hours is not None:
			doc["expected_working_hours"] = expected_working_hours
		return frappe.get_doc(doc).insert(ignore_permissions=True)

	def _make_punch(self, machine, device_user_id, timestamp, punch_direction="In", machine_user=None):
		ts = get_datetime(timestamp)
		punch_key = f"{machine}::{device_user_id}::{ts.isoformat()}::{punch_direction}"
		doc = {
			"doctype": "TimeBridge Punch Log",
			"machine": machine,
			"device_user_id": device_user_id,
			"timestamp": ts,
			"punch_direction": punch_direction,
			"source": "PyZK Pull",
			"punch_key": punch_key,
		}
		if machine_user:
			doc["machine_user"] = machine_user
		return frappe.get_doc(doc).insert(ignore_permissions=True)

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
					"timespan": "Last Week",
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
		self.assertIn(_format_chart_day_label(punch_day), chart["labels"])

	def test_format_chart_day_label(self):
		self.assertEqual(_format_chart_day_label(date(2026, 8, 30)), "30-Aug-26 (Sun)")
		self.assertEqual(_format_chart_day_label(date(2026, 8, 5)), "5-Aug-26 (Wed)")

	def test_format_chart_axis_label_does_not_swap_day_month(self):
		from timebridge.timebridge.services.dashboard import _format_chart_axis_label

		# Regression: get_period("Daily") is dd-mm-yy; re-parsing that as a date
		# turned 6 Sep into 9 Jun and 1 Sep into 9 Jan.
		self.assertEqual(
			_format_chart_axis_label(date(2026, 9, 6), "Daily"),
			"6-Sep-26 (Sun)",
		)
		self.assertEqual(
			_format_chart_axis_label(date(2026, 9, 1), "Daily"),
			"1-Sep-26 (Tue)",
		)
		self.assertEqual(
			_format_chart_axis_label(date(2026, 5, 9), "Weekly"),
			"9-May-26 (Sat)",
		)
		self.assertEqual(
			_format_chart_axis_label(date(2026, 2, 28), "Monthly"),
			"Feb 2026",
		)

	def test_active_users_chart_labels_match_real_dates(self):
		from frappe.utils.dateutils import get_period

		# Guard the old double-get_period path: period string must not be the input.
		sep6 = date(2026, 9, 6)
		period = get_period(sep6, "Daily")
		self.assertEqual(period, "06-09-26")
		from timebridge.timebridge.services.dashboard import _format_chart_axis_label

		self.assertNotEqual(
			_format_chart_axis_label(sep6, "Daily"),
			_format_chart_axis_label(getdate(period), "Daily"),
		)
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
		self.assertEqual(blank_day["row_status"], "absent")

	def test_employee_monthly_punch_summary_list_api(self):
		machine = self._make_machine(self.MACHINE_A)
		machine_user = self._make_machine_user(machine.name, "55", "API Monthly User")
		punch_day = now_datetime().replace(day=10, hour=9, minute=0, second=0, microsecond=0)

		self._make_punch(machine.name, "55", punch_day)

		result = get_employee_monthly_punch_summary_list(
			machine_user.name, punch_day.replace(day=1)
		)
		self.assertEqual(len(result["rows"]), get_last_day(punch_day).day)
		self.assertEqual(result["user_id"], "55")
		self.assertEqual(result["user_name"], "API Monthly User")
		with_punches = [row for row in result["rows"] if row["punches"]]
		self.assertEqual(len(with_punches), 1)
		self.assertEqual(with_punches[0]["punches"], 1)
		self.assertEqual(with_punches[0]["row_status"], "no_out")

	def test_format_monthly_summary_date(self):
		self.assertEqual(_format_monthly_summary_date(date(2026, 8, 5)), "05-Aug-2026 (Wed)")


	def test_summarize_first_last_ignores_direction(self):
		"""First timestamp is In even when tagged Out; last is Out even when tagged In."""
		punches = [
			frappe._dict(timestamp=get_datetime("2026-09-01 08:00:00"), punch_direction="Out"),
			frappe._dict(timestamp=get_datetime("2026-09-01 12:00:00"), punch_direction="In"),
			frappe._dict(timestamp=get_datetime("2026-09-01 17:00:00"), punch_direction="In"),
		]
		summary = _summarize_day_punches(punches, expected_hours=9)
		self.assertEqual(summary["punched_in_display"], "08:00:00")
		self.assertEqual(summary["punched_out_display"], "17:00:00")
		self.assertEqual(summary["working_hours"], 9.0)
		self.assertEqual(summary["punches"], 3)
		self.assertEqual(len(summary["punch_details"]), 3)
		self.assertEqual(summary["punch_details"][0]["direction"], "Out")
		self.assertIn("date_display", summary["punch_details"][0])
		self.assertEqual(summary["row_status"], "ok")

	def test_summarize_one_punch_is_no_out(self):
		punches = [
			frappe._dict(timestamp=get_datetime("2026-09-01 09:00:00"), punch_direction="In"),
		]
		summary = _summarize_day_punches(punches, expected_hours=9)
		self.assertTrue(summary["punched_in_display"])
		self.assertEqual(summary["punched_out_display"], "")
		self.assertIsNone(summary["working_hours"])
		self.assertEqual(summary["row_status"], "no_out")

	def test_summarize_short_day_status(self):
		punches = [
			frappe._dict(timestamp=get_datetime("2026-09-01 09:00:00"), punch_direction="In"),
			frappe._dict(timestamp=get_datetime("2026-09-01 16:00:00"), punch_direction="Out"),
		]
		summary = _summarize_day_punches(punches, expected_hours=9)
		self.assertEqual(summary["working_hours"], 7.0)
		self.assertEqual(summary["row_status"], "short")

	def test_resolve_expected_hours_machine_user_then_settings(self):
		ensure_default_expected_working_hours()
		machine = self._make_machine(self.MACHINE_A)
		mu_blank = self._make_machine_user(machine.name, "70", "Blank Hours")
		mu_set = self._make_machine_user(
			machine.name, "71", "Eight Hours", expected_working_hours=8
		)

		self.assertEqual(resolve_expected_hours(mu_set.name), 8.0)
		fallback = resolve_expected_hours(mu_blank.name)
		self.assertEqual(fallback, DEFAULT_EXPECTED_WORKING_HOURS)
		self.assertEqual(resolve_expected_hours(None), DEFAULT_EXPECTED_WORKING_HOURS)

	def test_monthly_short_and_punch_details(self):
		ensure_default_expected_working_hours()
		machine = self._make_machine(self.MACHINE_A)
		machine_user = self._make_machine_user(
			machine.name, "80", "Short Day User", expected_working_hours=10
		)
		day = now_datetime().replace(day=12, hour=9, minute=0, second=0, microsecond=0)
		self._make_punch(machine.name, "80", day, punch_direction="Out")
		self._make_punch(
			machine.name, "80", day.replace(hour=12, minute=0), punch_direction="In"
		)
		self._make_punch(
			machine.name, "80", day.replace(hour=17, minute=0), punch_direction="In"
		)

		result = get_employee_monthly_punch_summary_list(
			machine_user.name, day.replace(day=1)
		)
		self.assertEqual(result["expected_working_hours"], 10.0)
		day_12 = next(row for row in result["rows"] if getdate(row["date"]).day == 12)
		self.assertEqual(day_12["punches"], 3)
		self.assertEqual(day_12["punched_in_display"], "09:00:00")
		self.assertEqual(day_12["punched_out_display"], "17:00:00")
		self.assertEqual(day_12["working_hours"], 8.0)
		self.assertEqual(day_12["row_status"], "short")
		self.assertEqual(len(day_12["punch_details"]), 3)
		self.assertTrue(all(detail.get("name") for detail in day_12["punch_details"]))

	def test_daily_uses_machine_user_expected_hours(self):
		ensure_default_expected_working_hours()
		machine = self._make_machine(self.MACHINE_A)
		mu = self._make_machine_user(
			machine.name, "81", "Daily Short", expected_working_hours=10
		)
		day = now_datetime().replace(hour=9, minute=0, second=0, microsecond=0)
		self._make_punch(
			machine.name, "81", day, machine_user=mu.name
		)
		self._make_punch(
			machine.name,
			"81",
			day.replace(hour=16, minute=0),
			punch_direction="Out",
			machine_user=mu.name,
		)

		rows = [
			row
			for row in build_daily_punch_summary_rows(getdate(day), machine.name)
			if row["device_user_id"] == "81"
		]
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0]["expected_working_hours"], 10.0)
		self.assertEqual(rows[0]["row_status"], "short")

	def test_punch_summary_print_html(self):
		machine = self._make_machine(self.MACHINE_A)
		mu = self._make_machine_user(machine.name, "82", "Print User")
		day = now_datetime().replace(day=5, hour=9, minute=0, second=0, microsecond=0)
		self._make_punch(machine.name, "82", day)
		self._make_punch(
			machine.name, "82", day.replace(hour=18), punch_direction="Out"
		)

		monthly_html = build_employee_monthly_punch_summary_html(
			mu.name, day.replace(day=1), grayscale=False
		)
		self.assertIn("Employee Monthly Punch Summary", monthly_html)
		self.assertIn("Below expected hours", monthly_html)
		self.assertIn("A4 portrait", monthly_html)

		daily_html = build_daily_punch_summary_html(
			getdate(day), machine.name, grayscale=True
		)
		self.assertIn("Daily Punch Summary", daily_html)
		self.assertIn("#777777", daily_html)

	def test_daily_pdf_download_smoke(self):
		machine = self._make_machine(self.MACHINE_A)
		day = now_datetime().replace(hour=9, minute=0, second=0, microsecond=0)
		self._make_punch(machine.name, "83", day)
		self._make_punch(
			machine.name, "83", day.replace(hour=18), punch_direction="Out"
		)
		try:
			download_daily_punch_summary_pdf(getdate(day), machine.name)
		except Exception as exc:
			# wkhtmltopdf may be absent in CI/dev containers
			if "wkhtmltopdf" in str(exc).lower() or "Failed to load" in str(exc):
				self.skipTest(f"PDF engine unavailable: {exc}")
			raise
		self.assertEqual(frappe.local.response.type, "pdf")
		self.assertTrue(frappe.local.response.filecontent)
		self.assertIn("daily-punch-summary", frappe.local.response.filename)

	def test_monthly_machine_filter(self):
		machine_a = self._make_machine(self.MACHINE_A)
		machine_b = self._make_machine(self.MACHINE_B)
		machine_user = self._make_machine_user(machine_a.name, "90", "Machine Filter User")
		day = now_datetime().replace(day=8, hour=9, minute=0, second=0, microsecond=0)
		self._make_punch(machine_a.name, "90", day)
		self._make_punch(
			machine_a.name, "90", day.replace(hour=18), punch_direction="Out"
		)
		self._make_punch(machine_b.name, "90", day.replace(hour=10))
		self._make_punch(
			machine_b.name, "90", day.replace(hour=17), punch_direction="Out"
		)

		all_rows = build_employee_monthly_punch_summary_rows(
			machine_user.name, day.replace(day=1)
		)
		self.assertEqual(len(all_rows), get_last_day(day).day)
		day_row = next(row for row in all_rows if getdate(row["date"]).day == 8)
		self.assertEqual(day_row["punches"], 4)

		filtered = build_employee_monthly_punch_summary_rows(
			machine_user.name, day.replace(day=1), machine=machine_a.name
		)
		self.assertEqual(len(filtered), get_last_day(day).day)
		filtered_day = next(row for row in filtered if getdate(row["date"]).day == 8)
		self.assertEqual(filtered_day["punches"], 2)
		self.assertEqual(filtered_day["punched_in_display"], "09:00:00")
		self.assertEqual(filtered_day["punched_out_display"], "18:00:00")
