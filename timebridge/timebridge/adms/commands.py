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

from frappe.utils import cint, now_datetime

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
    
    Kept as the first bulk dialect. Fetch All now queues every dialect in
    user_query_round() — this firmware collects a bare DATA QUERY USERINFO
    and sends nothing, the same way it ignores CHECK.
    """

    return "DATA QUERY USERINFO"

USER_FETCH_TTL = 1800
USER_FETCH_ROUNDS = 2
USER_FETCH_PIN_CAP = 150


def user_fetch_key(machine):

    return f"timebridge_user_fetch::{machine}"


def user_query_round(machine, round_no, start=None, end=None):
    """
    User-list queries, in the dialects this firmware family uses.

    Bare DATA QUERY USERINFO is collected and answered with nothing, like
    CHECK. ATTLOG started working once it used tabs plus a date range, so
    OPERLOG / USERINFO get the same shape first. Later rounds copy the photo
    fetch: comma form, then one PIN= query per id already seen on a punch —
    a new site has punches before it has TimeBridge Machine Users.
    """

    if round_no == 1:

        commands = []

        if start and end:
            commands.extend([
                f"DATA QUERY OPERLOG StartTime={start}\tEndTime={end}",
                f"DATA QUERY USERINFO StartTime={start}\tEndTime={end}",
            ])

        commands.extend([
            "DATA QUERY tablename=userinfo\tfielddesc=*\tfilter=*",
            "DATA QUERY tablename=user\tfielddesc=*\tfilter=*",
            "DATA QUERY USERINFO PIN=*",
        ])

        return commands

    if round_no == 2:

        return [
            "DATA QUERY tablename=userinfo,fielddesc=*,filter=*",
            "DATA QUERY tablename=user,fielddesc=*,filter=*",
            "DATA QUERY USERINFO",
            "DATA QUERY OPERLOG",
        ]

    # Remaining ids are asked one per poll in advance_user_fetch, not here.
    return []


def punch_pins(machine):
    """Device user ids that have actually punched — names may still be missing."""

    return [
        pin
        for pin in frappe.get_all(
            "TimeBridge Punch Log",
            filters={"machine": machine, "device_user_id": ["!=", ""]},
            pluck="device_user_id",
            distinct=True,
            order_by="device_user_id",
        )
        if pin
    ]


def missing_user_pins(machine):
    """Punch ids with no TimeBridge Machine User yet. Empty list means the list is complete."""

    pins = punch_pins(machine)
    have = set(
        frappe.get_all(
            "TimeBridge Machine User",
            filters={"machine": machine},
            pluck="user_id",
        )
    )
    return [pin for pin in pins if pin not in have]


def start_user_fetch(machine, start, end, baseline=0):
    """
    Remember that Fetch All still wants names after the attendance dump.

    Round 0 means the ATTLOG command is in the queue; user dialects wait
    until the device has collected that, so they are not ignored the way a
    USERINFO+ATTLOG pair was on this hardware.
    """

    frappe.cache().set_value(
        user_fetch_key(machine),
        {
            "round": 0,
            "baseline": cint(baseline),
            "start": start,
            "end": end,
        },
        expires_in_sec=USER_FETCH_TTL,
    )


def advance_user_fetch(machine, users_now=None, drip=True):
    """
    Queue the next user-list work until every punch id has a name.

    Bulk dialects (rounds 1–2) are queued in full but handed to the device
    one command per poll. After that, missing ids are asked as
    DATA QUERY USERINFO PIN=<id> — one per poll — because a bundle is
    ignored after the first answer.

    drip=False skips the PIN loop so the form's 2s poll cannot flood the
    queue between device check-ins.
    """

    if pending_count(machine):
        return None

    state = frappe.cache().get_value(user_fetch_key(machine)) or {}

    if not state:
        return None

    pins = punch_pins(machine)
    missing = missing_user_pins(machine)

    if pins and not missing:
        frappe.cache().delete_value(user_fetch_key(machine))
        return None

    current = cint(state.get("round") or 0)

    if current < USER_FETCH_ROUNDS:
        nxt = current + 1
        queued = user_query_round(
            machine,
            nxt,
            start=state.get("start"),
            end=state.get("end"),
        )

        if not queued:
            state["round"] = nxt
            frappe.cache().set_value(
                user_fetch_key(machine), state, expires_in_sec=USER_FETCH_TTL
            )
            return nxt

        for command in queued:
            queue_command(machine, command)

        state["round"] = nxt
        frappe.cache().set_value(
            user_fetch_key(machine), state, expires_in_sec=USER_FETCH_TTL
        )
        return nxt

    if not drip or not missing:
        return None

    queue_command(machine, f"DATA QUERY USERINFO PIN={missing[0]}")
    return current

    

def update_user(pin, name, privilege="User", card=None):
    """
    Create or update one person on a push device.

    Wire format proven on modern ADMS firmware (DATA UPDATE USERINFO with
    tab-separated fields). Legacy "USER ADD" is rejected with -1002 on many
    units, so it is not used here.

    Privilege on the wire is 0 for a normal user and 14 for an administrator —
    the same numbers pyzk uses, and the same two values TimeBridge Machine User
    stores as labels.
    """

    pri = 14 if (privilege or "") == "Admin" else 0
    card = (card or "").strip() or "0"
    name = (name or "").strip() or f"User {pin}"

    return (
        f"DATA UPDATE USERINFO PIN={pin}\tName={name}\tPrivilege={pri}\tCard={card}"
    )


def resend_attendance_between(start, end):
    """
    Narrower form of the above, for one date range.

    Tab-separated arguments — the firmware splits on tabs, so a space here
    silently truncates the range and it re-sends everything instead.
    """

    return f"DATA QUERY ATTLOG StartTime={start}\tEndTime={end}"


PHOTO_FETCH_TTL = 600
PHOTO_FETCH_ROUNDS = 3


def photo_fetch_key(machine):

    return f"timebridge_photo_fetch::{machine}"


def photo_query_round(machine, round_no):
    """
    Enrolment-picture queries, in the dialects this firmware family uses.

    Round 1 uses tabs: the same split ATTLOG already proved on this device.
    Comma form was tried first and collected with no pictures coming back.
    Round 3 asks per PIN, which is how Bio-Photo import gets faces the bulk
    query will not re-send.
    """

    if round_no == 1:

        return [
            "DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=*",
            "DATA QUERY tablename=userpic\tfielddesc=*\tfilter=*",
            "DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=Type=9",
        ]

    if round_no == 2:

        return [
            "DATA QUERY tablename=biophoto,fielddesc=*,filter=*",
            "DATA QUERY tablename=userpic,fielddesc=*,filter=*",
            "DATA QUERY USERPIC",
            "DATA QUERY BIOPHOTO",
        ]

    pins = frappe.get_all(
        "TimeBridge Machine User",
        filters={"machine": machine},
        pluck="user_id",
    )

    commands = []

    for pin in pins:

        if not pin:
            continue

        commands.append(
            f"DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=PIN={pin}"
        )
        commands.append(f"DATA QUERY USERPIC PIN={pin}")

    return commands


def start_enroll_photo_fetch(machine, baseline=0):

    frappe.cache().set_value(
        photo_fetch_key(machine),
        {"round": 1, "baseline": cint(baseline)},
        expires_in_sec=PHOTO_FETCH_TTL,
    )

    for command in photo_query_round(machine, 1):
        queue_command(machine, command)


def advance_enroll_photo_fetch(machine, photos_now=0):
    """
    Queue the next dialect once the device has taken the last batch and still
    sent no enrolment pictures. No-op while commands are waiting, after a
    picture has arrived, or after the last round.
    """

    if pending_count(machine):
        return None

    state = frappe.cache().get_value(photo_fetch_key(machine)) or {}

    if not state:
        return None

    if cint(photos_now) > cint(state.get("baseline")):
        return None

    current = cint(state.get("round") or 1)

    if current >= PHOTO_FETCH_ROUNDS:
        return None

    nxt = current + 1
    commands = photo_query_round(machine, nxt)

    if not commands:
        return None

    for command in commands:
        queue_command(machine, command)

    state["round"] = nxt
    frappe.cache().set_value(
        photo_fetch_key(machine), state, expires_in_sec=PHOTO_FETCH_TTL
    )

    return nxt


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
        "TimeBridge Machine", machine, "last_contact_at", stamp, update_modified=False
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

    stored = frappe.db.get_value("TimeBridge Machine", machine, "last_contact_at")

    if not stored:
        return {}

    return {"at": str(stored)[:19], "kind": "recorded"}


def save_device_registered_users(machine, count):
    """
    Store the enrollment total the device itself reported.

    Separate from TimeBridge Machine User rows: those are names we have
    received, this is how many people the terminal says are enrolled.
    """

    from frappe.utils import cint

    if count is None:
        return

    frappe.db.set_value(
        "TimeBridge Machine",
        machine,
        "device_registered_users",
        cint(count),
        update_modified=False,
    )
    frappe.db.commit()


def pop_one_command(machine):
    """
    Hand over a single command and leave the rest queued.

    This firmware executes one C: line per /iclock/getrequest and ignores
    the rest of a bundle — proven on USERINFO: a batch of PIN= queries
    returned three names and dropped the other thirteen. Punches were
    fine because ATTLOG is already one command.
    """

    pending = frappe.cache().get_value(command_key(machine)) or []

    if not pending:
        return []

    first, rest = pending[0], pending[1:]

    if rest:
        frappe.cache().set_value(command_key(machine), rest, expires_in_sec=COMMAND_TTL)
    else:
        frappe.cache().delete_value(command_key(machine))

    return [first]