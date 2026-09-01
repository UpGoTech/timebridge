# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Pending TimeBridge Machine rows for unregistered iclock serials."""

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
	"""Upsert a Pending machine from GET /iclock/cdata?options=all."""

	serial = (serial or "").strip()
	if not serial:
		return None

	existing = machine_row(serial)
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

	if existing:
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
		if query:
			updates["adms_last_query"] = query
		frappe.db.set_value(MACHINE, existing.name, updates, update_modified=False)
		return existing

	machine_id = serial[:140]
	if frappe.db.exists(MACHINE, {"machine_id": machine_id}):
		machine_id = f"{serial[:120]}-{frappe.generate_hash(length=4)}"

	doc = frappe.get_doc(
		{
			"doctype": MACHINE,
			"machine_id": machine_id,
			"machine_name": serial,
			"device_brand": "ZKTeco",
			"serial_number": serial,
			"ip_address": ip if _valid_ip(ip) else "0.0.0.0",
			"port": 4370,
			"sdk_type": "ADMS",
			"adms_status": "Pending",
			"adms_pushver": str(pushver or "")[:140],
			"adms_language": str(language or "")[:140],
			"adms_pushcommkey": str(pushcommkey or "")[:140],
			"adms_last_init_at": now,
			"adms_last_query": query,
			"last_contact_at": now,
			"status": "Disconnected",
		}
	)
	doc.insert(ignore_permissions=True)
	return machine_row(serial)


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
	return frappe.get_all(
		MACHINE,
		filters={"sdk_type": "ADMS", "adms_status": "Pending"},
		fields=[
			"name",
			"serial_number",
			"ip_address",
			"adms_pushver",
			"last_contact_at",
			"adms_last_init_at",
		],
		order_by="last_contact_at desc",
	)


def _valid_ip(value):
	import ipaddress

	try:
		ipaddress.ip_address(value)
		return True
	except ValueError:
		return False
