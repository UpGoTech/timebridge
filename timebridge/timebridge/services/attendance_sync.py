# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Turn raw punches into one attendance row per employee per day.

The device tells us almost nothing beyond "person X was at the terminal at
time T": it never reports a direction — every punch carries status 255 — and
it sends each punch twice, about a second apart. Both facts are handled here
rather than being pushed onto whoever reads the report.

Direction is derived, not invented: the first surviving punch of a day is the
In, the last is the Out, and everything between stays Unknown because a
mid-day scan genuinely does not tell us which way someone was walking.
"""

import frappe

from frappe.utils import cint, flt, get_datetime, getdate, time_diff_in_seconds

# TimeBridge Settings has never been saved, so every field there reads back as
# 0/None. Same guard pyzk_connector.py and device_info.py already use.
DEFAULT_DUPLICATE_WINDOW = 60

# Used only when TimeBridge Settings has never been saved and reads back 0.
DEFAULT_HALF_DAY_HOURS = 4.0

# Python's weekday(): Monday is 0, Sunday is 6.
WEEKDAY_FIELDS = {
    0: "weekly_off_monday",
    1: "weekly_off_tuesday",
    2: "weekly_off_wednesday",
    3: "weekly_off_thursday",
    4: "weekly_off_friday",
    5: "weekly_off_saturday",
    6: "weekly_off_sunday",
}

# A day with a single punch cannot produce hours. Kept explicit so the reason
# shows up in the record instead of a silent zero.
SINGLE_PUNCH_REMARK = (
    "Only one punch recorded — no out time, so hours cannot be calculated. "
    "Almost always a forgotten punch-out rather than a genuine half day."
)

IN_OFFICE_REMARK = (
    "Punched in and has not punched out yet. Recalculated automatically once "
    "the out punch arrives."
)

ABSENT_REMARK = "No punch recorded on a working day."


def weekly_off_days():
    """
    Which weekdays are non-working, as a set of Python weekday numbers.

    Read from TimeBridge Settings so it can be changed from the UI rather than
    living in code. That Single has never been saved on this site, so a
    completely blank answer falls back to Sunday — which is what four weeks of
    this site's own punch data shows.
    """

    settings = frappe.db.get_singles_dict("TimeBridge Settings") or {}

    days = {
        weekday
        for weekday, fieldname in WEEKDAY_FIELDS.items()
        if cint(settings.get(fieldname))
    }

    return days or {6}


def half_day_hours():

    return flt(
        frappe.db.get_single_value("TimeBridge Settings", "half_day_hours")
    ) or DEFAULT_HALF_DAY_HOURS


def half_day_after():
    """
    Company-wide fallback cutoff, used only when a TimeBridge Shift has not set its own.

    Deliberately optional and off by default: with both blank, every day is
    counted exactly as it was before this rule existed, so switching it on is
    a decision rather than something that happens silently.
    """

    return frappe.db.get_single_value("TimeBridge Settings", "half_day_after_time") or None


def duplicate_window():

    return cint(
        frappe.db.get_single_value("TimeBridge Settings", "duplicate_punch_window")
    ) or DEFAULT_DUPLICATE_WINDOW


def build_attendance_key(employee, date):
    """One row per employee per day — the key that makes rebuilds idempotent."""

    return f"{employee}::{getdate(date)}"


def collapse_duplicates(punches, window):
    """
    Drop punches that repeat within `window` seconds of the one before.

    This device fires twice per scan (11:04:40 and 11:04:41). Left alone that
    doubles punch_count for everybody and makes a two-scan day look like four.
    """

    kept = []

    for punch in punches:

        if kept and time_diff_in_seconds(punch.timestamp, kept[-1].timestamp) <= window:
            continue

        kept.append(punch)

    return kept


def shift_bounds(shift):
    """
    Start, end, grace and half-day cutoff for a shift.

    grace_time is a field the TimeBridge Shift DocType has always had and nothing used.
    Without it someone arriving at 11:02 on an 11:00 shift is recorded as
    late, which is technically true and practically useless.

    The cutoff lives on the TimeBridge Shift because shifts already group people by when
    they start — a single company-wide time cannot be right for a 10:30 shift
    and an 11:30 one at once.
    """

    if not shift:
        return None, None, 0, None

    row = frappe.db.get_value(
        "TimeBridge Shift",
        shift,
        ["start_time", "end_time", "grace_time", "half_day_after_time"],
        as_dict=True,
    )

    if not row:
        return None, None, 0, None

    return row.start_time, row.end_time, cint(row.grace_time), row.half_day_after_time


def rebuild_for_range(from_date=None, to_date=None, employee=None):
    """
    Rebuild attendance for every employee/day that has punches in the range.

    Returns counts. Re-running is safe: rows are matched on attendance_key and
    updated in place, so the same day never produces two records.
    """

    conditions = ["p.employee IS NOT NULL"]
    values = {}

    if from_date:
        conditions.append("DATE(p.timestamp) >= %(from_date)s")
        values["from_date"] = getdate(from_date)

    if to_date:
        conditions.append("DATE(p.timestamp) <= %(to_date)s")
        values["to_date"] = getdate(to_date)

    if employee:
        conditions.append("p.employee = %(employee)s")
        values["employee"] = employee

    rows = frappe.db.sql(
        f"""
        SELECT p.name, p.employee, p.employee_name, p.timestamp, DATE(p.timestamp) AS day
        FROM `tabTimeBridge Punch Log` p
        WHERE {" AND ".join(conditions)}
        ORDER BY p.employee, p.timestamp
        """,
        values,
        as_dict=True,
    )

    grouped = {}

    for row in rows:
        grouped.setdefault((row.employee, row.day), []).append(row)

    created = updated = 0
    window = duplicate_window()

    for (emp, day), punches in grouped.items():

        if build_day(emp, day, punches, window):
            created += 1
        else:
            updated += 1

    frappe.db.commit()

    return {
        "days": len(grouped),
        "created": created,
        "updated": updated,
        "punches_considered": len(rows),
        "duplicate_window": window,
    }


def build_day(employee, day, punches, window):
    """
    Write one attendance row. Returns True if it was newly created.

    Also stamps direction back onto the punches themselves, so the Punch Log
    stops showing "Unknown" for the two that we can actually name.
    """

    kept = collapse_duplicates(punches, window)

    first = kept[0]
    last = kept[-1] if len(kept) > 1 else None

    employee_name = first.employee_name or frappe.db.get_value(
        "TimeBridge Employee", employee, "employee_name"
    )

    key = build_attendance_key(employee, day)
    existing = frappe.db.get_value(
        "TimeBridge Attendance", {"attendance_key": key}, ["name", "shift"], as_dict=True
    )

    shift = frappe.db.get_value("TimeBridge Employee", employee, "shift")

    # A shift set by hand on this row wins over the employee's default. The
    # scheduler reruns the last few days every 15 minutes, and without this it
    # silently overwrites that edit — the change appears to save and then
    # undoes itself, which is indistinguishable from the field being broken.
    #
    # Resolved here, before any timing is calculated, so late_by and
    # early_exit are measured against the shift actually being kept.
    if existing and existing.shift and existing.shift != shift:
        shift = existing.shift

    start_time, end_time, grace, shift_cutoff = shift_bounds(shift)

    total_hours = 0.0

    if last:
        total_hours = flt(
            time_diff_in_seconds(last.timestamp, first.timestamp) / 3600.0, 2
        )

    late_by = early_exit = 0

    if start_time is not None:
        # Grace is forgiven entirely, not deducted: arriving inside it is
        # simply on time, so late_by is 0 rather than a small positive number
        # that still reads as "late" in a report.
        scheduled_in = get_datetime(f"{day} 00:00:00") + start_time
        minutes_late = int(time_diff_in_seconds(first.timestamp, scheduled_in) // 60)
        late_by = max(minutes_late - grace, 0)

    if end_time is not None and last:
        scheduled_out = get_datetime(f"{day} 00:00:00") + end_time
        early_exit = max(int(time_diff_in_seconds(scheduled_out, last.timestamp) // 60), 0)

    status = "Present"
    remarks = None

    if not last:

        # Today with one punch means the person is still here — the day simply
        # is not over. Flagging that for review would put every present
        # employee on a problem list every morning.
        if getdate(day) == getdate(frappe.utils.today()):
            status = "In Office"
            remarks = IN_OFFICE_REMARK

        else:
            # A past day with one punch is different: the out time is genuinely
            # missing. Still not "Half Day" — we have no evidence they left
            # early, only that they did not scan.
            status = "Needs Review"
            remarks = SINGLE_PUNCH_REMARK

    elif total_hours < half_day_hours():
        status = "Half Day"

    # Second, independent half-day rule: too late to count as a full day, no
    # matter how long they then stayed. Applied only to a day that would
    # otherwise be Present, so it can never upgrade a Half Day or disturb the
    # In Office / Needs Review states, whose outcome is not known yet.
    # The shift's own cutoff wins; the company-wide one is only a fallback
    # for shifts that have not set theirs.
    cutoff = shift_cutoff or half_day_after()

    if cutoff and status == "Present":

        latest_full_day_start = get_datetime(f"{day} 00:00:00") + cutoff

        if first.timestamp > latest_full_day_start:
            status = "Half Day"
            remarks = (
                f"Arrived {first.timestamp.strftime('%H:%M')}, after the "
                f"half-day cutoff — counted as half a day regardless of hours worked."
            )

    payload = {
        "employee": employee,
        "employee_name": employee_name,
        "attendance_date": day,
        "shift": shift,
        "status": status,
        # A day with punches is not a leave day, so this is cleared rather than
        # left holding a stale value from before someone actually turned up.
        "leave_type": None,
        "first_in": first.timestamp,
        "last_out": last.timestamp if last else None,
        "total_hours": total_hours,
        "late_by": late_by,
        "early_exit": early_exit,
        "punch_count": len(kept),
        "remarks": remarks,
        "attendance_key": key,
    }

    if existing:
        frappe.db.set_value("TimeBridge Attendance", existing.name, payload)
        is_new = False

    else:
        frappe.get_doc(dict(payload, doctype="TimeBridge Attendance")).insert(
            ignore_permissions=True
        )
        is_new = True

    stamp_directions(punches, first, last)

    return is_new


def stamp_directions(punches, first, last):
    """
    Mark the day's first punch In and its last Out, and flag them all handled.

    Only these two are named. The rest keep Unknown deliberately — this device
    reports no direction, and guessing one for a mid-day scan would put a value
    in the database that nothing supports.
    """

    for punch in punches:

        direction = "Unknown"

        if punch.name == first.name:
            direction = "In"

        elif last is not None and punch.name == last.name:
            direction = "Out"

        frappe.db.set_value(
            "TimeBridge Punch Log",
            punch.name,
            {"punch_direction": direction, "processed": 1},
            update_modified=False,
        )


def mark_absentees(from_date, to_date, employee=None):
    """
    Write an Absent row for every working day an active employee did not punch.

    Without this, absence is invisible: attendance rows are only ever built
    from days that *have* punches, so someone who never came simply has no
    record and every report silently undercounts. Sundays are skipped, and so
    is anything before a person joined.

    Returns counts. Idempotent through the same attendance_key.
    """

    from frappe.utils import add_days, date_diff, getdate

    from timebridge.timebridge.doctype.timebridge_holiday.timebridge_holiday import (
        holidays_between,
    )
    from timebridge.timebridge.doctype.timebridge_leave.timebridge_leave import (
        leaves_between,
    )

    from_date = getdate(from_date)
    to_date = getdate(to_date)

    off_weekdays = weekly_off_days()
    holidays = holidays_between(from_date, to_date)
    leaves = leaves_between(from_date, to_date, employee=employee)

    filters = {"is_active": 1}

    if employee:
        filters["name"] = employee

    employees = frappe.get_all(
        "TimeBridge Employee",
        filters=filters,
        fields=["name", "employee_name", "shift", "date_of_joining"],
    )

    if not employees:
        return {"created": 0, "skipped_off_days": 0, "already_present": 0}

    # One query rather than one per employee-day: 16 people over a month is
    # nearly 500 lookups otherwise.
    #
    # punch_count is carried along because it decides ownership: a row with
    # punches was built from real attendance and must never be overwritten
    # here, while a row without punches is one this function wrote and may
    # need to change — an Absent day becomes On Leave the moment leave is
    # approved for it.
    existing = {
        row.attendance_key: row
        for row in frappe.get_all(
            "TimeBridge Attendance",
            filters={"attendance_date": ["between", [from_date, to_date]]},
            fields=["name", "attendance_key", "status", "punch_count"],
            limit=100000,
        )
    }

    created = off_days = holiday_days = leave_days = already = 0

    for emp in employees:

        joined = getdate(emp.date_of_joining) if emp.date_of_joining else None

        for offset in range(date_diff(to_date, from_date) + 1):

            day = getdate(add_days(from_date, offset))

            if day.weekday() in off_weekdays:
                off_days += 1
                continue

            if joined and day < joined:
                continue

            key = build_attendance_key(emp.name, day)
            row = existing.get(key)

            # A day that has punches is settled — it was built from what the
            # person actually did, and nothing here may second-guess it.
            if row and cint(row.punch_count) > 0:
                already += 1
                continue

            # A declared holiday is recorded as a holiday, not as everybody
            # failing to turn up. Written rather than skipped so the day is
            # visible in the report instead of being a silent gap.
            leave_type = None

            if day in holidays:
                status = "Holiday"
                remarks = holidays[day]
                holiday_days += 1

            elif (emp.name, day) in leaves:

                leave = leaves[(emp.name, day)]

                # Recorded as On Leave, not Present. The report counts paid
                # leave towards attendance, so pay is unaffected, but the
                # record still shows the person was not at work — which is the
                # only way to see who is taking leave, and how much.
                status = "On Leave"
                leave_type = leave.leave_type
                paid = "paid" if leave.is_paid else "unpaid"
                remarks = f"{leave.leave_type} ({paid})"

                if leave.half_day:
                    remarks += " — half day"

                leave_days += 1

            else:
                status = "Absent"
                remarks = ABSENT_REMARK
                created += 1

            if row:

                # Already the right answer — leave it untouched so the record's
                # modified timestamp does not churn on every scheduled run.
                if row.status == status:
                    already += 1
                    continue

                frappe.db.set_value(
                    "TimeBridge Attendance",
                    row.name,
                    {"status": status, "remarks": remarks, "shift": emp.shift,
                     "leave_type": leave_type},
                )

                row.status = status
                continue

            doc = frappe.get_doc({
                "doctype": "TimeBridge Attendance",
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "attendance_date": day,
                "shift": emp.shift,
                "status": status,
                "leave_type": leave_type,
                "total_hours": 0,
                "punch_count": 0,
                "remarks": remarks,
                "attendance_key": key,
            }).insert(ignore_permissions=True)

            existing[key] = frappe._dict(
                name=doc.name, attendance_key=key, status=status, punch_count=0
            )

    frappe.db.commit()

    return {
        "created": created,
        "holidays_marked": holiday_days,
        "leaves_marked": leave_days,
        "skipped_off_days": off_days,
        "already_present": already,
    }


def refresh_push_device_status():
    """
    Keep push devices' Status honest without anyone pressing a button.

    A push device's Status used to change only when Test Connection ran — and
    that always failed for them, so a device happily sending punches every
    thirty seconds still read "Disconnected" forever. Here the status follows
    the only evidence that means anything: whether it has been in touch.
    """

    from timebridge.timebridge.sdk_connectors.essl_connector import push_device_status
    from timebridge.timebridge.services.connection import PUSH_SDK_TYPES

    changed = 0

    for machine in frappe.get_all(
        "TimeBridge Machine",
        filters={"sdk_type": ["in", list(PUSH_SDK_TYPES)]},
        fields=["name", "status"],
    ):

        should_be = push_device_status(machine.name)

        if machine.status != should_be:
            frappe.db.set_value("TimeBridge Machine", machine.name, "status", should_be)
            changed += 1

    if changed:
        frappe.db.commit()

    return {"updated": changed}


def rebuild_recent(days=7):
    """
    Scheduler entry point: keep the last few days current.

    Builds attendance from punches first, then fills the gaps with Absent —
    that order matters, or a day whose punches arrive late would be marked
    absent and then corrected, flickering in anyone's report in between.
    """

    from frappe.utils import add_days, today

    start = add_days(today(), -cint(days))

    built = rebuild_for_range(from_date=start, to_date=today())

    # Yesterday backwards only. Marking today absent before the day is over
    # would flag everyone who simply has not arrived yet.
    absent = mark_absentees(start, add_days(today(), -1))

    return {"built": built, "absent": absent}
