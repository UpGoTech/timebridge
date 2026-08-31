# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Workspace dashboard helpers — distinct active users from punch logs."""

import calendar
from collections import defaultdict

import frappe
from frappe.utils import (
	add_days,
	format_date,
	format_time,
	get_datetime,
	get_first_day,
	get_last_day,
	getdate,
	now_datetime,
	today,
)
from frappe.utils.dateutils import (
	get_dates_from_timegrain,
	get_from_date_from_timespan,
	get_period,
	get_period_beginning,
)

def _distinct_user_key_sql():
	if frappe.db.db_type == "postgres":
		return "machine || '::' || device_user_id"
	return "CONCAT(machine, '::', device_user_id)"


def _today_sql_predicate():
	if frappe.db.db_type == "postgres":
		return "DATE(timestamp) = CURRENT_DATE"
	return "DATE(timestamp) = CURDATE()"


def _count_distinct_users_on_date(punch_date):
	key = _distinct_user_key_sql()
	return frappe.db.sql(
		f"""
		SELECT COUNT(DISTINCT {key})
		FROM `tabTimeBridge Punch Log`
		WHERE DATE(timestamp) = %(punch_date)s
		""",
		{"punch_date": getdate(punch_date)},
	)[0][0] or 0


def _count_distinct_users_today():
	return _count_distinct_users_on_date(today())


def _active_users_by_day(from_date, to_date):
	key = _distinct_user_key_sql()
	rows = frappe.db.sql(
		f"""
		SELECT DATE(timestamp) AS day,
			COUNT(DISTINCT {key}) AS count
		FROM `tabTimeBridge Punch Log`
		WHERE timestamp >= %s AND timestamp <= %s
		GROUP BY DATE(timestamp)
		ORDER BY day
		""",
		(from_date, to_date),
		as_dict=True,
	)
	return {getdate(row.day): int(row.count) for row in rows}


def _build_active_users_chart(chart, from_date, to_date, timegrain):
	counts_by_day = _active_users_by_day(from_date, to_date)
	dates = get_dates_from_timegrain(getdate(from_date), getdate(to_date), timegrain)
	result = [[getdate(d), counts_by_day.get(getdate(d), 0)] for d in dates]

	return {
		"labels": [
			format_date(get_period(r[0], timegrain), parse_day_first=True)
			if timegrain in ("Daily", "Weekly")
			else get_period(r[0], timegrain)
			for r in result
		],
		"datasets": [{"name": chart.name, "values": [r[1] for r in result]}],
	}


def _format_punch_time(timestamp):
	if not timestamp:
		return ""
	ts = get_datetime(timestamp)
	return format_time(ts)


