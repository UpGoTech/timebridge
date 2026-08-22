# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Commands sent back to a push device.

The device dials out to /iclock/getrequest on a timer asking "anything for
me?". That poll is the only channel we have to it — it never accepts an
incoming connection — so anything we want it to do has to wait here until it
next asks.

That makes this the answer to "the punches were rejected, how do we get them
back?": we cannot fetch them, but we can ask the device to send them again.
"""

import frappe

from frappe.utils import now_datetime

# Commands wait in the cache rather than a DocType: they are meaningful for
# minutes, are consumed exactly once, and a queue that survives a restart
# would re-trigger a bulk re-upload nobody asked for.
COMMAND_TTL = 3600
CONTACT_TTL = 86400


def command_key(machine):
    return f"timebridge_adms_commands::{machine}"


def contact_key(machine):
    return f"timebridge_adms_last_contact::{machine}"


def queue_command(machine, command):
    """
    Add one command for the device to collect on its next poll.

    Returns the id assigned to it, which is what the device quotes back when
    it reports the result.
    """

    pending = frappe.cache().get_value(command_key(machine)) or []

    command_id = (max([c["id"] for c in pending]) + 1) if pending else 1

    pending.append({
        "id": command_id,
        "command": command,
        "queued_at": now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    })

    frappe.cache().set_value(command_key(machine), pending, expires_in_sec=COMMAND_TTL)

    return command_id


def pop_commands(machine):
    """
    Hand over everything waiting and clear the queue.

    Cleared on collection, not on completion: a device that takes a command
    and then fails must not be sent it again on a loop. The user can always
    press the button a second time.
    """

    pending = frappe.cache().get_value(command_key(machine)) or []

    if pending:
        frappe.cache().delete_value(command_key(machine))

    return pending


def pending_count(machine):

    return len(frappe.cache().get_value(command_key(machine)) or [])


def format_commands(commands):
    """
    Render commands in the wire format the firmware expects:

        C:<id>:<command>

    One per line. An empty list must produce "OK" rather than an empty body,
    which some firmwares treat as a protocol error.
    """

    if not commands:
        return "OK"

    return "\n".join(f"C:{c['id']}:{c['command']}" for c in commands)


def resend_all_attendance():
    """
    Kept for reference: CHECK is the firmware's documented "re-send what you
    have" instruction.

    **It does not work on the AIFace MARS.** Tested 2026-08-01: the device
    collects the command and answers with nothing, because it already counts
    those records as delivered — we acknowledged them earlier while its serial
    was unrecognised, and that advanced its pointer for good.

    Use resend_attendance_between() instead. An explicit date range ignores the
    delivered pointer, and the same device returned 15 punches within seconds.
    """

    return "CHECK"


def request_users():
    """
    Ask for the enrolled user list.

    Worth doing alongside any attendance request: punches carry only a numeric
    id, so without this every row reads "user 11" instead of a name.
    link_unmatched_punches() then joins up punches that arrived first.
    """

    return "DATA QUERY USERINFO"


def resend_attendance_between(start, end):
    """
    Narrower form of the above, for one date range.

    Tab-separated arguments — the firmware splits on tabs, so a space here
    silently truncates the range and it re-sends everything instead.
    """

    return f"DATA QUERY ATTLOG StartTime={start}\tEndTime={end}"


def record_contact(machine, kind):
    """
    Remember that the device just spoke to us, and how.

    Without this there is no way to tell "the device is silent" from "the
    device is fine and has nothing to say" — the two look identical, and the
    difference decides whether you go and look at the hardware.

    Written to the record as well as the cache. The cache alone was not enough:
    `bench migrate` and `bench clear-cache` wipe it, and a device that had been
    polling happily all day would suddenly read as "has never contacted us" —
    and then get marked Disconnected by the status refresh.
    """

    stamp = now_datetime()

    frappe.cache().set_value(
        contact_key(machine),
        {
            "at": stamp.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": kind
        },
        expires_in_sec=CONTACT_TTL
    )

    frappe.db.set_value(
        "Biometric Machine", machine, "last_contact_at", stamp, update_modified=False
    )
    frappe.db.commit()


def last_contact(machine):
    """
    When the device last spoke — from the cache if it is warm, from the record
    if it is not, so a cleared cache reports the truth rather than "never".
    """

    cached = frappe.cache().get_value(contact_key(machine))

    if cached:
        return cached

    stored = frappe.db.get_value("Biometric Machine", machine, "last_contact_at")

    if not stored:
        return {}

    return {"at": str(stored)[:19], "kind": "recorded"}
