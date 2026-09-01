# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""ADMS TimeBridge Machine rows — created in Add Machine, linked on device init."""

import json

import frappe
from frappe.utils import now_datetime

from timebridge.timebridge.iclock.protocol import RECEIVE_FIELDS
from timebridge.timebridge.services.device_records import get_machine_by_serial

MACHINE = "TimeBridge Machine"
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


def create_pending_machine(
	machine_id,
	machine_name,
	serial_number,
	device_brand="ZKTeco",
	ip_address=None,
):
	"""Operator-created Pending ADMS machine (Add Machine → Push)."""

	serial_number = (serial_number or "").strip()
	machine_id = (machine_id or "").strip()
	machine_name = (machine_name or "").strip()

	if not serial_number:
		frappe.throw("Serial Number is required.")
	if not machine_id:
		frappe.throw("Machine ID is required.")
	if not machine_name:
		frappe.throw("Machine Name is required.")
	if get_machine_by_serial(serial_number):
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

	peers.ensure_peer_for_machine(serial_number, doc.name)
	return {"machine": doc.name, "machine_id": doc.machine_id}


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
	rows = frappe.get_all(
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
	)
	for row in rows:
		row["device_seen"] = bool(row.adms_last_init_at)
	return rows


def _valid_ip(value):
	import ipaddress

	try:
		ipaddress.ip_address(value)
		return True
	except ValueError:
		return False
