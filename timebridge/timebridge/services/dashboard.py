# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Workspace dashboard helpers — distinct active users from punch logs."""

import calendar
from collections import defaultdict
from html import escape

import frappe
from frappe.utils import (
	add_days,
	add_to_date,
	flt,
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

DEFAULT_EXPECTED_WORKING_HOURS = 9.0


def ensure_default_expected_working_hours():
	"""Persist Settings.default_expected_working_hours when missing (Singles gotcha)."""
	current = frappe.db.get_single_value(
		"TimeBridge Settings", "default_expected_working_hours"
	)
	if current is None or current == "" or flt(current) <= 0:
		frappe.db.set_single_value(
			"TimeBridge Settings",
			"default_expected_working_hours",
			DEFAULT_EXPECTED_WORKING_HOURS,
		)


def resolve_expected_hours(machine_user=None):
	"""Machine User hours if set, else Settings, else 9.0."""
	if machine_user:
		mu_hours = frappe.db.get_value(
			"TimeBridge Machine User", machine_user, "expected_working_hours"
		)
		if mu_hours is not None and mu_hours != "" and flt(mu_hours) > 0:
			return flt(mu_hours)

	settings_hours = frappe.db.get_single_value(
		"TimeBridge Settings", "default_expected_working_hours"
	)
	if settings_hours is not None and settings_hours != "" and flt(settings_hours) > 0:
		return flt(settings_hours)
	return DEFAULT_EXPECTED_WORKING_HOURS


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


def _format_chart_day_label(day):
	"""e.g. 30-Aug-26 (Sun) — Active Users Per Day chart axis."""
	day = getdate(day)
	return f"{day.day}-{day.strftime('%b')}-{day.strftime('%y')} ({calendar.day_abbr[day.weekday()]})"


def _format_chart_axis_label(day, timegrain):
	"""Format an axis tick from a real date — never from get_period() strings.

	get_period(Daily/Weekly) returns dd-mm-yy (e.g. 06-09-26). Feeding that back
	into getdate()/format_date() re-parses as month-first, so 6 Sep becomes 9 Jun.
	"""
	day = getdate(day)
	if timegrain == "Daily":
		return _format_chart_day_label(day)
	if timegrain == "Weekly":
		# Period ending (Saturday) as an unambiguous day label.
		return _format_chart_day_label(day)
	return get_period(day, timegrain)


def _build_active_users_chart(chart, from_date, to_date, timegrain):
	counts_by_day = _active_users_by_day(from_date, to_date)
	dates = get_dates_from_timegrain(getdate(from_date), getdate(to_date), timegrain)
	result = [[getdate(d), counts_by_day.get(getdate(d), 0)] for d in dates]

	return {
		"labels": [_format_chart_axis_label(r[0], timegrain) for r in result],
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


def _local_day_range(day):
	"""Half-open [start, end) in site-local naive datetimes — avoids DATE() TZ shifts."""
	start = get_datetime(f"{getdate(day)} 00:00:00")
	end = add_to_date(start, days=1)
	return start, end


def _fetch_punches_for_date(punch_date, machine=None):
	start, end = _local_day_range(punch_date)
	conditions = ["timestamp >= %(start)s", "timestamp < %(end)s"]
	values = {"start": start, "end": end}
	if machine:
		conditions.append("machine = %(machine)s")
		values["machine"] = machine

	where = " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT name, machine, device_user_id, machine_user, timestamp, punch_direction
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
		fields=["name", "user_name", "user_id", "machine", "expected_working_hours"],
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
		fields=["machine", "user_id", "user_name", "name", "expected_working_hours"],
	)
	name_map = {}
	for row in rows:
		name_map[(row.machine, row.user_id)] = row
	return name_map


def _format_monthly_summary_date(day):
	"""e.g. 05-Aug-2026 (Wed)"""
	day = getdate(day)
	return f"{day.day:02d}-{day.strftime('%b')}-{day.year} ({calendar.day_abbr[day.weekday()]})"


def _punch_direction_label(direction):
	"""Normalize device direction to In / Out / Unknown for display."""
	value = (direction or "").strip()
	if value in ("In", "Out"):
		return value
	return "Unknown"


def _row_status(punches_count, punched_in, punched_out, working_hours, expected_hours):
	if punches_count <= 0:
		return "absent"
	if punched_in and not punched_out:
		return "no_out"
	if working_hours is not None and flt(working_hours) < flt(expected_hours):
		return "short"
	return "ok"


def _summarize_day_punches(punches, expected_hours=None):
	"""First/last punch of the day as In/Out; ignore punch_direction for times."""
	expected = (
		flt(expected_hours)
		if expected_hours is not None
		else DEFAULT_EXPECTED_WORKING_HOURS
	)
	if not punches:
		return {
			"punched_in": None,
			"punched_in_display": "",
			"punched_out": None,
			"punched_out_display": "",
			"working_hours": None,
			"working_hours_display": "",
			"punches": 0,
			"punch_details": [],
			"row_status": "absent",
			"expected_working_hours": expected,
		}

	ordered = sorted(punches, key=lambda p: get_datetime(p.timestamp))
	punch_details = [
		{
			"name": p.get("name") or getattr(p, "name", None),
			"date_display": _format_monthly_summary_date(getdate(p.timestamp)),
			"time_display": _format_punch_time(p.timestamp),
			"direction": _punch_direction_label(p.punch_direction),
		}
		for p in ordered
	]

	first_punch = ordered[0]
	punched_in_dt = get_datetime(first_punch.timestamp)
	punched_out_dt = None
	if len(ordered) >= 2:
		punched_out_dt = get_datetime(ordered[-1].timestamp)

	working_hours, working_hours_display = _compute_working_hours(
		punched_in_dt, punched_out_dt
	)
	return {
		"punched_in": punched_in_dt,
		"punched_in_display": _format_punch_time(first_punch.timestamp),
		"punched_out": punched_out_dt,
		"punched_out_display": _format_punch_time(
			ordered[-1].timestamp if punched_out_dt else None
		),
		"working_hours": working_hours,
		"working_hours_display": working_hours_display,
		"punches": len(ordered),
		"punch_details": punch_details,
		"row_status": _row_status(
			len(ordered), punched_in_dt, punched_out_dt, working_hours, expected
		),
		"expected_working_hours": expected,
	}


def _fetch_punches_for_user_month(user_id, from_date, to_date, machine=None):
	start, _ = _local_day_range(from_date)
	_, end = _local_day_range(to_date)
	conditions = [
		"device_user_id = %(user_id)s",
		"timestamp >= %(start)s",
		"timestamp < %(end)s",
	]
	values = {
		"user_id": str(user_id),
		"start": start,
		"end": end,
	}
	if machine:
		conditions.append("machine = %(machine)s")
		values["machine"] = machine
	where = " AND ".join(conditions)
	return frappe.db.sql(
		f"""
		SELECT name, machine, device_user_id, machine_user, timestamp, punch_direction
		FROM `tabTimeBridge Punch Log`
		WHERE {where}
		ORDER BY timestamp
		""",
		values,
		as_dict=True,
	)


def build_employee_monthly_punch_summary_rows(
	machine_user, month, expected_hours=None, machine=None
):
	"""One row per calendar day for a user's global device_user_id.

	Days without punches stay blank (nothing invented). Optional machine limits
	punches to that TimeBridge Machine.
	"""
	if not machine_user or not month:
		return []

	user_id = frappe.db.get_value("TimeBridge Machine User", machine_user, "user_id")
	if not user_id:
		frappe.throw("TimeBridge Machine User not found")

	expected = (
		flt(expected_hours)
		if expected_hours is not None
		else resolve_expected_hours(machine_user)
	)
	month_date = getdate(month)
	from_date = get_first_day(month_date)
	to_date = get_last_day(month_date)

	punches = _fetch_punches_for_user_month(
		user_id, from_date, to_date, machine=machine or None
	)
	by_day = defaultdict(list)
	for punch in punches:
		by_day[getdate(punch.timestamp)].append(punch)

	rows = []
	day = from_date
	while day <= to_date:
		summary = _summarize_day_punches(by_day.get(day, []), expected_hours=expected)
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
def get_employee_monthly_punch_summary_list(machine_user=None, month=None, machine=None):
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
	expected = resolve_expected_hours(machine_user)
	return {
		"user_id": mu.user_id if mu else "",
		"user_name": mu.user_name if mu else "",
		"expected_working_hours": expected,
		"machine": machine or "",
		"rows": build_employee_monthly_punch_summary_rows(
			machine_user, month, expected_hours=expected, machine=machine or None
		),
	}


def build_daily_punch_summary_rows(punch_date, machine=None):
	punches = _fetch_punches_for_date(punch_date, machine=machine)
	grouped = defaultdict(list)
	for punch in punches:
		grouped[(punch.machine, punch.device_user_id)].append(punch)

	machine_user_ids = {p.machine_user for p in punches if p.machine_user}
	linked_users = _machine_user_names(machine_user_ids)
	name_by_device = _machine_user_names_by_device_ids(set(grouped.keys()))
	default_expected = resolve_expected_hours(None)

	rows = []
	for (machine_id, device_user_id), user_punches in grouped.items():
		linked = next((p.machine_user for p in user_punches if p.machine_user), None)
		expected = default_expected
		user_name = device_user_id
		if linked and linked in linked_users:
			user_name = linked_users[linked].user_name
			expected = resolve_expected_hours(linked)
		elif (machine_id, device_user_id) in name_by_device:
			mu_row = name_by_device[(machine_id, device_user_id)]
			user_name = mu_row.user_name
			expected = resolve_expected_hours(mu_row.name)

		summary = _summarize_day_punches(user_punches, expected_hours=expected)
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


def _legend_html(grayscale=False):
	# wkhtmltopdf mishandles inline-block legends; use a single-row table.
	if grayscale:
		short_bg, no_out_bg = "#777777", "#d8d8d8"
	else:
		short_bg, no_out_bg = "#ffe8cc", "#e8f0fe"
	return f"""
	<table class="tb-ps-legend" cellpadding="0" cellspacing="0">
		<tr>
			<td class="tb-ps-legend-cell">
				<span class="tb-ps-swatch" style="background:{short_bg}">&nbsp;</span>
				<span class="tb-ps-legend-label">Below expected hours</span>
			</td>
			<td class="tb-ps-legend-cell">
				<span class="tb-ps-swatch" style="background:{no_out_bg}">&nbsp;</span>
				<span class="tb-ps-legend-label">No out punch</span>
			</td>
			<td class="tb-ps-legend-cell">
				<span class="tb-ps-swatch" style="background:#ffffff;border:1px solid #999">&nbsp;</span>
				<span class="tb-ps-legend-label">Normal / absent</span>
			</td>
		</tr>
	</table>
	"""


def _table_styles(grayscale=False):
	if grayscale:
		short = "background:#777777;color:#fff;"
		no_out = "background:#d8d8d8;"
	else:
		short = "background:#ffe8cc;"
		no_out = "background:#e8f0fe;"
	return f"""
	<style>
		@page {{ size: A4 portrait; margin: 12mm; }}
		body {{ font-family: Helvetica, Arial, sans-serif; font-size: 11px; color: #222; }}
		h1 {{ font-size: 16px; margin: 0 0 4px; }}
		.tb-ps-meta {{ color: #555; margin-bottom: 12px; }}
		table.tb-ps-legend {{
			width: auto; border-collapse: collapse; margin: 0 0 14px 0;
			border: none;
		}}
		table.tb-ps-legend td {{
			border: none; padding: 0 18px 0 0; vertical-align: middle;
			white-space: nowrap; font-size: 11px;
		}}
		.tb-ps-swatch {{
			width: 12px; height: 12px; border: 1px solid #999;
			display: inline-block; vertical-align: middle; line-height: 12px;
			font-size: 8px;
		}}
		.tb-ps-legend-label {{ vertical-align: middle; margin-left: 4px; }}
		table.tb-ps-data {{ width: 100%; border-collapse: collapse; }}
		table.tb-ps-data th, table.tb-ps-data td {{
			border: 1px solid #ccc; padding: 6px 8px; text-align: left;
		}}
		table.tb-ps-data th {{ background: #f3f3f3; font-size: 10px; text-transform: uppercase; }}
		table.tb-ps-data td.r, table.tb-ps-data th.r {{ text-align: right; }}
		table.tb-ps-data tr.short td {{ {short} }}
		table.tb-ps-data tr.no_out td {{ {no_out} }}
	</style>
	"""


def _render_punch_summary_html(
	title,
	subtitle,
	columns,
	rows,
	grayscale=False,
):
	"""Shared A4 HTML for Print and PDF."""
	header = "".join(
		f'<th class="{"r" if col.get("align") == "right" else ""}">{escape(col["label"])}</th>'
		for col in columns
	)
	body_rows = []
	for row in rows:
		status = row.get("row_status") or "ok"
		cls = status if status in ("short", "no_out") else ""
		cells = []
		for col in columns:
			val = row.get(col["key"], "")
			if val is None:
				val = ""
			align = "r" if col.get("align") == "right" else ""
			cells.append(f'<td class="{align}">{escape(str(val))}</td>')
		body_rows.append(f'<tr class="{cls}">{"".join(cells)}</tr>')

	return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">{_table_styles(grayscale=grayscale)}</head>
<body>
<h1>{escape(title)}</h1>
<div class="tb-ps-meta">{escape(subtitle)}</div>
{_legend_html(grayscale=grayscale)}
<table class="tb-ps-data">
<thead><tr>{header}</tr></thead>
<tbody>{"".join(body_rows)}</tbody>
</table>
</body></html>"""


def build_employee_monthly_punch_summary_html(
	machine_user, month, grayscale=False, machine=None
):
	payload = get_employee_monthly_punch_summary_list(
		machine_user, month, machine=machine or None
	)
	month_date = getdate(month)
	period = f"{month_date.strftime('%B')} {month_date.year}"
	user_label = " · ".join(
		part for part in [payload.get("user_id"), payload.get("user_name")] if part
	) or "—"
	expected = payload.get("expected_working_hours")
	parts = [user_label, period]
	if machine:
		parts.append(str(machine))
	parts.append(f"Expected {expected:g}h")
	subtitle = " · ".join(parts)
	columns = [
		{"key": "date_display", "label": "Date"},
		{"key": "punched_in_display", "label": "Punched In"},
		{"key": "punched_out_display", "label": "Punched Out"},
		{"key": "working_hours_display", "label": "Working Hrs", "align": "right"},
		{"key": "punches", "label": "Punches", "align": "right"},
	]
	return _render_punch_summary_html(
		"Employee Monthly Punch Summary",
		subtitle,
		columns,
		payload.get("rows") or [],
		grayscale=grayscale,
	)


def build_daily_punch_summary_html(punch_date, machine=None, grayscale=False):
	rows = build_daily_punch_summary_rows(punch_date, machine or None)
	day = getdate(punch_date)
	subtitle = day.strftime("%d-%b-%Y")
	if machine:
		subtitle = f"{subtitle} · {machine}"
	columns = [
		{"key": "user_name", "label": "User Name"},
		{"key": "punched_in_display", "label": "Punched In"},
		{"key": "punched_out_display", "label": "Punched Out"},
		{"key": "working_hours_display", "label": "Working Hrs", "align": "right"},
		{"key": "punches", "label": "Punches", "align": "right"},
	]
	return _render_punch_summary_html(
		"Daily Punch Summary",
		subtitle,
		columns,
		rows,
		grayscale=grayscale,
	)


@frappe.whitelist()
def get_employee_monthly_punch_summary_print_html(
	machine_user=None, month=None, machine=None
):
	if not machine_user:
		frappe.throw("User is required")
	if not month:
		frappe.throw("Month is required")
	return build_employee_monthly_punch_summary_html(
		machine_user, month, grayscale=False, machine=machine or None
	)


@frappe.whitelist()
def get_daily_punch_summary_print_html(date=None, machine=None):
	if not date:
		frappe.throw("Date is required")
	return build_daily_punch_summary_html(date, machine or None, grayscale=False)


@frappe.whitelist()
def download_employee_monthly_punch_summary_pdf(
	machine_user=None, month=None, machine=None
):
	from frappe.utils.pdf import get_pdf

	if not machine_user:
		frappe.throw("User is required")
	if not month:
		frappe.throw("Month is required")
	html = build_employee_monthly_punch_summary_html(
		machine_user, month, grayscale=True, machine=machine or None
	)
	month_date = getdate(month)
	filename = f"employee-monthly-punch-summary-{month_date.strftime('%Y-%m')}.pdf"
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def download_daily_punch_summary_pdf(date=None, machine=None):
	from frappe.utils.pdf import get_pdf

	if not date:
		frappe.throw("Date is required")
	html = build_daily_punch_summary_html(date, machine or None, grayscale=True)
	filename = f"daily-punch-summary-{getdate(date)}.pdf"
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = get_pdf(html)
	frappe.local.response.type = "pdf"


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
