import socket

import frappe

from frappe.utils import cint

from timebridge.timebridge.sdk_connectors.pyzk_connector import (
    DEFAULT_CONNECTION_TIMEOUT,
    DEFAULT_RETRY_COUNT,
    RETRY_BACKOFF_SECONDS,
)
from timebridge.timebridge.services.connection import get_connector

DEVICE_INFO_EVENT = "timebridge_device_info"

# Headroom on top of the worst-case retry budget, so the worker is never
# killed in the middle of an attempt the connector was still willing to make.
JOB_TIMEOUT_BUFFER = 60

# The stages the client draws a progress list from. Keep in step with the
# STEPS array in biometric_machine.js — the client matches on these numbers.
STEP_NETWORK = 1
STEP_CONNECT = 2
STEP_READ = 3
STEP_SAVE = 4
TOTAL_STEPS = 4

# How long the plain "is anything listening on that port" probe may take.
# Deliberately short: this is a reachability question, not the real session,
# and a long wait here is indistinguishable from a hung job to the user.
SOCKET_PROBE_TIMEOUT = 5

# Progress is mirrored into the cache so the browser can *poll* for it over
# the normal web port, instead of depending on the realtime (socketio) port.
#
# Why: this bench runs under WSL2, which only forwards IPv4 listeners to
# Windows. Frappe's web server binds 0.0.0.0 (IPv4) and is reachable, but
# socketio binds :: (IPv6) and is not — so realtime events never arrive in the
# browser at all. Proven with a pair of test listeners: the IPv4 one answered
# from Windows, the IPv6 one did not. Polling sidesteps that entirely and
# needs no change to Frappe itself.
#
# publish_realtime is still called as well, so nothing breaks for anyone whose
# socketio does work.
PROGRESS_TTL = 600


def progress_key(machine_id):

    return f"timebridge_device_info_progress::{machine_id}"


def set_progress(machine_id, payload):
    """Record where the job has got to, for the browser to poll."""

    frappe.cache().set_value(
        progress_key(machine_id),
        payload,
        expires_in_sec=PROGRESS_TTL
    )


def get_progress(machine_id):

    return frappe.cache().get_value(progress_key(machine_id)) or {}


def enqueue_device_info(machine_id):
    """
    Queue a device read in the background. Returns immediately with the
    job id and a run_id; progress is polled via api.get_device_info_progress
    and is mirrored onto the Biometric Machine record.
    """

    job_id = f"{DEVICE_INFO_EVENT}::{machine_id}"

    # Identifies this particular click. Without it the browser could pick up
    # the cached result of an earlier run and report it as the new one — which
    # is exactly the sort of stale answer that makes a test button untrustworthy.
    run_id = frappe.generate_hash(length=10)

    set_progress(machine_id, {
        "run_id": run_id,
        "status": "queued",
        "stage": "Queued",
        "step": 0,
        "total": TOTAL_STEPS
    })

    job = frappe.enqueue(
        "timebridge.timebridge.services.device_info.run_device_info_job",
        queue="short",
        job_id=job_id,
        deduplicate=True,
        timeout=job_timeout(),
        machine_id=machine_id,
        user=frappe.session.user,
        run_id=run_id
    )

    # enqueue() returns None when deduplication suppressed the job,
    # which means one is already in flight for this machine.
    if job is None:

        # Follow the run already going, rather than the run_id just minted for
        # a job that was never created — otherwise the browser polls for
        # something that will never report.
        running = get_progress(machine_id)

        return {
            "status": "queued",
            "run_id": running.get("run_id"),
            "message": "A device read is already running for this machine",
            "timeout": job_timeout()
        }

    return {
        "status": "queued",
        "job_id": job.id,
        "run_id": run_id,
        "message": "Device read queued",

        # The client arms its watchdog from this. Sending the real budget
        # means the UI gives up at the same moment the worker would, rather
        # than at some guessed interval that is always wrong.
        "timeout": job_timeout()
    }


