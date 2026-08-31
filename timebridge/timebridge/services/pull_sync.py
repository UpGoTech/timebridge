# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Pull sync: users and punches read off a device we dial ourselves.

The mirror image of adms/, where the device drives everything. Here Frappe
opens the session, reads the device out, and closes it. Both paths store
through adms/logger.py into the same tables, so `source` on a punch is the only
record of which transport carried it.

Two decisions shape this module.

**Reading and writing are separated.** The ZK protocol requires the terminal to
be disabled while it is read, so nobody can punch while we hold the session.
Reading 46k records takes seconds; inserting them takes minutes. So the device
is emptied into memory, released, and only then is the database touched — the
terminal is offline for the short part, not the long one.

**Progress goes through the cache, not realtime.** socketio binds IPv6 under
WSL2 and never reaches the browser here, so the form polls instead. Same
reasoning, same shape as services/device_info.py.
"""

import frappe

from frappe.utils import add_to_date, cint, get_datetime, now_datetime

from timebridge.timebridge.adms import logger
from timebridge.timebridge.services.connection import get_connector, is_push_device
from timebridge.timebridge.services.device_info import (
    failure_reason,
    job_timeout,
    probe_socket,
    set_machine_status,
    uses_udp,
)
from timebridge.timebridge.services.machine_log import write_machine_log

PULL_SYNC_EVENT = "timebridge_pull_sync"

SOURCE_PYZK = "PyZK Pull"

# Punches are stored in batches, each one committed. A run killed part way
# through therefore keeps what it already wrote, and re-running costs nothing:
# the unique punch_key skips every row already in place.
INSERT_BATCH = 500

# Reading is quick, storing tens of thousands of rows is not, so the
# connector's retry budget is nowhere near the whole story. A worker killed
# mid-insert would leave a half-stored sync — recoverable, but only by
# noticing. This buys the insert phase room to finish.
INSERT_BUDGET_SECONDS = 3600

PROGRESS_TTL = 1800

# Mirrors the four steps in device_info.py and the STEPS array in
# timebridge_machine.js. The client matches on these numbers.
STEP_NETWORK = 1
STEP_CONNECT = 2
STEP_READ = 3
STEP_SAVE = 4
TOTAL_STEPS = 4


def progress_key(machine_id):

    return f"timebridge_pull_sync_progress::{machine_id}"


def set_progress(machine_id, payload):

    frappe.cache().set_value(
        progress_key(machine_id),
        payload,
        expires_in_sec=PROGRESS_TTL
    )


def get_progress(machine_id):

    return frappe.cache().get_value(progress_key(machine_id)) or {}


def pull_job_timeout():
    """Connect budget plus room to store what the device hands over."""

    return job_timeout() + INSERT_BUDGET_SECONDS


def enqueue_pull_sync(machine_id, days=30):
    """
    Queue a full read of a dialable device and return at once.

    Deduplicated per machine: two of these running together would open two
    sessions to one terminal, and connect() disables it on the way in.

    Queued on `long` deliberately. A first pull can be forty thousand rows,
    which would sit on the short queue far past its timeout and be killed
    halfway.
    """

    job_id = f"{PULL_SYNC_EVENT}::{machine_id}"

    run_id = frappe.generate_hash(length=10)

    set_progress(machine_id, {
        "run_id": run_id,
        "status": "queued",
        "stage": "Queued",
        "step": 0,
        "total": TOTAL_STEPS
    })

    job = frappe.enqueue(
        "timebridge.timebridge.services.pull_sync.run_pull_sync_job",
        queue="long",
        job_id=job_id,
        deduplicate=True,
        timeout=pull_job_timeout(),
        machine_id=machine_id,
        days=days,
        user=frappe.session.user,
        run_id=run_id
    )

    # enqueue() returns None when deduplication suppressed the job, meaning a
    # pull is already in flight. Report the run already going rather than the
    # run_id just minted, or the browser waits for something that never reports.
    if job is None:

        running = get_progress(machine_id)

        return {
            "status": "queued",
            "mode": "pull",
            "run_id": running.get("run_id"),
            "message": "A fetch is already running for this machine",
            "timeout": pull_job_timeout()
        }

    return {
        "status": "queued",
        "mode": "pull",
        "job_id": job.id,
        "run_id": run_id,
        "days": cint(days),
        "message": "Fetch queued",
        "timeout": pull_job_timeout()
    }


def enqueue_pull_users(machine_id):
    """
    Queue a users-only read from a dialable device.

    Shares the per-machine deduplication key with a full pull so two sessions
    cannot open to one terminal at once.
    """

    job_id = f"{PULL_SYNC_EVENT}::{machine_id}"

    run_id = frappe.generate_hash(length=10)

    set_progress(machine_id, {
        "run_id": run_id,
        "status": "queued",
        "stage": "Queued",
        "step": 0,
        "total": TOTAL_STEPS
    })

    job = frappe.enqueue(
        "timebridge.timebridge.services.pull_sync.run_pull_users_job",
        queue="long",
        job_id=job_id,
        deduplicate=True,
        timeout=pull_job_timeout(),
        machine_id=machine_id,
        user=frappe.session.user,
        run_id=run_id
    )

    if job is None:

        running = get_progress(machine_id)

        return {
            "status": "queued",
            "mode": "pull",
            "run_id": running.get("run_id"),
            "message": "A fetch is already running for this machine",
            "timeout": pull_job_timeout()
        }

    return {
        "status": "queued",
        "mode": "pull",
        "job_id": job.id,
        "run_id": run_id,
        "message": "User fetch queued",
        "timeout": pull_job_timeout()
    }


def run_pull_users_job(machine_id, user=None, run_id=None):
    """Background entry point for users-only pull."""

    user = user or frappe.session.user

    def on_stage(step, stage, detail=None):
        publish_stage(machine_id, user, step, stage, detail, run_id=run_id)

    on_stage(0, "Background worker picked up the job")

    result = pull_users_only(machine_id, on_stage=on_stage)

    final = dict(result, machine_id=machine_id, run_id=run_id)

    frappe.db.commit()

    set_progress(machine_id, final)

    frappe.publish_realtime(
        PULL_SYNC_EVENT,
        message=final,
        user=user,
        after_commit=True
    )

    return result


def pull_users_only(machine_id, on_stage=None):
    """
    Read enrolled users from a dialable device and store them — no punches.
    """

    def stage(step, text, detail=None):

        if on_stage:
            on_stage(step, text, detail)

    device = frappe.get_doc("TimeBridge Machine", machine_id)

    if is_push_device(device):

        return {
            "status": "failed",
            "failed_step": STEP_CONNECT,
            "message": (
                f"{device.machine_name or device.name} is a push device (SDK Type: "
                "ADMS). Use Fetch users, which asks it to re-send enrolled users."
            )
        }

    port = cint(device.port) or 4370
    udp = uses_udp(device)

    stage(
        STEP_NETWORK,
        "Checking network",
        f"{device.ip_address}:{port}" + (" UDP" if udp else "")
    )

    if udp:
        reachable, detail = True, "udp"
    else:
        reachable, detail = probe_socket(device.ip_address, port)

    if not reachable:

        set_machine_status(device, "Disconnected")
        msg = f"Cannot reach {device.ip_address}:{port} — {detail}"
        write_machine_log(
            machine=machine_id,
            level="Error",
            event="Pull",
            message=msg,
        )

        return {
            "status": "failed",
            "failed_step": STEP_NETWORK,
            "machine_status": "Disconnected",
            "message": msg
        }

    connector = get_connector(device)

    conn = None
    users = []

    try:

        stage(STEP_CONNECT, "Connecting to device")

        conn = connector.connect(
            device,
            on_attempt=lambda attempt, attempts: stage(
                STEP_CONNECT,
                "Connecting to device",
                f"attempt {attempt} of {attempts}"
            )
        )

        stage(STEP_READ, "Reading users from device")

        users = connector.get_users(conn)

        stage(STEP_READ, "Reading users from device", f"{len(users)} users read")

    except Exception as e:

        tb = frappe.get_traceback()
        write_machine_log(
            machine=machine_id,
            level="Error",
            event="Pull",
            message=str(e),
            details=tb,
        )
        frappe.log_error(tb, "TimeBridge: Pull Users Error")

        set_machine_status(device, "Disconnected")

        return {
            "status": "failed",
            "failed_step": STEP_CONNECT if conn is None else STEP_READ,
            "machine_status": "Disconnected",
            "reason": failure_reason(e),
            "message": str(e)
        }

    finally:

        try:
            connector.disconnect(conn)

        except Exception:
            tb = frappe.get_traceback()
            write_machine_log(
                machine=machine_id,
                level="Warning",
                event="Pull",
                message="Device disconnect failed after pull users",
                details=tb,
            )
            frappe.log_error(
                tb,
                "TimeBridge: Device Disconnect Error"
            )

    sync_batch = now_datetime().strftime("%Y-%m-%d %H:%M:%S")

    user_counts = store_users(machine_id, users, sync_batch, stage)

    set_machine_status(device, "Connected")

    return {
        "status": "success",
        "machine_status": "Connected",
        "users": user_counts,
        "message": f"{user_counts.get('created', 0)} new users"
    }


def publish_stage(machine_id, user, step, stage, detail=None, run_id=None):
    """
    Say what the worker is doing now, for the form to pick up on its next poll.

    Written to the cache before the realtime publish, because the cache is the
    channel the browser actually reads. Not after_commit: this job holds one
    transaction across a long insert loop, so deferring these would deliver
    every stage at the very end, which is the same as showing nothing.
    """

    payload = {
        "machine_id": machine_id,
        "run_id": run_id,
        "status": "progress",
        "step": step,
        "total": TOTAL_STEPS,
        "stage": stage,
        "detail": detail
    }

    set_progress(machine_id, payload)

    frappe.publish_realtime(PULL_SYNC_EVENT, message=payload, user=user)


def run_pull_sync_job(machine_id, days=30, user=None, run_id=None):
    """
    Background entry point. A queued job cannot return anything to whoever
    enqueued it, so the outcome is published instead.
    """

    user = user or frappe.session.user

    def on_stage(step, stage, detail=None):
        publish_stage(machine_id, user, step, stage, detail, run_id=run_id)

    # Proof that a worker exists and took the job. Without it, a starved queue
    # and an unreachable device look identical from the form.
    on_stage(0, "Background worker picked up the job")

    result = pull_all_data(machine_id, days=days, on_stage=on_stage)

    final = dict(result, machine_id=machine_id, run_id=run_id)

    frappe.db.commit()

    set_progress(machine_id, final)

    frappe.publish_realtime(
        PULL_SYNC_EVENT,
        message=final,
        user=user,
        after_commit=True
    )

    return result


def pull_all_data(machine_id, days=30, on_stage=None):
    """
    Read a device's users and punches and store them.

    `days` limits how far back punches are kept; 0 means the device's whole
    log. Users are always taken in full — they are few, and a punch whose user
    is missing cannot be attached to an employee.

    Returns a dict with "status", "message" and counts. Safe to run again at
    any time: users are upserted and punches are keyed.

    on_stage(step, stage, detail) is optional so the scheduler and console can
    call this directly, where there is nobody to report progress to.
    """

    def stage(step, text, detail=None):

        if on_stage:
            on_stage(step, text, detail)

    device = frappe.get_doc("TimeBridge Machine", machine_id)

    # A push device accepts no incoming connection, so there is nothing to
    # dial and no point walking the steps below to a certain failure.
    if is_push_device(device):

        return {
            "status": "failed",
            "failed_step": STEP_CONNECT,
            "message": (
                f"{device.machine_name or device.name} is a push device (SDK Type: "
                "ADMS). It cannot be read on demand — it uploads on its own timer. "
                "Use Fetch All Data, which asks it to re-send."
            )
        }

    port = cint(device.port) or 4370
    udp = uses_udp(device)

    # Reachability first. Without it the connector spends its entire retry
    # budget discovering silence and then reports a network fault as a
    # protocol one. UDP devices refuse TCP on the same port, so probing
    # would fail a machine that can still be read.
    stage(
        STEP_NETWORK,
        "Checking network",
        f"{device.ip_address}:{port}" + (" UDP" if udp else "")
    )

    if udp:
        reachable, detail = True, "udp"
    else:
        reachable, detail = probe_socket(device.ip_address, port)

    if not reachable:

        set_machine_status(device, "Disconnected")
        msg = f"Cannot reach {device.ip_address}:{port} — {detail}"
        write_machine_log(
            machine=machine_id,
            level="Error",
            event="Pull",
            message=msg,
        )

        return {
            "status": "failed",
            "failed_step": STEP_NETWORK,
            "machine_status": "Disconnected",
            "message": msg
        }

    connector = get_connector(device)

    conn = None
    users = []
    punches = []
    photos = []

    try:

        stage(STEP_CONNECT, "Connecting to device")

        conn = connector.connect(
            device,
            on_attempt=lambda attempt, attempts: stage(
                STEP_CONNECT,
                "Connecting to device",
                f"attempt {attempt} of {attempts}"
            )
        )

        stage(STEP_READ, "Reading users from device")

        users = connector.get_users(conn)

        stage(STEP_READ, "Reading punches from device", f"{len(users)} users read")

        punches = connector.get_attendance(conn)

        stage(
            STEP_READ,
            "Reading punches from device",
            f"{len(users)} users, {len(punches)} punches read"
        )

        getter = getattr(connector, "get_user_photos", None)

        if getter:
            try:
                photos = getter(conn, users) or []
            except Exception:
                tb = frappe.get_traceback()
                write_machine_log(
                    machine=machine_id,
                    level="Warning",
                    event="Photo",
                    message="Pull photo read failed",
                    details=tb,
                )
                frappe.log_error(
                    tb,
                    "TimeBridge: Pull Photo Read Error"
                )
                photos = []

    except Exception as e:

        tb = frappe.get_traceback()
        write_machine_log(
            machine=machine_id,
            level="Error",
            event="Pull",
            message=str(e),
            details=tb,
        )
        frappe.log_error(tb, "TimeBridge: Pull Sync Error")

        set_machine_status(device, "Disconnected")

        return {
            "status": "failed",
            "failed_step": STEP_CONNECT if conn is None else STEP_READ,
            "machine_status": "Disconnected",
            "reason": failure_reason(e),
            "message": str(e)
        }

    finally:

        # connect() left the terminal disabled, so it must be re-enabled even
        # if the read above blew up — otherwise the device stays dead to the
        # people standing in front of it.
        try:
            connector.disconnect(conn)

        except Exception:
            tb = frappe.get_traceback()
            write_machine_log(
                machine=machine_id,
                level="Warning",
                event="Pull",
                message="Device disconnect failed after pull users",
                details=tb,
            )
            frappe.log_error(
                tb,
                "TimeBridge: Device Disconnect Error"
            )

    # Everything below runs with the device already back in service.
    sync_batch = now_datetime().strftime("%Y-%m-%d %H:%M:%S")

    user_counts = store_users(machine_id, users, sync_batch, stage)

    from timebridge.timebridge.adms.photos import save_photo

    for photo in photos or []:
        if photo.get("user_id") and photo.get("image_bytes"):
            save_photo(machine_id, photo["user_id"], photo["image_bytes"], "PyZK Pull")

    punch_counts = store_punches(machine_id, punches, days, sync_batch, stage)

    # Devices are read users-first, so most punches match immediately. This
    # catches the rest: people deleted from the device but still in its log,
    # and punches stored before their TimeBridge Machine User was mapped to a TimeBridge Employee.
    linked = logger.link_unmatched_punches(machine_id)

    set_machine_status(device, "Connected")

    return {
        "status": "success",
        "machine_status": "Connected",
        "users": user_counts,
        "punches": punch_counts,
        "linked": linked,
        "message": (
            f"{punch_counts['created']} new punches, "
            f"{user_counts['created']} new users"
        )
    }


def store_users(machine_id, users, sync_batch, stage):
    """
    Upsert what the device reported, and record the run.

    A failure here is logged and returned rather than raised: punches are the
    data that cannot be recovered later, and abandoning them because a name
    would not save would be the worse loss.
    """

    stage(STEP_SAVE, "Saving users", f"{len(users)} read")

    sync_log = logger.open_sync_log(machine_id, "Users", sync_batch)

    try:
        counts = logger.save_users(machine_id, users)

    except Exception as e:

        tb = frappe.get_traceback()
        write_machine_log(
            machine=machine_id,
            level="Error",
            event="Pull",
            message=f"Pull user save failed: {e}",
            details=tb,
        )
        frappe.log_error(tb, "TimeBridge: Pull User Save Error")

        logger.close_sync_log(sync_log, "Failed", fetched=len(users), error=str(e))

        return {"created": 0, "updated": 0, "error": str(e)}

    logger.close_sync_log(
        sync_log,
        "Success",
        fetched=len(users),
        created=counts["created"],
        skipped=len(users) - counts["created"] - counts["updated"]
    )

    return counts


def store_punches(machine_id, punches, days, sync_batch, stage):
    """
    Store the punches inside the requested window, in committed batches.

    Records already held are dropped before any insert is attempted: a device
    hands over its whole log every time, so on the second run almost all of it
    is already here, and checking in bulk turns tens of thousands of queries
    into one.
    """

    days = cint(days)

    cutoff = get_datetime(add_to_date(now_datetime(), days=-days)) if days > 0 else None

    in_window = []
    outside = 0

    for record in punches:

        if cutoff and get_datetime(record["timestamp"]) < cutoff:
            outside += 1
            continue

        in_window.append(record)

    stage(
        STEP_SAVE,
        "Storing punches",
        f"{len(in_window)} in window, {outside} older than the window"
    )

    fresh, already_held = drop_stored(machine_id, in_window)

    sync_log = logger.open_sync_log(machine_id, "Attendance", sync_batch)

    created = 0
    duplicates = already_held
    invalid = 0
    unmatched = 0

    try:

        for start in range(0, len(fresh), INSERT_BATCH):

            batch = fresh[start:start + INSERT_BATCH]

            counts = logger.save_punches(
                machine_id,
                batch,
                sync_batch=sync_batch,
                source=SOURCE_PYZK
            )

            created += counts["created"]
            duplicates += counts["duplicates"]
            invalid += counts["invalid"]
            unmatched += counts["unmatched"]

            # Each batch is made durable as it lands, so a run that is
            # interrupted has still made progress and the retry is cheap.
            frappe.db.commit()

            stage(
                STEP_SAVE,
                "Storing punches",
                f"{min(start + INSERT_BATCH, len(fresh))} of {len(fresh)} — {created} new"
            )

    except Exception as e:

        tb = frappe.get_traceback()
        write_machine_log(
            machine=machine_id,
            level="Error",
            event="Pull",
            message=f"Pull punch save failed: {e}",
            details=tb,
        )
        frappe.log_error(tb, "TimeBridge: Pull Punch Save Error")

        logger.close_sync_log(
            sync_log,
            "Failed",
            fetched=len(in_window),
            created=created,
            skipped=duplicates + outside,
            error=str(e)
        )

        raise

    logger.close_sync_log(
        sync_log,
        "Success",
        fetched=len(in_window),
        created=created,
        skipped=duplicates + invalid + outside
    )

    return {
        "read": len(punches),
        "in_window": len(in_window),
        "outside_window": outside,
        "created": created,
        "duplicates": duplicates,
        "invalid": invalid,
        "unmatched": unmatched,
        "sync_batch": sync_batch
    }


def drop_stored(machine_id, records):
    """
    Split records into those not yet stored and a count of those already held.

    The key is built the same way TimeBridge Punch Log builds it, so this
    agrees with the unique constraint that has the final say.
    """

    from timebridge.timebridge.doctype.timebridge_punch_log.timebridge_punch_log import (
        build_punch_key,
    )

    if not records:
        return [], 0

    stored = set(
        frappe.get_all(
            "TimeBridge Punch Log",
            filters={"machine": machine_id},
            pluck="punch_key"
        )
    )

    fresh = []
    already_held = 0

    # Also guards against a device reporting the same punch twice in one read,
    # which would otherwise reach the database as a duplicate insert.
    seen = set()

    for record in records:

        try:
            key = build_punch_key(
                machine_id,
                record["device_user_id"],
                record["timestamp"]
            )

        except Exception:
            # Left for save_punches to count as invalid, so there is one place
            # that decides what an unusable record is.
            fresh.append(record)
            continue

        if key in stored or key in seen:
            already_held += 1
            continue

        seen.add(key)
        fresh.append(record)

    return fresh, already_held
