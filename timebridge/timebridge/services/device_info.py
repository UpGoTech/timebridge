import frappe

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


def enqueue_device_info(machine_id):
    """
    Queue a device read in the background. Returns immediately with the
    job id; the result arrives on the DEVICE_INFO_EVENT realtime event
    and is mirrored onto the Biometric Machine record.
    """

    job_id = f"{DEVICE_INFO_EVENT}::{machine_id}"

    job = frappe.enqueue(
        "timebridge.timebridge.services.device_info.run_device_info_job",
        queue="short",
        job_id=job_id,
        deduplicate=True,
        timeout=job_timeout(),
        machine_id=machine_id,
        user=frappe.session.user
    )

    # enqueue() returns None when deduplication suppressed the job,
    # which means one is already in flight for this machine.
    if job is None:

        return {
            "status": "queued",
            "message": "A device read is already running for this machine"
        }

    return {
        "status": "queued",
        "job_id": job.id,
        "message": "Device read queued"
    }


def run_device_info_job(machine_id, user=None):
    """
    Background entry point. Wraps fetch_device_info so the outcome is
    pushed to the user who asked for it — a queued job cannot return a
    value to the caller that enqueued it.
    """

    result = fetch_device_info(machine_id)

    # after_commit, because the client reloads the form when this lands.
    # Emitting before the job's transaction commits would race the
    # serial_number / device_model / status writes made above.
    frappe.publish_realtime(
        DEVICE_INFO_EVENT,
        message=dict(result, machine_id=machine_id),
        user=user or frappe.session.user,
        after_commit=True
    )

    return result


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


def fetch_device_info(machine_id):
    """
    Pull live metadata off a biometric device and mirror the identifying
    parts of it back onto the Biometric Machine record.

    Returns a dict with "status" ("success" / "failed"), "message" and,
    on success, "info" holding everything the connector reported.
    """

    device = frappe.get_doc(
        "Biometric Machine",
        machine_id
    )

    connector = get_connector(device)

    conn = None

    try:

        conn = connector.connect(device)

        info = connector.get_device_info(conn)


    except Exception as e:

        frappe.log_error(
            frappe.get_traceback(),
            "TimeBridge: Device Info Error"
        )

        set_machine_status(device, "Disconnected")

        return {
            "status": "failed",
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


    apply_device_info(device, info)

    return {
        "status": "success",
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
