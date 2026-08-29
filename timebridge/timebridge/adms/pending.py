# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Tracks inbound ADMS traffic from devices that are not yet registered.

Push devices identify themselves only by serial number. Until a
TimeBridge Machine exists with that serial, handshakes and heartbeats
were invisible — this module makes them discoverable from Desk.
"""

import json

import frappe

from timebridge.timebridge.adms import logger

DOCTYPE = "TimeBridge Pending Device Signal"


def remote_ip():
    """Best-effort client address for an inbound ADMS request."""

    request = getattr(frappe.local, "request", None)

    if not request:
        return None

    forwarded = request.headers.get("X-Forwarded-For")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.remote_addr


def classify_signal(endpoint, method):
    """Human-readable label for the kind of contact."""

    endpoint = (endpoint or "").lower()
    method = (method or "").upper()

    if endpoint == "cdata" and method in ("GET", "HEAD"):
        return "Handshake"

    if endpoint == "getrequest":
        return "Heartbeat"

    if endpoint == "cdata" and method == "POST":
        return "Upload"

    if endpoint == "ping":
        return "Ping"

    if endpoint == "fdata":
        return "Photo Upload"

    if endpoint == "devicecmd":
        return "Command Result"

    return "Other"


def record_signal(serial, endpoint, method, args=None):
    """
    Upsert a pending signal for an unregistered serial.

    Called from the ADMS renderer on every inbound request whose SN does
    not match a TimeBridge Machine. Safe to call frequently — heartbeats
    only bump hit_count and last_seen.
    """

    serial = (serial or "").strip()

    if not serial:
        return

    if logger.get_machine_by_serial(serial):
        _mark_registered_if_pending(serial)
        return

    now = frappe.utils.now_datetime()
    signal_type = classify_signal(endpoint, method)
    query_args = ""

    if args:
        try:
            query_args = json.dumps(args, sort_keys=True)[:2000]
        except TypeError:
            query_args = str(args)[:2000]

    ip = remote_ip()
    existing = frappe.db.get_value(
        DOCTYPE,
        {"serial_number": serial},
        ["name", "status", "hit_count"],
        as_dict=True,
    )

    if existing:
        updates = {
            "endpoint": endpoint,
            "method": method,
            "signal_type": signal_type,
            "last_seen": now,
            "hit_count": (existing.hit_count or 0) + 1,
            "query_args": query_args,
        }

        if ip:
            updates["remote_ip"] = ip

        if existing.status == "Dismissed":
            updates["status"] = "Pending"

        frappe.db.set_value(DOCTYPE, existing.name, updates, update_modified=True)
    else:
        frappe.get_doc(
            {
                "doctype": DOCTYPE,
                "serial_number": serial,
                "endpoint": endpoint,
                "method": method,
                "signal_type": signal_type,
                "remote_ip": ip,
                "first_seen": now,
                "last_seen": now,
                "hit_count": 1,
                "query_args": query_args,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True)

    frappe.db.commit()


def _mark_registered_if_pending(serial):
    """Close out a pending row once the serial is registered elsewhere."""

    name = frappe.db.get_value(
        DOCTYPE,
        {"serial_number": serial, "status": "Pending"},
        "name",
    )

    if not name:
        return

    machine = logger.get_machine_by_serial(serial)

    frappe.db.set_value(
        DOCTYPE,
        name,
        {
            "status": "Registered",
            "registered_machine": machine,
        },
        update_modified=True,
    )
    frappe.db.commit()


def list_pending(limit=50):
    """Rows shown on the Device Registration desk page."""

    return frappe.get_all(
        DOCTYPE,
        filters={"status": "Pending"},
        fields=[
            "name",
            "serial_number",
            "signal_type",
            "endpoint",
            "method",
            "remote_ip",
            "first_seen",
            "last_seen",
            "hit_count",
            "query_args",
        ],
        order_by="last_seen desc",
        limit=limit,
    )


def dismiss_signal(name):
    frappe.db.set_value(DOCTYPE, name, "status", "Dismissed", update_modified=True)
    frappe.db.commit()


def register_machine(name, machine_id, machine_name, device_brand, ip_address):
    """
    Create a TimeBridge Machine from a pending signal and close the row.
    """

    signal = frappe.get_doc(DOCTYPE, name)

    if signal.status != "Pending":
        frappe.throw(f"Signal {name} is not pending.")

    if frappe.db.exists("TimeBridge Machine", {"machine_id": machine_id}):
        frappe.throw(f"Machine ID {machine_id!r} already exists.")

    if frappe.db.exists("TimeBridge Machine", {"serial_number": signal.serial_number}):
        frappe.throw(
            f"Serial {signal.serial_number!r} is already registered on another machine."
        )

    machine = frappe.get_doc(
        {
            "doctype": "TimeBridge Machine",
            "machine_id": machine_id,
            "machine_name": machine_name,
            "device_brand": device_brand,
            "serial_number": signal.serial_number,
            "ip_address": ip_address,
            "port": 4370,
            "sdk_type": "ADMS",
            "sync_enabled": 1,
        }
    )
    machine.insert()

    frappe.db.set_value(
        DOCTYPE,
        name,
        {
            "status": "Registered",
            "registered_machine": machine.name,
        },
        update_modified=True,
    )
    frappe.db.commit()

    return {
        "machine": machine.name,
        "machine_id": machine.machine_id,
        "serial_number": signal.serial_number,
    }


def unlink_machine(machine_name):
    """
    Drop the back-reference when a registered machine is removed.

    The signal row stays for audit, but reopens as Pending so the serial can
    be registered again from Device Registration.
    """

    for name in frappe.get_all(
        DOCTYPE,
        filters={"registered_machine": machine_name},
        pluck="name",
    ):
        frappe.db.set_value(
            DOCTYPE,
            name,
            {
                "registered_machine": None,
                "status": "Pending",
            },
            update_modified=True,
        )
