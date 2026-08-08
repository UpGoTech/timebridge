# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Everyone's clock times for a month, laid out sideways.

The Attendance Register answers "who was here" in one letter a day. Employee
Attendance Detail answers "what time" — but for one person, reading downwards,
which means sixteen exports to see a team.

This is that same question asked sideways: staff down the page, dates across
it, and the actual In and Out in every cell. It exists for Excel. Thirty-one
date columns will not fit a sheet of A4, and the letter register is already
the thing that prints.
"""

import calendar

import frappe

from frappe.utils import cint, get_last_day, getdate

from timebridge.timebridge.report.attendance_report.attendance_report import (
    SICK_LEAVE_CODE,
    STATUS_CODE,
    WEEKLY_OFF_CODE,
    code_sort_key,
    get_employees,
    weekly_off_dates,
)

# Both times in one cell, as chosen. The alternative — a separate In column and
# Out column per day — reaches sixty-four columns and puts each time in its own
# Excel cell, which is better for arithmetic and worse for reading. Reading won.
TIME_JOIN = "-"

LEGEND = (
    "हर खाने में <b>In-Out</b> का समय &nbsp;·&nbsp; "
    "R = साप्ताहिक अवकाश &nbsp;·&nbsp; H = त्योहार &nbsp;·&nbsp; "
    "S = बीमारी की छुट्टी &nbsp;·&nbsp; L = अन्य छुट्टी &nbsp;·&nbsp; "
    "A = गैरहाज़िर &nbsp;·&nbsp; ख़ाली = कोई रिकॉर्ड नहीं"
)


def execute(filters=None):

    filters = frappe._dict(filters or {})

    month, year = resolve_period(filters)
    days = calendar.monthrange(year, month)[1]

    off_days = weekly_off_dates(year, month, days)
    employees = get_employees(filters)

    columns = build_columns(days, off_days)

    if not employees:
        return columns, [], LEGEND

    records = day_times(employees, year, month)

    # By code read as a number, the same order the register uses — 2 before 10,
    # not after it.
    employees = sorted(employees, key=code_sort_key)

    return columns, build_rows(employees, records, off_days, days), LEGEND


def resolve_period(filters):

    if filters.get("month") and filters.get("year"):
        return cint(filters.month), cint(filters.year)

    today = getdate()

    return today.month, today.year


def day_times(employees, year, month):
    """
    Clock times for the month, keyed by (employee, day-of-month).

    The register has a helper of its own, but it never selects the times —
    it only ever needed a status letter. Rather than widening a query two
    reports would then share for different reasons, this asks for exactly what
    a punch register needs, and needs no join: leave_type is already carried on
    the attendance row.
    """

    first = getdate(f"{year}-{month:02d}-01")
    last = get_last_day(first)

    rows = frappe.db.sql(
        """
        SELECT employee, DAY(attendance_date) AS day,
               first_in, last_out, status, leave_type
        FROM `tabTimeBridge Attendance`
        WHERE employee IN %(employees)s
          AND attendance_date BETWEEN %(first)s AND %(last)s
        """,
        {"employees": [e.name for e in employees], "first": first, "last": last},
        as_dict=True,
    )

    return {(r.employee, r.day): r for r in rows}


def build_columns(days, off_days):

    columns = [
        {"label": "Code", "fieldname": "employee_code", "fieldtype": "Data", "width": 60},
        {"label": "Full Name Of The Employee", "fieldname": "employee_name",
         "fieldtype": "Data", "width": 180},
    ]

    for day in range(1, days + 1):

        columns.append({
            "label": str(day),
            "fieldname": f"day_{day}",
            "fieldtype": "Data",
            # Wide enough for "11:38-19:01" without clipping, which is the
            # whole point of the report.
            "width": 100,
            # Read by the client to shade the date of a weekly off, the same
            # way the register marks its Sundays.
            "weekly_off": 1 if day in off_days else 0,
        })

    return columns


def build_rows(employees, records, off_days, days):

    data = []

    for emp in employees:

        row = {
            "employee": emp.name,
            "employee_code": emp.employee_code,
            "employee_name": emp.employee_name,
        }

        for day in range(1, days + 1):
            row[f"day_{day}"] = cell(records.get((emp.name, day)), day, off_days)

        data.append(row)

    return data


def cell(record, day, off_days):
    """
    What one day says.

    A time when there is one. Otherwise the register's own letter, so a day off
    and a day skipped never look alike — an empty cell would make a Sunday
    indistinguishable from an absence.
    """

    if not record:
        return WEEKLY_OFF_CODE if day in off_days else ""

    first_in = clock(record.first_in)
    last_out = clock(record.last_out)

    if first_in and last_out:
        return f"{first_in}{TIME_JOIN}{last_out}"

    # One punch and no pair. The time is still real and worth showing; the
    # trailing dash says the other half never arrived rather than implying the
    # person left at that moment.
    if first_in:
        return f"{first_in}{TIME_JOIN}"

    if record.status == "On Leave" and (record.leave_type or "") == "Sick Leave":
        return SICK_LEAVE_CODE

    return STATUS_CODE.get(record.status, "") or (
        WEEKLY_OFF_CODE if day in off_days else ""
    )


def clock(value):
    """Just the clock face — the date is already the column heading."""

    return str(value)[11:16] if value else None
