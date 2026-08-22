# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Persistence for records that arrived over ADMS push.

Writes into the same TimeBridge Punch Log / Machine User tables the pull path
will use, so push and pull are only a transport difference. Idempotency comes
from the unique punch_key column, checked here before insert and enforced by
the database if two requests race.
"""

import frappe

from frappe.utils import cint, get_datetime, now_datetime

from timebridge.timebridge.doctype.timebridge_punch_log.timebridge_punch_log import (
    build_punch_key,
)

SOURCE_ADMS = "ADMS Push"


def get_machine_by_serial(serial):
    """
    Inbound requests identify themselves by serial number, never by IP, so this
    is the only join available. Returns None for an unknown device; the caller
    must not create records for devices nobody registered.
    """

    if not serial:
        return None

    return frappe.db.get_value(
        "Biometric Machine",
        {"serial_number": serial},
        "name",
    )


def save_punches(machine, records, sync_batch=None, save_raw=None):
    """
    Insert punch records, skipping any already stored.

    Returns a dict of counts. Unmatched users are stored anyway — a punch whose
    device_user_id has no Machine User yet is still evidence someone was at the
    door, and dropping it would lose data permanently.
    """

    if save_raw is None:
        save_raw = cint(
            frappe.db.get_single_value("TimeBridge Settings", "save_raw_events")
        )

    sync_batch = sync_batch or now_datetime().strftime("%Y-%m-%d %H:%M:%S")

    created = 0
    duplicates = 0
    invalid = 0
    unmatched = 0

    for record in records:

        try:
            timestamp = get_datetime(record["timestamp"])
        except Exception:
            invalid += 1
            continue

        punch_key = build_punch_key(machine, record["device_user_id"], timestamp)

        if frappe.db.exists("TimeBridge Punch Log", {"punch_key": punch_key}):
            duplicates += 1
            continue

        # Both links are resolved here, not just the machine user. Attendance,
        # the reports and every per-person view join on employee — a punch that
        # only knows its Machine User is invisible to all of them.
        mapping = frappe.db.get_value(
            "Machine User",
            {"machine": machine, "user_id": record["device_user_id"]},
            ["name", "employee"],
            as_dict=True,
        )

        machine_user = mapping.name if mapping else None
        employee = mapping.employee if mapping else None

        if not machine_user:
            unmatched += 1

        doc = frappe.get_doc({
            "doctype": "TimeBridge Punch Log",
            "machine": machine,
            "device_user_id": record["device_user_id"],
            "machine_user": machine_user,
            "employee": employee,
            "employee_name": (
                frappe.db.get_value("Employee", employee, "employee_name")
                if employee else None
            ),
            "timestamp": timestamp,
            "punch_direction": record.get("punch_direction") or "Unknown",
            "verify_mode": record.get("verify_mode"),
            "device_status": record.get("device_status"),
            "source": SOURCE_ADMS,
            "sync_batch": sync_batch,
            "raw_payload": record.get("raw") if save_raw else None,
        })

        try:
            doc.insert(ignore_permissions=True)
            created += 1

        except frappe.exceptions.UniqueValidationError:
            # Another request inserted the same punch between the check above
            # and this insert. Harmless, and exactly what the constraint is for.
            duplicates += 1

    return {
        "created": created,
        "duplicates": duplicates,
        "invalid": invalid,
        "unmatched": unmatched,
        "sync_batch": sync_batch,
    }


def save_users(machine, records):
    """
    Upsert Machine User rows on (machine, user_id) — the pair the DocType
    already guards against duplicates.

    Only fields the device actually reported are written, so a later pull sync
    that knows more (finger counts, face enrolment) is not overwritten with
    blanks.
    """

    created = 0
    updated = 0

    for record in records:

        existing = frappe.db.get_value(
            "Machine User",
            {"machine": machine, "user_id": record["user_id"]},
            "name",
        )

        if existing:

            changes = {}
            current = frappe.db.get_value(
                "Machine User", existing, ["user_name", "card_number", "privilege"], as_dict=True
            )

            if record.get("user_name") and record["user_name"] != current.user_name:
                changes["user_name"] = record["user_name"]

            if record.get("card_number") and record["card_number"] != current.card_number:
                changes["card_number"] = record["card_number"]

            if record.get("privilege") and record["privilege"] != current.privilege:
                changes["privilege"] = record["privilege"]

            if changes:
                frappe.db.set_value("Machine User", existing, changes)
                updated += 1

            continue

        frappe.get_doc({
            "doctype": "Machine User",
            "machine": machine,
            "user_id": record["user_id"],
            "user_name": record["user_name"],
            "card_number": record.get("card_number"),
            "privilege": record.get("privilege") or "User",
            "is_active": 1,
        }).insert(ignore_permissions=True)

        created += 1

    return {"created": created, "updated": updated}


def link_unmatched_punches(machine):
    """
    Fill machine_user and employee on punches that are missing either.

    ADMS devices commonly upload punches before USERINFO, so this backfill is
    the normal path rather than a repair job. It also catches punches stored
    before their Machine User was mapped to an Employee — that mapping usually
    happens later, and without this those punches stay invisible to attendance
    and every report forever.
    """

    unmatched = frappe.get_all(
        "TimeBridge Punch Log",
        filters={
            "machine": machine,
            "employee": ("is", "not set"),
        },
        fields=["name", "device_user_id", "machine_user"],
        limit=20000,
    )

    linked = 0

    for punch in unmatched:

        mapping = frappe.db.get_value(
            "Machine User",
            {"machine": machine, "user_id": punch.device_user_id},
            ["name", "employee"],
            as_dict=True,
        )

        if not mapping:
            continue

        updates = {}

        if not punch.machine_user:
            updates["machine_user"] = mapping.name

        if mapping.employee:
            updates["employee"] = mapping.employee
            updates["employee_name"] = frappe.db.get_value(
                "Employee", mapping.employee, "employee_name"
            )

        if updates:
            frappe.db.set_value("TimeBridge Punch Log", punch.name, updates)
            linked += 1

    return linked


def open_sync_log(machine, sync_type, sync_batch):
    """Record that a push arrived, before doing the work."""

    doc = frappe.get_doc({
        "doctype": "TimeBridge Sync Log",
        "machine": machine,
        "sync_type": sync_type,
        "status": "Running",
        "started_at": now_datetime(),
        "sync_batch": sync_batch,
    })

    doc.insert(ignore_permissions=True)

    return doc.name


def close_sync_log(name, status, fetched=0, created=0, skipped=0, error=None):

    if not name:
        return

    frappe.db.set_value("TimeBridge Sync Log", name, {
        "status": status,
        "finished_at": now_datetime(),
        "records_fetched": fetched,
        "records_created": created,
        "records_skipped": skipped,
        "error_message": error,
    })