def _compute_working_hours(punched_in, punched_out):
	"""Return (decimal_hours, display) e.g. (9.5, '9:30'). Blank when out is missing."""
	if not punched_in or not punched_out:
		return None, ""
	in_dt = get_datetime(punched_in)
	out_dt = get_datetime(punched_out)
	if out_dt <= in_dt:
		return None, ""
	total_minutes = int((out_dt - in_dt).total_seconds() // 60)
	hours, minutes = divmod(total_minutes, 60)
	return round(total_minutes / 60, 2), f"{hours}:{minutes:02d}"


def _fetch_punches_for_date(punch_date, machine=None):
	punch_date = getdate(punch_date)
	conditions = ["DATE(timestamp) = %(punch_date)s"]
	values = {"punch_date": punch_date}
	if machine:
		conditions.append("machine = %(machine)s")
		values["machine"] = machine

	where = " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT machine, device_user_id, machine_user, timestamp, punch_direction
		FROM `tabTimeBridge Punch Log`
		WHERE {where}
		ORDER BY timestamp
		""",
		values,
		as_dict=True,
	)


def _machine_user_names(machine_user_ids):
	if not machine_user_ids:
		return {}
	rows = frappe.get_all(
		"TimeBridge Machine User",
		filters={"name": ["in", list(machine_user_ids)]},
		fields=["name", "user_name", "user_id", "machine"],
	)
	return {row.name: row for row in rows}


def _machine_user_names_by_device_ids(pairs):
	"""pairs: set of (machine, device_user_id)"""
	if not pairs:
		return {}
	machines = {machine for machine, _ in pairs}
	rows = frappe.get_all(
		"TimeBridge Machine User",
		filters={"machine": ["in", list(machines)]},
		fields=["machine", "user_id", "user_name"],
	)
	name_map = {}
	for row in rows:
		name_map[(row.machine, row.user_id)] = row.user_name
	return name_map


def _format_monthly_summary_date(day):
	"""e.g. 05-Aug-2026 (Wed)"""
	day = getdate(day)
	return f"{day.day:02d}-{day.strftime('%b')}-{day.year} ({calendar.day_abbr[day.weekday()]})"


def _summarize_day_punches(punches):
	"""In/out/hrs/count for one calendar day from punch rows."""
	if not punches:
		return {
			"punched_in": None,
			"punched_in_display": "",
			"punched_out": None,
			"punched_out_display": "",
			"working_hours": None,
			"working_hours_display": "",
			"punches": 0,
		}

	in_punches = [p for p in punches if p.punch_direction == "In"]
	out_punches = [p for p in punches if p.punch_direction == "Out"]
	first_punch = min(punches, key=lambda p: p.timestamp)
	punched_in = (
		min(in_punches, key=lambda p: p.timestamp).timestamp
		if in_punches
		else first_punch.timestamp
	)
	punched_out = (
		max(out_punches, key=lambda p: p.timestamp).timestamp if out_punches else None
	)
	punched_in_dt = get_datetime(punched_in)
	punched_out_dt = get_datetime(punched_out) if punched_out else None
	working_hours, working_hours_display = _compute_working_hours(punched_in_dt, punched_out_dt)
	return {
		"punched_in": punched_in_dt,
		"punched_in_display": _format_punch_time(punched_in),
		"punched_out": punched_out_dt,
		"punched_out_display": _format_punch_time(punched_out),
		"working_hours": working_hours,
		"working_hours_display": working_hours_display,
		"punches": len(punches),
	}


def _fetch_punches_for_user_month(user_id, from_date, to_date):
	return frappe.db.sql(
		"""
		SELECT machine, device_user_id, machine_user, timestamp, punch_direction
		FROM `tabTimeBridge Punch Log`
		WHERE device_user_id = %(user_id)s
		  AND DATE(timestamp) >= %(from_date)s
		  AND DATE(timestamp) <= %(to_date)s
		ORDER BY timestamp
		""",
		{
			"user_id": str(user_id),
			"from_date": getdate(from_date),
			"to_date": getdate(to_date),
		},
		as_dict=True,
	)


def build_employee_monthly_punch_summary_rows(machine_user, month):
	"""One row per calendar day for a user's global device_user_id."""
	if not machine_user or not month:
		return []

	user_id = frappe.db.get_value("TimeBridge Machine User", machine_user, "user_id")
	if not user_id:
		frappe.throw("TimeBridge Machine User not found")

	month_date = getdate(month)
	from_date = get_first_day(month_date)
	to_date = get_last_day(month_date)

	punches = _fetch_punches_for_user_month(user_id, from_date, to_date)
	by_day = defaultdict(list)
	for punch in punches:
		by_day[getdate(punch.timestamp)].append(punch)

	rows = []
	day = from_date
	while day <= to_date:
		summary = _summarize_day_punches(by_day.get(day, []))
		rows.append(
			{
				"date": day,
				"date_display": _format_monthly_summary_date(day),
				**summary,
			}
		)
		day = add_days(day, 1)
	return rows


@frappe.whitelist()
def get_employee_monthly_punch_summary_list(machine_user=None, month=None):
	"""Rows and user metadata for the Employee Monthly Punch Summary Desk Page."""

	if not machine_user:
		frappe.throw("User is required")
	if not month:
		frappe.throw("Month is required")

	mu = frappe.db.get_value(
		"TimeBridge Machine User",
		machine_user,
		["user_id", "user_name"],
		as_dict=True,
	)
	return {
		"user_id": mu.user_id if mu else "",
		"user_name": mu.user_name if mu else "",
		"rows": build_employee_monthly_punch_summary_rows(machine_user, month),
	}


def build_daily_punch_summary_rows(punch_date, machine=None):
	punches = _fetch_punches_for_date(punch_date, machine=machine)
	grouped = defaultdict(list)
	for punch in punches:
		grouped[(punch.machine, punch.device_user_id)].append(punch)

	machine_user_ids = {p.machine_user for p in punches if p.machine_user}
	linked_users = _machine_user_names(machine_user_ids)
	name_by_device = _machine_user_names_by_device_ids(set(grouped.keys()))

	rows = []
	for (machine_id, device_user_id), user_punches in grouped.items():
		summary = _summarize_day_punches(user_punches)

		user_name = device_user_id
		linked = next((p.machine_user for p in user_punches if p.machine_user), None)
		if linked and linked in linked_users:
			user_name = linked_users[linked].user_name
		elif (machine_id, device_user_id) in name_by_device:
			user_name = name_by_device[(machine_id, device_user_id)]

		rows.append(
			{
				"user_name": user_name,
				**summary,
				"machine": machine_id,
				"device_user_id": device_user_id,
			}
		)

	rows.sort(key=lambda row: row["punched_in"] or get_datetime("1900-01-01"), reverse=True)
	return rows


@frappe.whitelist()
def get_daily_punch_summary_list(date=None, machine=None):
	"""Rows for the Daily Punch Summary modal."""

	if not date:
		frappe.throw("Date is required")
	return build_daily_punch_summary_rows(date, machine or None)


@frappe.whitelist()
def get_users_punched_today(filters=None):
	"""Custom Number Card — Today's Punch Summary; click opens the Desk Page."""

	return {
		"value": _count_distinct_users_today(),
		"route": "daily-punch-summary",
		"route_options": {"date": today()},
	}


@frappe.whitelist()
def get_active_users_per_day_chart(
	chart_name=None,
	chart=None,
	no_cache=None,
	filters=None,
	from_date=None,
	to_date=None,
	timespan=None,
	time_interval=None,
	heatmap_year=None,
	refresh=None,
):
	"""Custom Dashboard Chart — daily distinct active users from punch logs."""

	if chart_name:
		chart_doc = frappe.get_doc("Dashboard Chart", chart_name)
	else:
		chart_doc = frappe._dict(frappe.parse_json(chart))

	timespan = timespan or chart_doc.timespan
	timegrain = time_interval or chart_doc.time_interval or "Daily"

	if timespan == "Select Date Range":
		if from_date and len(from_date):
			from_date = get_datetime(from_date)
		else:
			from_date = get_datetime(chart_doc.from_date)

		if to_date and len(to_date):
			to_date = get_datetime(to_date)
		else:
			to_date = get_datetime(chart_doc.to_date)
	else:
		to_date = now_datetime()
		from_date = get_from_date_from_timespan(to_date, timespan)
		from_date = get_period_beginning(from_date, timegrain)

	return _build_active_users_chart(chart_doc, from_date, to_date, timegrain)
