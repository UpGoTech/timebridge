# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Queue commands for the device's next /iclock/getrequest poll."""

import frappe
from frappe.utils import cint, now_datetime

CONTACT_TTL = 86400
PHOTO_FETCH_TTL = 600
DOCTYPE = "TimeBridge Device Command"


def contact_key(machine):
	return f"timebridge_adms_last_contact::{machine}"


def photo_fetch_key(machine):
	return f"timebridge_photo_fetch::{machine}"


def _next_command_id(machine):
	last = frappe.db.sql(
		"""
		SELECT MAX(command_id) FROM `tabTimeBridge Device Command`
		WHERE machine = %s
		""",
		machine,
	)[0][0]
	return cint(last) + 1


def queue_command(machine, command, kind="Other", user_id=None):
	command_id = _next_command_id(machine)
	frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"machine": machine,
			"command_id": command_id,
			"command": command,
			"kind": kind,
			"user_id": user_id,
			"status": "Queued",
			"queued_at": now_datetime(),
		}
	).insert(ignore_permissions=True)
	return command_id


def pop_commands(machine):
	rows = frappe.get_all(
		DOCTYPE,
		filters={"machine": machine, "status": "Queued"},
		fields=["name", "command_id", "command"],
		order_by="command_id asc",
	)
	pending = []
	now = now_datetime()
	for row in rows:
		frappe.db.set_value(
			DOCTYPE,
			row.name,
			{"status": "Sent", "sent_at": now},
			update_modified=False,
		)
		pending.append({"id": row.command_id, "command": row.command})
	return pending


def pending_count(machine):
	return frappe.db.count(DOCTYPE, {"machine": machine, "status": "Queued"})


def format_commands(commands):
	if not commands:
		return "OK"
	return "\n".join(f"C:{c['id']}:{c['command']}" for c in commands)


def request_users():
	return "DATA QUERY USERINFO"


def resend_attendance_between(start, end):
	return f"DATA QUERY ATTLOG StartTime={start}\tEndTime={end}"


def request_info():
	return "INFO"


def format_userinfo_update(user_id, user_name, privilege="User", password="", card=""):
	pri = "14" if privilege == "Admin" else "0"
	return (
		f"DATA UPDATE USERINFO PIN={user_id}\tName={user_name or ''}"
		f"\tPri={pri}\tPasswd={password or ''}\tCard={card or ''}\tGrp=1"
	)


def format_userinfo_delete(user_id):
	return f"DATA DELETE USERINFO PIN={user_id}"


def photo_queries(machine):
	return [
		"DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=*",
		"DATA QUERY tablename=userpic\tfielddesc=*\tfilter=*",
		"DATA QUERY USERPIC",
		"DATA QUERY BIOPHOTO",
	]


def start_enroll_photo_fetch(machine, baseline=0):
	frappe.cache().set_value(
		photo_fetch_key(machine),
		{"round": 1, "baseline": cint(baseline)},
		expires_in_sec=PHOTO_FETCH_TTL,
	)
	for command in photo_queries(machine):
		queue_command(machine, command, kind="Photo")


def advance_enroll_photo_fetch(machine, photos_now=0):
	return None


def record_contact(machine, kind):
	stamp = now_datetime()
	frappe.cache().set_value(
		contact_key(machine),
		{"at": stamp.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind},
		expires_in_sec=CONTACT_TTL,
	)
	frappe.db.set_value(
		"TimeBridge Machine",
		machine,
		"last_contact_at",
		stamp,
		update_modified=False,
	)


def last_contact(machine):
	cached = frappe.cache().get_value(contact_key(machine))
	if cached:
		return cached
	stored = frappe.db.get_value("TimeBridge Machine", machine, "last_contact_at")
	if not stored:
		return {}
	return {"at": str(stored)[:19], "kind": "recorded"}
