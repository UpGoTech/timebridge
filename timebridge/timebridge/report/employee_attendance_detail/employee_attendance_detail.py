# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
One person, one month, every day — with the times.

The Attendance Register answers "who was here" across the whole company, one
letter per day. It cannot answer "what time did she actually arrive on the
14th", because a letter has no room for a clock. This report is the other half:
a single employee, a single month, and the In and Out behind each letter.

Clicking a name on the register opens this already filtered on that person and
that month, so the two read as one thing rather than two reports to line up by
hand.
"""

import calendar

import frappe

from frappe.utils import cint, flt, getdate

from timebridge.timebridge.report.attendance_report.attendance_report import (
    NO_RECORD_CODE,
    SICK_LEAVE_CODE,
    STATUS_CODE,
    WEEKLY_OFF_CODE,
    weekly_off_dates,
)


def execute(filters=None):

    filters = frappe._dict(filters or {})

    employee = filters.get("employee")
    month, year = resolve_period(filters)

    columns = get_columns()

    if not employee:

        # Without a person this report has nothing to be about. Saying so beats
        # an empty grid that looks like an employee with no attendance.
        #
        # The empty summary list matters: Frappe only clears the cards when it
        # is sent something, so omitting it would leave the last employee's
        # numbers sitting above an empty table.
        return columns, [], no_employee_message(), None, []

    days = calendar.monthrange(year, month)[1]

    rows = build_rows(employee, year, month, days)
    totals = summarise(rows)

    return (
        columns,
        rows,
        heading(employee, month, year),
        None,
        report_summary(totals),
    )


def resolve_period(filters):

    if filters.get("month") and filters.get("year"):
        return cint(filters.month), cint(filters.year)

    today = getdate()

    return today.month, today.year


def get_columns():

    return [
        {"label": "Date", "fieldname": "attendance_date", "fieldtype": "Date", "width": 100},
        {"label": "Day", "fieldname": "day_name", "fieldtype": "Data", "width": 60},
        {"label": "Status", "fieldname": "status_code", "fieldtype": "Data", "width": 70},
        # Data rather than Time: only the clock face is wanted, and a blank
        # must stay genuinely blank on the days nobody punched.
        {"label": "In", "fieldname": "first_in", "fieldtype": "Data", "width": 70},
        {"label": "Out", "fieldname": "last_out", "fieldtype": "Data", "width": 70},
        {"label": "Punches", "fieldname": "punch_count", "fieldtype": "Int", "width": 80},
        {"label": "Remarks", "fieldname": "remarks", "fieldtype": "Data", "width": 220},
    ]

    # Hours, Late and Early were columns here. They are derived from the two
    # times either side of them — a reader who wants to know how late someone
    # was can see it against the shift printed in the heading — and three
    # columns of arithmetic were crowding out the thing this report is for.


def build_rows(employee, year, month, days):
    """
    One row per calendar day, whether or not anything was recorded.

    Listing only the days that have records would quietly hide the days that
    do not — and a missing day is exactly what someone opens this to find.
    """

    from timebridge.timebridge.doctype.timebridge_holiday.timebridge_holiday import (
        holidays_between,
    )
    from timebridge.timebridge.doctype.timebridge_leave.timebridge_leave import (
        leaves_between,
    )

    first = getdate(f"{year}-{month:02d}-01")
    last = getdate(f"{year}-{month:02d}-{days:02d}")

    records = day_records(employee, first, last)
    holidays = holidays_between(first, last)
    off_days = weekly_off_dates(year, month, days)

    # Whether a day off is paid decides the Payable Days card, and that answer
    # lives on the leave record rather than on the attendance row.
    leaves = leaves_between(first, last, employee=employee)

    rows = []

    for day in range(1, days + 1):

        date = getdate(f"{year}-{month:02d}-{day:02d}")
        record = records.get(date)

        row = {
            "attendance_date": date,
            "day_name": calendar.day_abbr[date.weekday()],
            "first_in": None,
            "last_out": None,
            "punch_count": 0,
            "remarks": None,
        }

        if not record:

            # No record is not the same as no information. A Sunday is a rest
            # day and a gazetted holiday is a holiday; only a genuinely unknown
            # working day is left blank.
            if date in holidays:
                row["status_code"] = STATUS_CODE["Holiday"]
                row["remarks"] = holidays[date]

            elif day in off_days:
                row["status_code"] = WEEKLY_OFF_CODE

            else:
                row["status_code"] = NO_RECORD_CODE

            rows.append(row)
            continue

        code = STATUS_CODE.get(record.status, "?")

        # Sick leave is the one with a paid quota, so it is worth telling apart
        # from the rest at a glance — same rule the register uses.
        if record.status == "On Leave" and (record.leave_type or "") == "Sick Leave":
            code = SICK_LEAVE_CODE

        leave = leaves.get((employee, date))

        row.update({
            "status_code": code,
            "status": record.status,
            # Carried for the summary only; the table shows it in Remarks,
            # which attendance already writes as "Sick Leave (paid)".
            "leave_is_paid": cint(leave.is_paid) if leave else 0,
            "leave_is_half": cint(leave.half_day) if leave else 0,
            "first_in": clock(record.first_in),
            "last_out": clock(record.last_out),
            "punch_count": cint(record.punch_count),
            "remarks": record.remarks,
        })

        rows.append(row)

    return rows


def clock(value):
    """Just the time. The date is already the first column of the row."""

    return str(value)[11:16] if value else None


def day_records(employee, first, last):

    rows = frappe.db.sql(
        """
        SELECT
            attendance_date, status, leave_type, first_in, last_out,
            total_hours, late_by, early_exit, punch_count, remarks
        FROM `tabTimeBridge Attendance`
        WHERE employee = %(employee)s
          AND attendance_date BETWEEN %(first)s AND %(last)s
        """,
        {"employee": employee, "first": first, "last": last},
        as_dict=True,
    )

    return {getdate(r.attendance_date): r for r in rows}


def summarise(rows):
    """
    The month in five numbers, counted from the rows already on screen.

    Counted here rather than queried again so the cards can never disagree
    with the table under them.
    """

    totals = {"present": 0, "half": 0, "absent": 0, "leave": 0, "payable": 0.0}

    for row in rows:

        status = row.get("status")

        if status == "Present":
            totals["present"] += 1
            totals["payable"] += 1

        elif status == "Half Day":
            totals["half"] += 1
            totals["payable"] += 0.5

        elif status == "Absent":
            totals["absent"] += 1

        elif status == "On Leave":

            totals["leave"] += 1

            # Paid leave counts as present, by decision: a day the company pays
            # for in full should not read as a gap in someone's attendance.
            #
            # It is therefore counted twice on purpose — once in Present and
            # once in On Leave — so the cards cannot be added across. On Leave
            # is kept because it is the only place a paid day off is still
            # visible as a day off, and the register writes S on that date
            # either way.
            if row.get("leave_is_paid"):

                part = 0.5 if row.get("leave_is_half") else 1

                totals["present"] += part
                totals["payable"] += part

    return totals


def card(label, value, indicator):
    """
    A number card, shown as a whole number when it is one.

    Present and Payable Days can land on a half — a half-day, or half a day of
    paid leave — but most months they do not, and "17.0 days present" reads
    like a machine talking.
    """

    value = flt(value, 1)
    whole = value == cint(value)

    return {
        "label": label,
        "value": cint(value) if whole else value,
        "datatype": "Int" if whole else "Float",
        "indicator": indicator,
    }


def report_summary(totals):

    return [
        card("Present", totals["present"], "Green"),
        card("Half Day", totals["half"], "Orange"),
        # Red only when there is something to be red about, so the card is a
        # signal rather than permanent decoration.
        card("Absent", totals["absent"], "Red" if totals["absent"] else "Grey"),
        card("On Leave", totals["leave"], "Blue"),
        card("Payable Days", totals["payable"], "Green"),
    ]

    # Total Hours and Late Days were cards here too, on a second row. Both are
    # already in the table below, column by column and day by day, where they
    # can be read against the date that produced them — a single month total
    # for hours answers no question anyone was asking.


def heading(employee, month, year):

    emp = frappe.db.get_value(
        "TimeBridge Employee", employee, ["employee", "employee_code", "shift"], as_dict=True
    ) or frappe._dict()

    shift = ""

    if emp.shift:

        bounds = frappe.db.get_value("TimeBridge Shift", emp.shift, ["shift_name", "start_time", "end_time"],
                                     as_dict=True)

        if bounds:

            # The shift is what Late and Early are measured against, so a page
            # full of "23 minutes late" is unreadable without it on the page.
            label = frappe.utils.escape_html(bounds.shift_name or emp.shift)
            hours = f"{str(bounds.start_time)[:5]}–{str(bounds.end_time)[:5]}"

            # Shifts here are often named after their own hours ("11:00 -
            # 19:00"), and printing both reads as a stutter.
            if str(bounds.start_time)[:5] not in label:
                label = f"{label} {hours}"

            shift = f" &nbsp;·&nbsp; {label}"

    period = f"{calendar.month_name[month]} {year}"
    code = f" &nbsp;·&nbsp; Code {frappe.utils.escape_html(emp.employee_code)}" if emp.employee_code else ""

    return (
        "<div style='text-align:center;line-height:1.6;margin-bottom:4px'>"
        f"<div style='font-size:15px;font-weight:700'>"
        f"{frappe.utils.escape_html(emp.employee or employee)}</div>"
        f"<div style='font-size:12px;color:#777'>{period}{code}{shift}</div>"
        "</div>"
    )


def no_employee_message():

    return (
        "<div style='text-align:center;color:#777;padding:8px'>"
        "Pick an employee to see their day-by-day attendance."
        "</div>"
    )