def publish_stage(machine_id, user, step, stage, detail=None, run_id=None):
    """
    Tell the browser what the worker is doing right now.

    Written to the cache first — that is the channel the browser actually
    reads, by polling. The realtime publish is kept as well so nothing breaks
    where socketio is reachable, but nothing depends on it.

    Deliberately NOT after_commit: progress is only useful while the job is
    still running, and the job holds one transaction from start to finish.
    Deferring these to commit time would deliver every stage at the end, all
    at once, which is the same as showing nothing.
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

    frappe.publish_realtime(
        DEVICE_INFO_EVENT,
        message=payload,
        user=user
    )


def run_device_info_job(machine_id, user=None, run_id=None):
    """
    Background entry point. Wraps fetch_device_info so the outcome is
    published for the user who asked for it — a queued job cannot return a
    value to the caller that enqueued it.
    """

    user = user or frappe.session.user

    def on_stage(step, stage, detail=None):
        publish_stage(machine_id, user, step, stage, detail, run_id=run_id)

    # Step 0 is the handshake the user is really waiting on: proof that a
    # worker exists and picked this up. Without it, a starved queue and a
    # dead device look identical from the form.
    on_stage(0, "Background worker picked up the job")

    result = fetch_device_info(machine_id, on_stage=on_stage)

    final = dict(result, machine_id=machine_id, run_id=run_id)

    # The record writes above are committed by the job wrapper. Publish the
    # final state to the cache only after that commit, so a client that polls
    # the instant it sees "success" cannot reload the form and read the old
    # serial_number / status.
    frappe.db.commit()

    set_progress(machine_id, final)

    frappe.publish_realtime(
        DEVICE_INFO_EVENT,
        message=final,
        user=user,
        after_commit=True
    )

    return result


def probe_socket(ip_address, port, timeout=SOCKET_PROBE_TIMEOUT):
    """
    Is anything accepting TCP on that address and port?

    Separating this from the protocol session is what makes a failure
    readable: "nothing is listening" and "it answered but refused us" are
    completely different problems, and the full session cannot tell them
    apart.
    """

    try:
        with socket.create_connection((ip_address, port), timeout=timeout):
            return True, "port is open"

    except socket.timeout:
        return False, "no response within %ss — wrong IP, or blocked by a firewall" % timeout

    except OSError as e:
        return False, str(e)


def job_timeout():
    """
    Worst case the connector can take: every attempt burning the full
    connection timeout, plus the backoff waited between them.
    """

    timeout = frappe.db.get_single_value(
        "TimeBridge Settings",
        "connection_timeout"
    ) or DEFAULT_CONNECTION_TIMEOUT

    attempts = frappe.db.get_single_value(
        "TimeBridge Settings",
        "retry_count"
    ) or DEFAULT_RETRY_COUNT

    timeout = int(timeout)
    attempts = max(int(attempts), 1)

    backoff = RETRY_BACKOFF_SECONDS * (attempts * (attempts - 1)) // 2

    return (attempts * timeout) + backoff + JOB_TIMEOUT_BUFFER


def fetch_device_info(machine_id, on_stage=None):
    """
    Pull live metadata off a biometric device and mirror the identifying
    parts of it back onto the Biometric Machine record.

    Returns a dict with "status" ("success" / "failed"), "message" and,
    on success, "info" holding everything the connector reported.

    on_stage(step, stage, detail) is optional and called as the work
    progresses, so a caller can show it live. It stays optional because
    this function is also the synchronous entry point for the scheduler
    and console, where there is nobody to report to.
    """

    def stage(step, text, detail=None):

        if on_stage:
            on_stage(step, text, detail)

    device = frappe.get_doc(
        "Biometric Machine",
        machine_id
    )

    # A push device answers no connection at all, so the whole probe-and-dial
    # sequence below is meaningless for it. Report what health actually means
    # for that kind of machine — has it been sending — instead of walking four
    # steps to a certain failure.
    from timebridge.timebridge.services.connection import is_push_device

    if is_push_device(device):

        stage(STEP_NETWORK, "Checking device type", "push device — nothing to dial")

        result = get_connector(device).health(device)

        set_machine_status(device, result["machine_status"])

        return dict(result, failed_step=None if result["status"] == "success" else STEP_CONNECT)

    port = cint(device.port) or 4370

    # Reachability first. If nothing is listening, the connector would
    # spend the entire retry budget discovering that — up to ~96s of
    # silence for the stock settings — and then report it as a protocol
    # error rather than a network one.
    stage(STEP_NETWORK, "Checking network", f"{device.ip_address}:{port}")

    reachable, detail = probe_socket(device.ip_address, port)

    if not reachable:

        set_machine_status(device, "Disconnected")

        return {
            "status": "failed",
            "failed_step": STEP_NETWORK,
            "machine_status": "Disconnected",
            "message": f"Cannot reach {device.ip_address}:{port} — {detail}"
        }

    stage(STEP_NETWORK, "Checking network", f"port {port} is open")

    connector = get_connector(device)

    conn = None

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

        stage(STEP_READ, "Reading device information")

        info = connector.get_device_info(conn)


    except Exception as e:

        frappe.log_error(
            frappe.get_traceback(),
            "TimeBridge: Device Info Error"
        )

        set_machine_status(device, "Disconnected")

        return {
            "status": "failed",
            "failed_step": STEP_CONNECT if conn is None else STEP_READ,
            "machine_status": "Disconnected",
            "message": str(e)
        }


    finally:

        # The ZK protocol leaves the device disabled after connect(),
        # so it must be re-enabled even when the read above blew up.
        try:
            connector.disconnect(conn)

        except Exception:

            frappe.log_error(
                frappe.get_traceback(),
                "TimeBridge: Device Disconnect Error"
            )


    stage(STEP_SAVE, "Saving to the record")

    apply_device_info(device, info)

    return {
        "status": "success",
        "machine_status": "Connected",
        "message": f"{device.machine_name} Info Fetched",
        "info": info
    }


def apply_device_info(device, info):
    """
    Write the device-reported identity back onto the record, but only
    where the device actually told us something and it differs from
    what is already stored.
    """

    updates = {}

    serial_number = info.get("serial_number")

    if serial_number and serial_number != device.serial_number:
        updates["serial_number"] = serial_number

    # The device's own name is the closest thing ZK reports to a model;
    # platform is the firmware build string, used only as a fallback.
    device_model = info.get("device_name") or info.get("platform")

    if device_model and device_model != device.device_model:
        updates["device_model"] = device_model

    if device.status != "Connected":
        updates["status"] = "Connected"

    if updates:

        frappe.db.set_value(
            "Biometric Machine",
            device.name,
            updates
        )


def set_machine_status(device, status):

    if device.status == status:
        return

    frappe.db.set_value(
        "Biometric Machine",
        device.name,
        "status",
        status
    )
