# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""ADMS TimeBridge Machine rows — created in Add Machine, linked on device init."""

import json

import frappe
from frappe.utils import now_datetime, format_datetime

from timebridge.timebridge.iclock.protocol import RECEIVE_FIELDS
from timebridge.timebridge.services.device_records import get_machine_by_serial

MACHINE = "TimeBridge Machine"
PEER = "TimeBridge ADMS Peer"
DISCOVERABLE_CATEGORIES = frozenset({"Handshake", "Heartbeat"})
MACHINE_FIELDS = [
	"name",
	"adms_status",
	"sdk_type",
	"adms_stamp",
	"adms_op_stamp",
	"adms_photo_stamp",
	"adms_handshake_at",
	*RECEIVE_FIELDS,
]


def remote_ip():
	request = getattr(frappe.local, "request", None)
	if not request:
		return None
	forwarded = request.headers.get("X-Forwarded-For")
	if forwarded:
		return forwarded.split(",")[0].strip()
	return request.remote_addr


def machine_row(serial):
	name = get_machine_by_serial(serial)
	if not name:
		return None
	row = frappe.db.get_value(MACHINE, name, MACHINE_FIELDS, as_dict=True)
	return row


def record_init(serial, args):
	"""Refresh metadata on a pre-created Pending machine when the device inits."""

	serial = (serial or "").strip()
	if not serial:
		return None

	existing = machine_row(serial)
	if not existing:
		return None

	now = now_datetime()
	ip = remote_ip() or "0.0.0.0"
	pushver = (args or {}).get("pushver") or (args or {}).get("pushver".upper())
	language = (args or {}).get("language")
	pushcommkey = (args or {}).get("pushcommkey")
	query = ""
	if args:
		try:
			query = json.dumps(args, sort_keys=True)[:2000]
		except TypeError:
			query = str(args)[:2000]

	updates = {
		"last_contact_at": now,
		"adms_last_init_at": now,
	}
	if ip and ip != "0.0.0.0":
		updates["ip_address"] = ip
	if pushver:
		updates["adms_pushver"] = str(pushver)[:140]
	if language:
		updates["adms_language"] = str(language)[:140]
	if pushcommkey:
		updates["adms_pushcommkey"] = str(pushcommkey)[:140]
	if query:
		updates["adms_last_query"] = query
	frappe.db.set_value(MACHINE, existing.name, updates, update_modified=False)
	return machine_row(serial)


def peer_is_discoverable(serial):
	serial = (serial or "").strip()
	if not serial:
		return False

	existing = machine_row(serial)
	if existing:
		return existing.adms_status == "Pending"

	peer = frappe.db.get_value(PEER, {"serial_number": serial}, "last_category")
	if not peer:
		return False
	return peer in DISCOVERABLE_CATEGORIES


def create_pending_machine(
	machine_id,
	machine_name,
	serial_number,
	device_brand="ZKTeco",
	ip_address=None,
	require_discovery=True,
):
	"""Create a Pending ADMS machine after the device has checked in."""

	serial_number = (serial_number or "").strip()
	machine_id = (machine_id or "").strip()
	machine_name = (machine_name or "").strip()

	if not serial_number:
		frappe.throw("Serial Number is required.")
	if not machine_id:
		frappe.throw("Machine ID is required.")
	if not machine_name:
		frappe.throw("Machine Name is required.")
	if require_discovery and not peer_is_discoverable(serial_number):
		frappe.throw(
			"This device has not sent a handshake or heartbeat yet. "
			"Reboot it from Settings or wait for it to check in."
		)
	existing = machine_row(serial_number)
	if existing:
		if existing.adms_status == "Pending":
			return {"machine": existing.name, "machine_id": existing.machine_id}
		frappe.throw(f"A machine with serial {serial_number!r} already exists.")
	if frappe.db.exists(MACHINE, {"machine_id": machine_id}):
		frappe.throw(f"Machine ID {machine_id!r} already exists.")

	doc = frappe.get_doc(
		{
			"doctype": MACHINE,
			"machine_id": machine_id,
			"machine_name": machine_name,
			"device_brand": device_brand or "ZKTeco",
			"serial_number": serial_number,
			"ip_address": ip_address if ip_address and _valid_ip(ip_address) else "0.0.0.0",
			"port": 4370,
			"sdk_type": "ADMS",
			"adms_status": "Pending",
			"status": "Disconnected",
		}
	)
	doc.insert()
	from timebridge.timebridge.iclock import peers

	peers.ensure_peer(serial_number)
	_apply_peer_init_to_machine(serial_number, doc.name)
	return {"machine": doc.name, "machine_id": doc.machine_id}


