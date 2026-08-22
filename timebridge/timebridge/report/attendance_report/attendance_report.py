# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
The monthly attendance register: one row per employee, one column per day.

A totals-only Summary view lived here too, behind a View filter. It has been
removed — the register already shows every day and carries its own totals, so
the second view was a different arrangement of the same numbers with a filter
to maintain and a choice to make before either could be read.

The period is always a calendar month rather than a free date range, because
this sheet gets printed and signed one month at a time.
"""

import calendar

import frappe

from frappe.utils import cint, get_last_day, getdate

# One letter per day, so 31 columns still fit across a printed page.
STATUS_CODE = {
    "Present": "P",
    "Absent": "A",
    # Half a day is written the way a paper register writes it — half present,
    # half absent — rather than as a letter someone has to look up.
    "Half Day": "P/A",
    "On Leave": "L",
    "Holiday": "H",
    "In Office": "I",
    "Needs Review": "?",
}

# Sick leave is shown apart from other leave: it is the one with a paid quota,
# so counting it in with the rest would hide the thing worth watching.
SICK_LEAVE_CODE = "S"

WEEKLY_OFF_CODE = "R"
NO_RECORD_CODE = ""

LEGEND = (
    "P = Present &nbsp; A = Absent &nbsp; P/A = Half Day &nbsp; S = Sick Leave &nbsp; L = Other Leave &nbsp; "
    # "I = In Office" is left out on purpose. It can only ever appear against
    # today — someone who has punched in and not yet out — so on a register for
    # a finished month it is a line of legend explaining a letter that is not
    # on the page.
    "H = Holiday &nbsp; R = Rest (Weekly Off) &nbsp; ? = Needs Review"
)


def execute(filters=None):

    return day_wise(frappe._dict(filters or {}))


# ---------------------------------------------------------------- shared

def get_employees(filters):

    conditions = ""
    values = {}

    for field in ("organization", "branch", "department", "shift"):

        if filters.get(field):
            conditions += f" AND emp.{field} = %({field})s"
            values[field] = filters.get(field)

    if filters.get("biometric_machine"):

        # Membership is read from the Machine User links rather than from
        # Employee.biometric_machine, because the link is what attendance
        # actually follows, and that field can only name one machine even for
        # somebody enrolled on two.
        conditions += """
            AND emp.name IN (
                SELECT mu.employee
                FROM `tabMachine User` mu
                WHERE mu.machine = %(biometric_machine)s
                  AND mu.employee IS NOT NULL
            )
        """
        values["biometric_machine"] = filters.get("biometric_machine")

    if filters.get("employee"):
        conditions += " AND emp.name = %(employee)s"
        values["employee"] = filters.get("employee")

    if not filters.get("include_inactive"):
        conditions += " AND emp.is_active = 1"

    return frappe.db.sql(
        f"""
        SELECT
            emp.name, emp.employee_code, emp.employee_name,
            emp.organization, emp.branch, emp.department, emp.shift
        FROM `tabEmployee` emp
        WHERE 1 = 1 {conditions}
        ORDER BY emp.employee_name ASC
        """,
        values,
        as_dict=True,
    )


# --------------------------------------------------------------- day-wise

def day_wise(filters):

    month, year = resolve_period(filters)
    days = calendar.monthrange(year, month)[1]

    off_days = weekly_off_dates(year, month, days)
    employees = get_employees(filters)

    columns = day_columns(year, month, days, off_days)
    heading = day_wise_heading(filters, month, year)

    if not employees:
        return columns, [], heading

    records = day_records(employees, year, month)

    # Ordered by code, read as a number. A plain text sort puts 10 before 2 and
    # 1000 in the middle, which looks like a mistake on a printed register.
    employees = sorted(employees, key=code_sort_key)

    return columns, day_rows(employees, records, off_days, days, month, year), heading


def code_sort_key(employee):

    code = (employee.employee_code or "").strip()

    # Codes are numeric here, but a lettered one (F9, F10) must not crash the
    # sort — it simply goes to the end, in its own alphabetical order.
    if code.isdigit():
        return (0, int(code), "")

    return (1, 0, code.lower())


def day_wise_heading(filters, month, year):
    """
    The title block printed above the table.

    Frappe renders this on screen and carries it into Print and PDF, which is
    where a sheet needs to identify itself — one printed page of letters is
    meaningless without knowing whose staff and which month.

    It does not reach the Excel export; Frappe writes only the grid there. Tick
    "Include filters" when exporting if the period needs to travel with it.
    """

    organisation = filters.get("organization") or frappe.db.get_value(
        "Organization", {}, "name"
    )

    name = frappe.db.get_value("Organization", organisation, "organization_name") or ""

    period = f"{calendar.month_name[month]} {year}"

    # The title block is for paper. On screen the organisation and month are
    # already sitting in the filter bar a few pixels above, so repeating them
    # only pushes the register itself further down. Hidden on screen, shown
    # when printed — the legend stays visible in both, since the letters are
    # meaningless without it.
    return (
        "<style>"
        "  .tb-print-title { display: none; }"
        "  @media print { .tb-print-title { display: block !important; } }"
        "</style>"
        "<div class='tb-print-title' style='text-align:center;line-height:1.5;margin-bottom:6px'>"
        f"<div style='font-size:15px;font-weight:700'>{frappe.utils.escape_html(name)}</div>"
        f"<div style='font-weight:600'>Attendance Register for {period}</div>"
        "</div>"
        f"<div style='text-align:center;font-size:11px;color:#777'>{LEGEND}</div>"
    )


def resolve_period(filters):

    if filters.get("month") and filters.get("year"):
        return cint(filters.month), cint(filters.year)

    today = getdate()

    return today.month, today.year


def day_columns(year, month, days, off_days):

    columns = [
        # No serial column of our own: Frappe numbers every row already, and a
        # second count beside it looks like a mistake — it was also being
        # summed into a meaningless total at the foot of the page.
        {"label": "Code", "fieldname": "employee_code", "fieldtype": "Data", "width": 70},
        {"label": "Full Name Of The Employee", "fieldname": "employee_name",
         "fieldtype": "Data", "width": 190},
    ]

    for day in range(1, days + 1):

        columns.append({
            # Just the number. "1 W" ran together into something unreadable,
            # and the weekly off is now shown by shading the header instead.
            "label": str(day),
            "fieldname": f"day_{day}",
            "fieldtype": "Data",
            # 38px could not fit a two-digit date beside the sort marker, so
            # every day past the 9th showed as "1...".
            "width": 50,
            # Read by the client formatter to shade the whole column, so a
            # weekly off is obvious at a glance instead of having to count
            # across thirty-one narrow boxes.
            "weekly_off": 1 if day in off_days else 0,
        })

    columns += [
        {"label": "Total Month Day", "fieldname": "month_days", "fieldtype": "Int", "width": 90},
        {"label": "P", "fieldname": "total_present", "fieldtype": "Int", "width": 45},
        {"label": "P/A", "fieldname": "total_half", "fieldtype": "Int", "width": 55},
        {"label": "L", "fieldname": "total_leave", "fieldtype": "Int", "width": 45},
        {"label": "A", "fieldname": "total_absent", "fieldtype": "Int", "width": 45},
    ]

    return columns


def day_records(employees, year, month):
    """Attendance for the month, keyed by (employee, day-of-month)."""

    first = getdate(f"{year}-{month:02d}-01")
    last = get_last_day(first)

    rows = frappe.db.sql(
        """
        SELECT att.employee, DAY(att.attendance_date) AS day, att.status,
               att.total_hours, att.leave_type, lv.is_paid, lv.half_day
        FROM `tabTimeBridge Attendance` att
        LEFT JOIN `tabTimeBridge Leave` lv
               ON lv.employee = att.employee
              AND lv.approval_status = 'Approved'
              AND att.attendance_date BETWEEN lv.from_date AND lv.to_date
        WHERE att.employee IN %(employees)s
          AND att.attendance_date BETWEEN %(first)s AND %(last)s
        """,
        {"employees": [e.name for e in employees], "first": first, "last": last},
        as_dict=True,
    )

    return {(r.employee, r.day): r for r in rows}


def weekly_off_dates(year, month, days):
    """
    Which days of this month are weekly offs.

    Read from the same setting attendance uses, so the register cannot
    disagree with the records it is printing.
    """

    from timebridge.timebridge.services.attendance_sync import weekly_off_days

    off_weekdays = weekly_off_days()

    return {
        day
        for day in range(1, days + 1)
        if calendar.weekday(year, month, day) in off_weekdays
    }


def day_rows(employees, records, off_days, days, month, year):

    data = []

    for emp in employees:

        row = {
            "employee": emp.name,
            "employee_code": emp.employee_code,
            "employee_name": emp.employee_name,
            "month_days": days,
        }

        present = absent = leave = half = 0

        for day in range(1, days + 1):

            record = records.get((emp.name, day))

            if not record:
                # A weekly off with no record is still a weekly off; anything
                # else genuinely has no information and is left blank rather
                # than guessed at.
                row[f"day_{day}"] = WEEKLY_OFF_CODE if day in off_days else NO_RECORD_CODE
                continue

            code = STATUS_CODE.get(record.status, "?")

            if record.status == "On Leave" and (record.leave_type or "") == "Sick Leave":
                code = SICK_LEAVE_CODE

            row[f"day_{day}"] = code

            if record.status == "Present":
                present += 1

            elif record.status == "Half Day":
                half += 1

            elif record.status == "Absent":
                absent += 1

            elif record.status == "On Leave":
                leave += 1

        row["total_present"] = present
        row["total_half"] = half
        row["total_absent"] = absent
        row["total_leave"] = leave

        data.append(row)

    return data

