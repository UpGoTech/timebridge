# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
One machine user, one date range, every day — with In, Out, and working hours.

Built directly from TimeBridge Punch Log for the selected TimeBridge Machine
User. The name shown is the device's user_name, not TimeBridge Employee.
"""

import calendar

import frappe

from frappe.utils import add_days, date_diff, flt, get_first_day, getdate, today

from timebridge.timebridge.report.attendance_report.attendance_report import (
    NO_RECORD_CODE,
    STATUS_CODE,
    WEEKLY_OFF_CODE,
)
from timebridge.timebridge.services.attendance_sync import (
    punches_grouped_by_day,
    summarize_punch_day,
    weekly_off_days,
)


def execute(filters=None):

    filters = frappe._dict(filters or {})
    machine_user = filters.get("machine_user")

    columns = get_columns()

    if not machine_user:
        return columns, [], no_machine_user_message(), None, []

    machine_user_doc = frappe.db.get_value(
        "TimeBridge Machine User",
        machine_user,
        ["user_name", "user_id", "employee"],
        as_dict=True,
    )

    if not machine_user_doc:
        return columns, [], no_machine_user_message(), None, []

    first, last = resolve_period(filters)
    rows = build_rows(machine_user, machine_user_doc.employee, first, last)

    return columns, rows, heading(machine_user_doc, first, last), None, []


def resolve_period(filters):

    first = getdate(filters.from_date) if filters.get("from_date") else get_first_day(today())
    last = getdate(filters.to_date) if filters.get("to_date") else today()

    if first > last:
        frappe.throw(frappe._("From Date cannot be after To Date"))

    if date_diff(last, first) > 365:
        frappe.throw(frappe._("Date range cannot exceed 366 days"))

    return first, last


def get_columns():

    return [
        {"label": "Date", "fieldname": "attendance_date", "fieldtype": "Date", "width": 100},
        {"label": "Day", "fieldname": "day_name", "fieldtype": "Data", "width": 60},
        {"label": "Status", "fieldname": "status_code", "fieldtype": "Data", "width": 70},
        {"label": "In", "fieldname": "first_in", "fieldtype": "Data", "width": 70},
        {"label": "Out", "fieldname": "last_out", "fieldtype": "Data", "width": 70},
        {"label": "Working Hours", "fieldname": "working_hours", "fieldtype": "Float", "width": 110, "precision": 2},
    ]


def build_rows(machine_user, employee, first, last):
    """One row per calendar day in the range, whether or not anything was recorded."""

    from timebridge.timebridge.doctype.timebridge_holiday.timebridge_holiday import (
        holidays_between,
    )

    records = day_records_from_punches(machine_user, employee, first, last)
    holidays = holidays_between(first, last)
    off_days = weekly_off_dates_between(first, last)

    rows = []
    date = first

    while date <= last:
        record = records.get(date)

        row = {
            "attendance_date": date,
            "day_name": calendar.day_abbr[date.weekday()],
            "first_in": None,
            "last_out": None,
            "working_hours": None,
        }

        if not record:
            if date in holidays:
                row["status_code"] = STATUS_CODE["Holiday"]
                row["remarks"] = holidays[date]
            elif date in off_days:
                row["status_code"] = WEEKLY_OFF_CODE
            else:
                row["status_code"] = NO_RECORD_CODE

            rows.append(row)
            date = add_days(date, 1)
            continue

        code = STATUS_CODE.get(record.status, "?")

        row.update({
            "status_code": code,
            "status": record.status,
            "first_in": clock(record.first_in),
            "last_out": clock(record.last_out),
            "working_hours": hours(record.total_hours),
        })

        rows.append(row)
        date = add_days(date, 1)

    return rows


def day_records_from_punches(machine_user, employee, first, last):
    """Summarise Punch Log rows into one record per day."""

    grouped = punches_grouped_by_day(
        from_date=first,
        to_date=last,
        machine_user=machine_user,
    )

    return {
        day: summarize_punch_day(employee, day, punches)
        for day, punches in grouped.items()
    }


def weekly_off_dates_between(first, last):
    """Weekly off dates across an arbitrary range (not tied to one calendar month)."""

    off_weekdays = weekly_off_days()
    off_dates = set()
    date = getdate(first)
    last = getdate(last)

    while date <= last:
        if date.weekday() in off_weekdays:
            off_dates.add(date)
        date = add_days(date, 1)

    return off_dates


def clock(value):
    """Just the time. The date is already the first column of the row."""

    return str(value)[11:16] if value else None


def hours(value):
    """Blank when zero — a day with no out punch should not read as '0.00 hours'."""

    value = flt(value, 2)
    return value if value else None


def heading(machine_user_doc, first, last):
    """Title uses the device user name from TimeBridge Machine User."""

    shift = ""
    employee = machine_user_doc.employee

    if employee:
        shift_name = frappe.db.get_value("TimeBridge Employee", employee, "shift")

        if shift_name:
            bounds = frappe.db.get_value(
                "TimeBridge Shift",
                shift_name,
                ["shift_name", "start_time", "end_time"],
                as_dict=True,
            )

            if bounds:
                label = frappe.utils.escape_html(bounds.shift_name or shift_name)
                hours_label = f"{str(bounds.start_time)[:5]}–{str(bounds.end_time)[:5]}"

                if str(bounds.start_time)[:5] not in label:
                    label = f"{label} {hours_label}"

                shift = f" &nbsp;·&nbsp; {label}"

    period = f"{frappe.utils.formatdate(first)} – {frappe.utils.formatdate(last)}"
    user_id = machine_user_doc.user_id or ""
    id_label = f" &nbsp;·&nbsp; ID {frappe.utils.escape_html(user_id)}" if user_id else ""

    return (
        "<div style='text-align:center;line-height:1.6;margin-bottom:4px'>"
        f"<div style='font-size:15px;font-weight:700'>"
        f"{frappe.utils.escape_html(machine_user_doc.user_name or user_id)}</div>"
        f"<div style='font-size:12px;color:#777'>{period}{id_label}{shift}</div>"
        "</div>"
    )


def no_machine_user_message():

    return (
        "<div style='text-align:center;color:#777;padding:8px'>"
        "Pick a machine user to see their day-by-day working hours."
        "</div>"
    )
