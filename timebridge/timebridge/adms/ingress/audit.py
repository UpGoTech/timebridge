# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS Request Log writer — gated by TimeBridge Machine Check fields.

Unknown serials (no Machine yet) are always logged so discovery stays visible.
"""

from __future__ import annotations

import frappe

from frappe.utils import add_days, cint, now_datetime, today

from timebridge.timebridge.adms import logger, parser
from timebridge.timebridge.adms.pending import remote_ip

DOCTYPE = "TimeBridge ADMS Request Log"
MAX_PREVIEW = 4000

TOGGLE_BY_CATEGORY = {
	"Handshake": "log_adms_handshake",
	"Heartbeat": "log_adms_heartbeat",
	"Ping": "log_adms_ping",
	"Attendance": "log_adms_attendance",
	"Users": "log_adms_users",
	"Photos": "log_adms_photos",
	"Commands": "log_adms_commands",
	"Other": None,
}


def classify(endpoint, method, args=None):
	"""Map an inbound /iclock request to a Request Log category."""

	endpoint = (endpoint or "").lower()
	method = (method or "GET").upper()
	args = args or {}
	table = (args.get("table") or args.get("Table") or "").upper()

	if endpoint == "cdata" and method in ("GET", "HEAD"):
		return "Handshake"

	if endpoint == "getrequest":
		return "Heartbeat"

	if endpoint == "ping":
		return "Ping"

	if endpoint == "devicecmd":
		return "Commands"

	if endpoint == "fdata":
		return "Photos"

	if endpoint == "cdata" and method == "POST":
		if table == "ATTLOG":
			return "Attendance"
		if table in ("OPERLOG", "USERINFO", "OPTIONS"):
			return "Users"
		if table in ("ATTPHOTO", "USERPIC", "USERPHOTO", "FACE", "BIOPHOTO"):
			return "Photos"
		return "Other"

	if endpoint == "querydata":
		return "Other"

	return "Other"


def _machine_toggles(machine_name):
	if not machine_name:
		return None

	return frappe.db.get_value(
		"TimeBridge Machine",
		machine_name,
		[
			"log_adms_handshake",
			"log_adms_heartbeat",
			"log_adms_ping",
			"log_adms_attendance",
			"log_adms_users",
			"log_adms_photos",
			"log_adms_commands",
			"log_adms_bodies",
		],
		as_dict=True,
	)


def should_log(category, toggles):
	"""Unknown SN (no toggles) → always log. Otherwise honour the Check field."""

	if toggles is None:
		return True

	field = TOGGLE_BY_CATEGORY.get(category)
	if field is None:
		return bool(
			cint(toggles.get("log_adms_attendance"))
			or cint(toggles.get("log_adms_users"))
			or cint(toggles.get("log_adms_photos"))
			or cint(toggles.get("log_adms_commands"))
		)

	return bool(cint(toggles.get(field)))


def _is_operlog_heartbeat(args, body):
	"""OPERLOG/USERINFO POST with no modelled rows — Fabrixcel floods these."""

	table = (args.get("table") or args.get("Table") or "").upper()
	if table not in ("OPERLOG", "USERINFO"):
		return False

	records, _skipped = parser.parse_userinfo(body or "")
	op_rows = parser.parse_oplog(body or "")
	photo_rows = parser.parse_photo_fields(body or "")
	return not records and not op_rows and not photo_rows


def write_request_log(
	serial=None,
	endpoint=None,
	method=None,
	args=None,
	body=None,
	response=None,
	category=None,
):
	"""Append one Request Log row when Machine toggles allow. Never raises."""

	try:
		args = args or {}
		serial = (serial or args.get("SN") or args.get("sn") or "").strip() or None
		category = category or classify(endpoint, method, args)
		machine = logger.get_machine_by_serial(serial) if serial else None
		toggles = _machine_toggles(machine)

		if not should_log(category, toggles):
			return None

		if category == "Users" and _is_operlog_heartbeat(args, body):
			return None

		include_bodies = True
		if toggles is not None:
			include_bodies = bool(cint(toggles.get("log_adms_bodies")))

		query_string = "&".join(f"{k}={v}" for k, v in sorted(args.items()))

		body_preview = None
		response_preview = None
		if include_bodies:
			if body:
				body_preview = str(body)[:MAX_PREVIEW]
			if response is not None:
				response_preview = str(response)[:MAX_PREVIEW]

		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"machine": machine,
				"serial_number": serial,
				"logged_at": now_datetime(),
				"category": category,
				"method": (method or "").upper(),
				"endpoint": (endpoint or "").lower(),
				"remote_ip": remote_ip(),
				"status": 200,
				"query_string": query_string[:1000] if query_string else None,
				"body_preview": body_preview,
				"response_preview": response_preview,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	except Exception:
		frappe.logger().error("TimeBridge: failed to write ADMS request log", exc_info=True)
		return None


def clear_old_request_logs():
	"""Drop Request Log rows older than log_retention_days."""

	days = cint(frappe.db.get_single_value("TimeBridge Settings", "log_retention_days")) or 90
	if days <= 0:
		return 0

	cutoff = add_days(today(), -days)
	old = frappe.get_all(
		DOCTYPE,
		filters=[["creation", "<", cutoff]],
		pluck="name",
		limit=5000,
	)

	for name in old:
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)

	if old:
		frappe.db.commit()

	return len(old)
