# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Send TimeBridge Machine User name and id to the device.

Direction is the opposite of Fetch: Frappe holds the master row and the
terminal is updated. Photos and biometric templates are not part of this
path — a JPEG in Desk is not a face template the device can unlock with.
"""

import frappe

from frappe.utils import cint

from timebridge.timebridge.services.connection import get_connector, is_push_device


def send_users_to_device(machine_id):
    """
    Push every Machine User for this terminal onto the hardware.

    ADMS devices collect the commands on their next poll (~30s). PyZK devices
    are dialled and written immediately. Returns a status dict the form dialog
    can show without a second round-trip.
    """

    machine = frappe.get_doc("TimeBridge Machine", machine_id)
    users = machine_users(machine_id)

    if not users:
        return {
            "status": "failed",
            "message": (
                "No TimeBridge Machine Users on this machine. Add them here "
                "first (user id and name), then send again."
            ),
        }

    if is_push_device(machine):
        return send_via_adms(machine, users)

    return send_via_pyzk(machine, users)


def machine_users(machine_id):
    """Rows shaped for both transports: id, name, privilege, card."""

    rows = frappe.get_all(
        "TimeBridge Machine User",
        filters={"machine": machine_id},
        fields=["user_id", "user_name", "privilege", "card_number", "employee"],
        order_by="user_id asc",
    )

    for row in rows:

        # Prefer the linked employee name when the device-side name is empty
        # or still the placeholder "User 3".
        if row.employee and (
            not (row.user_name or "").strip()
            or (row.user_name or "").startswith("User ")
        ):
            emp_name = frappe.db.get_value(
                "TimeBridge Employee", row.employee, "employee"
            )
            if emp_name:
                row.user_name = emp_name

    return [r for r in rows if str(r.user_id or "").strip()]


def send_via_adms(machine, users):
    """
    Queue one DATA UPDATE USERINFO command per person.

    The device must already be polling this site. Serial is required so the
    next getrequest can be matched back to this machine's queue.
    """

    from timebridge.timebridge.adms import commands

    if not machine.serial_number:
        return {
            "status": "failed",
            "message": (
                "This machine has no serial number, so the device cannot collect "
                "the commands. Fill in Serial Number first."
            ),
        }

    queued = 0

    for row in users:
        commands.queue_command(
            machine.name,
            commands.update_user(
                pin=str(row.user_id).strip(),
                name=row.user_name,
                privilege=row.privilege,
                card=row.card_number,
            ),
        )
        queued += 1

    contact = commands.last_contact(machine.name) or {}

    return {
        "status": "queued",
        "mode": "push",
        "queued": queued,
        "serial": machine.serial_number,
        "last_contact": contact.get("at"),
        "message": (
            f"Queued {queued} user(s) for the device. It will collect them on "
            "its next poll (about every 30 seconds). Name and id only — photos "
            "are not sent this way."
        ),
    }


def send_via_pyzk(machine, users):
    """Dial the terminal and write each user with pyzk set_user."""

    connector = get_connector(machine)
    conn = None

    try:
        conn = connector.connect(machine)
        result = connector.set_users(conn, users)

    except Exception as e:
        return {
            "status": "failed",
            "mode": "pull",
            "message": f"Could not write users to the device: {e}",
        }

    finally:
        if conn:
            try:
                connector.disconnect(conn)
            except Exception:
                frappe.log_error(
                    title="TimeBridge: Device Disconnect Error",
                    message=frappe.get_traceback(),
                )

    failed = result.get("failed") or []
    written = cint(result.get("written"))

    if failed and not written:
        return {
            "status": "failed",
            "mode": "pull",
            "written": 0,
            "failed": failed,
            "message": f"Device rejected all {len(failed)} user(s).",
        }

    if failed:
        return {
            "status": "partial",
            "mode": "pull",
            "written": written,
            "failed": failed,
            "message": (
                f"Wrote {written} user(s); {len(failed)} failed. "
                "Name and id only — photos are not sent this way."
            ),
        }

    return {
        "status": "success",
        "mode": "pull",
        "written": written,
        "failed": [],
        "message": (
            f"Wrote {written} user(s) to the device. "
            "Name and id only — photos are not sent this way."
        ),
    }
