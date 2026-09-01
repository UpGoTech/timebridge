# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""ADMS peer roster — one row per serial that has contacted /iclock."""

import frappe
from frappe.utils import cint, format_datetime, now_datetime

from timebridge.timebridge.iclock import audit
from timebridge.timebridge.iclock.discovery import remote_ip
from timebridge.timebridge.services.device_records import get_machine_by_serial

PEER = "TimeBridge ADMS Peer"
MACHINE = "TimeBridge Machine"
ALLOWED_PEER_COMMANDS = frozenset({"REBOOT"})

# frappe.get_all silently drops fields named last_seen_at / first_seen_at — fetch via SQL.
PEER_LIST_FIELDS = """
	name, serial_number, remote_ip, last_seen_at,
	last_category, hit_count, pending_command, adms_pushver, first_seen_at
"""


def _fetch_peers(limit=500):
	return frappe.db.sql(
		f"""
		SELECT {PEER_LIST_FIELDS}
		FROM `tabTimeBridge ADMS Peer`
		ORDER BY last_seen_at DESC, modified DESC
		LIMIT {limit}
		""",
		as_dict=True,
	)


def _fmt_dt(value):
	return format_datetime(value) if value else None


def record_contact(serial, endpoint, method, args=None):
	serial = (serial or "").strip()
	if not serial:
		return None

	now = now_datetime()
	category = audit.classify(endpoint, method, _table(args))
	ip = remote_ip()
	pushver = None
	if args:
		pushver = args.get("pushver") or args.get("PushVer")

	name = frappe.db.get_value(PEER, {"serial_number": serial}, "name")
	if name:
		values = {
			"last_seen_at": now,
			"hit_count": cint(frappe.db.get_value(PEER, name, "hit_count")) + 1,
			"last_endpoint": endpoint,
			"last_category": category,
		}
		if ip:
			values["remote_ip"] = ip
		if pushver:
			values["adms_pushver"] = str(pushver)[:140]
		frappe.db.set_value(PEER, name, values, update_modified=False)
		return name

	doc = frappe.get_doc(
		{
			"doctype": PEER,
			"serial_number": serial,
			"remote_ip": ip,
			"first_seen_at": now,
			"last_seen_at": now,
			"hit_count": 1,
			"last_endpoint": endpoint,
			"last_category": category,
			"adms_pushver": str(pushver or "")[:140] or None,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_peer(serial):
	"""Ensure a peer row exists for this serial (observability only — no Machine link)."""

	serial = (serial or "").strip()
	if not serial:
		return None
	if frappe.db.exists(PEER, {"serial_number": serial}):
		return frappe.db.get_value(PEER, {"serial_number": serial}, "name")

	now = now_datetime()
	doc = frappe.get_doc(
		{
			"doctype": PEER,
			"serial_number": serial,
			"first_seen_at": now,
			"last_seen_at": None,
			"hit_count": 0,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_peer_for_machine(serial, machine=None):
	"""Backward-compatible alias — peers are keyed by serial only."""

	return ensure_peer(serial)


def dismiss_peer(serial=None, peer=None):
	"""Remove a peer from the roster. Pending machines are dismissed too."""

	serial = (serial or "").strip()
	if peer:
		serial = serial or frappe.db.get_value(PEER, peer, "serial_number")
	if not serial and not peer:
		frappe.throw("Serial or peer is required.")

	name = peer or frappe.db.get_value(PEER, {"serial_number": serial}, "name")
	if not name:
		frappe.throw("Peer not found.")

	machine_name = get_machine_by_serial(serial)
	if machine_name:
		adms_status = frappe.db.get_value(MACHINE, machine_name, "adms_status")
		if adms_status == "Pending":
			from timebridge.timebridge.iclock import discovery

			discovery.dismiss_machine(machine_name)

	frappe.delete_doc(PEER, name, ignore_permissions=True)
	return {"peer": name, "serial": serial, "status": "dismissed"}


def queue_serial_command(serial, command):
	serial = (serial or "").strip()
	command = (command or "").strip().upper()
	if not serial:
		frappe.throw("Serial number is required.")
	if command not in ALLOWED_PEER_COMMANDS:
		frappe.throw(f"Unsupported peer command: {command}")

	machine_name = get_machine_by_serial(serial)
	if machine_name:
		status = frappe.db.get_value("TimeBridge Machine", machine_name, "adms_status")
		if status == "Registered":
			frappe.throw("Use device commands for registered machines.")

	if not frappe.db.exists(PEER, {"serial_number": serial}):
		ensure_peer(serial)

	name = frappe.db.get_value(PEER, {"serial_number": serial}, "name")
	last_id = cint(frappe.db.get_value(PEER, name, "pending_command_id"))
	frappe.db.set_value(
		PEER,
		name,
		{
			"pending_command": command,
			"pending_command_id": last_id + 1,
		},
		update_modified=False,
	)
	return {"serial": serial, "command": command, "command_id": last_id + 1}


def pop_serial_command(serial):
	serial = (serial or "").strip()
	if not serial:
		return None

	row = frappe.db.get_value(
		PEER,
		{"serial_number": serial},
		["name", "pending_command", "pending_command_id"],
		as_dict=True,
	)
	if not row or not row.pending_command:
		return None

	from timebridge.timebridge.iclock.commands import format_commands

	text = format_commands(
		[{"id": row.pending_command_id or 1, "command": row.pending_command}]
	)
	frappe.db.set_value(
		PEER,
		row.name,
		{"pending_command": None, "pending_command_id": 0},
		update_modified=False,
	)
	return text


def _peer_status(serial, machine, adms_status):
	if not machine:
		return "Unknown"
	if adms_status == "Registered":
		return "Registered"
	if adms_status == "Dismissed":
		return "Dismissed"
	return "Pending"


def list_roster():
	rows = []
	seen_serials = set()

	for peer in _fetch_peers():
		adms_status = None
		machine_name = get_machine_by_serial(peer.serial_number)
		machine_label = None
		if machine_name:
			adms_status = frappe.db.get_value("TimeBridge Machine", machine_name, "adms_status")
			machine_label = frappe.db.get_value(
				"TimeBridge Machine", machine_name, "machine_name"
			)
		seen_serials.add(peer.serial_number)
		rows.append(
			{
				"peer": peer.name,
				"serial_number": peer.serial_number,
				"machine": machine_name,
				"machine_name": machine_label,
				"status": _peer_status(peer.serial_number, machine_name, adms_status),
				"remote_ip": peer.remote_ip,
				"last_seen_at": _fmt_dt(peer.last_seen_at),
				"last_category": peer.last_category,
				"hit_count": peer.hit_count,
				"pending_command": peer.pending_command,
				"device_seen": bool(peer.last_seen_at),
			}
		)

	for machine in frappe.get_all(
		MACHINE,
		filters={"sdk_type": "ADMS", "adms_status": "Pending"},
		fields=["name", "serial_number", "machine_name", "ip_address", "adms_last_init_at"],
	):
		if not machine.serial_number or machine.serial_number in seen_serials:
			continue
		rows.append(
			{
				"peer": None,
				"serial_number": machine.serial_number,
				"machine": machine.name,
				"machine_name": machine.machine_name,
				"status": "Pending",
				"remote_ip": machine.ip_address,
				"last_seen_at": _fmt_dt(machine.adms_last_init_at),
				"last_category": None,
				"hit_count": 0,
				"pending_command": None,
				"device_seen": bool(machine.adms_last_init_at),
			}
		)

	return rows


def _table(args):
	if not args:
		return None
	return args.get("table") or args.get("Table")