def adopt_discovered_peer(
	serial_number,
	machine_id=None,
	machine_name=None,
	device_brand="ZKTeco",
	ip_address=None,
):
	"""Add Machine → Push: create Pending row from a discovered peer."""

	serial_number = (serial_number or "").strip()
	return create_pending_machine(
		machine_id=machine_id or serial_number,
		machine_name=machine_name or serial_number,
		serial_number=serial_number,
		device_brand=device_brand,
		ip_address=ip_address,
		require_discovery=True,
	)


def register_machine(name):
	doc = frappe.get_doc(MACHINE, name)
	if doc.sdk_type != "ADMS":
		frappe.throw("Only ADMS machines can be registered this way.")
	if doc.adms_status == "Registered":
		return {"machine": doc.name, "status": "Registered"}
	doc.adms_status = "Registered"
	doc.save()
	return {"machine": doc.name, "status": "Registered"}


def dismiss_machine(name):
	doc = frappe.get_doc(MACHINE, name)
	if doc.sdk_type != "ADMS":
		frappe.throw("Only ADMS machines can be dismissed.")
	doc.adms_status = "Dismissed"
	doc.save()
	return {"machine": doc.name, "status": "Dismissed"}


def list_pending():
	return list_discoverable()


def list_discoverable():
	"""Devices that contacted /iclock and can be opened for Register."""

	rows = []
	seen_serials = set()

	for machine in frappe.get_all(
		MACHINE,
		filters={"sdk_type": "ADMS", "adms_status": "Pending"},
		fields=[
			"name",
			"serial_number",
			"ip_address",
			"machine_name",
			"adms_pushver",
			"last_contact_at",
			"adms_last_init_at",
		],
		order_by="modified desc",
	):
		if not machine.serial_number:
			continue
		seen_serials.add(machine.serial_number)
		peer = frappe.db.get_value(
			PEER,
			{"serial_number": machine.serial_number},
			["last_category", "last_seen_at"],
			as_dict=True,
		)
		last_at = machine.last_contact_at or machine.adms_last_init_at
		if not last_at and peer:
			last_at = peer.last_seen_at
		rows.append(
			{
				"name": machine.name,
				"serial_number": machine.serial_number,
				"ip_address": machine.ip_address,
				"machine_name": machine.machine_name,
				"adms_pushver": machine.adms_pushver,
				"last_contact_at": format_datetime(last_at) if last_at else None,
				"adms_last_init_at": format_datetime(machine.adms_last_init_at)
				if machine.adms_last_init_at
				else None,
				"last_category": peer.last_category if peer else None,
				"device_seen": bool(machine.adms_last_init_at),
				"discovered": True,
			}
		)

	from timebridge.timebridge.iclock.peers import _fetch_peers

	for peer in _fetch_peers():
		if not peer.serial_number or peer.serial_number in seen_serials:
			continue
		if get_machine_by_serial(peer.serial_number):
			continue
		if peer.last_category not in DISCOVERABLE_CATEGORIES:
			continue
		rows.append(
			{
				"name": None,
				"peer": peer.name,
				"serial_number": peer.serial_number,
				"ip_address": peer.remote_ip,
				"machine_name": peer.serial_number,
				"adms_pushver": peer.adms_pushver,
				"last_contact_at": format_datetime(peer.last_seen_at)
				if peer.last_seen_at
				else None,
				"adms_last_init_at": format_datetime(peer.last_seen_at)
				if peer.last_category == "Handshake" and peer.last_seen_at
				else None,
				"last_category": peer.last_category,
				"device_seen": peer.last_category == "Handshake",
				"discovered": True,
			}
		)

	return rows


def _apply_peer_init_to_machine(serial, machine_name):
	peer = frappe.db.get_value(
		PEER,
		{"serial_number": serial},
		["last_category", "last_seen_at", "adms_pushver", "remote_ip"],
		as_dict=True,
	)
	if not peer or peer.last_category != "Handshake" or not peer.last_seen_at:
		return

	updates = {
		"adms_last_init_at": peer.last_seen_at,
		"last_contact_at": peer.last_seen_at,
	}
	if peer.adms_pushver:
		updates["adms_pushver"] = peer.adms_pushver
	if peer.remote_ip and _valid_ip(peer.remote_ip):
		updates["ip_address"] = peer.remote_ip
	frappe.db.set_value(MACHINE, machine_name, updates, update_modified=False)


def _valid_ip(value):
	import ipaddress

	try:
		ipaddress.ip_address(value)
		return True
	except ValueError:
		return False
