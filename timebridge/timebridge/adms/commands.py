# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Commands sent back to a push device.

The device dials /iclock/getrequest asking "anything for me?". That poll is
the only channel we have. Identity writes (create/update/delete user) live in
TimeBridge Device Command so a restart cannot drop a PIN that Desk already saved.
"""

import frappe

from frappe.utils import cint, now_datetime

CONTACT_TTL = 86400
PHOTO_FETCH_TTL = 600
PHOTO_FETCH_ROUNDS = 3

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
	"""
	Persist one command for the device to collect on its next poll.

	Returns the id the device quotes back in C:<id>:<command>.
	"""

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
	"""
	Hand over queued commands and mark them Sent.

	Cleared on collection, not on completion: a device that takes a command
	and then fails must not be sent it again on a loop.
	"""

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
	"""
	Wire format: C:<id>:<command> per line. Empty list must be "OK".
	"""

	if not commands:
		return "OK"

	return "\n".join(f"C:{c['id']}:{c['command']}" for c in commands)


def request_users():
	return "DATA QUERY USERINFO"


def resend_attendance_between(start, end):
	return f"DATA QUERY ATTLOG StartTime={start}\tEndTime={end}"


def format_userinfo_update(user_id, user_name, privilege="User", password="", card=""):
	"""Push SDK DATA UPDATE USERINFO. Pri 0 = user, 14 = admin."""

	pri = "14" if privilege == "Admin" else "0"
	return (
		f"DATA UPDATE USERINFO PIN={user_id}\tName={user_name or ''}"
		f"\tPri={pri}\tPasswd={password or ''}\tCard={card or ''}\tGrp=1"
	)


def format_userinfo_delete(user_id):
	return f"DATA DELETE USERINFO PIN={user_id}"


def photo_query_round(machine, round_no):
	if round_no == 1:
		return [
			"DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=*",
			"DATA QUERY tablename=userpic\tfielddesc=*\tfilter=*",
			"DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=Type=9",
		]

	if round_no == 2:
		return [
			"DATA QUERY tablename=biophoto,fielddesc=*,filter=*",
			"DATA QUERY tablename=userpic,fielddesc=*,filter=*",
			"DATA QUERY USERPIC",
			"DATA QUERY BIOPHOTO",
		]

	pins = frappe.get_all(
		"TimeBridge Machine User",
		filters={"machine": machine},
		pluck="user_id",
	)

	out = []
	for pin in pins:
		if not pin:
			continue
		out.append(f"DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=PIN={pin}")
		out.append(f"DATA QUERY USERPIC PIN={pin}")
	return out


def start_enroll_photo_fetch(machine, baseline=0):
	frappe.cache().set_value(
		photo_fetch_key(machine),
		{"round": 1, "baseline": cint(baseline)},
		expires_in_sec=PHOTO_FETCH_TTL,
	)

	for command in photo_query_round(machine, 1):
		queue_command(machine, command, kind="Photo")


def advance_enroll_photo_fetch(machine, photos_now=0):
	if pending_count(machine):
		return None

	state = frappe.cache().get_value(photo_fetch_key(machine)) or {}

	if not state:
		return None

	if cint(photos_now) > cint(state.get("baseline")):
		return None

	current = cint(state.get("round") or 1)

	if current >= PHOTO_FETCH_ROUNDS:
		return None

	nxt = current + 1
	cmds = photo_query_round(machine, nxt)

	if not cmds:
		return None

	for command in cmds:
		queue_command(machine, command, kind="Photo")

	state["round"] = nxt
	frappe.cache().set_value(
		photo_fetch_key(machine), state, expires_in_sec=PHOTO_FETCH_TTL
	)

	return nxt


def record_contact(machine, kind):
	stamp = now_datetime()

	frappe.cache().set_value(
		contact_key(machine),
		{"at": stamp.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind},
		expires_in_sec=CONTACT_TTL,
	)

	frappe.db.set_value(
		"TimeBridge Machine", machine, "last_contact_at", stamp, update_modified=False
	)
	frappe.db.commit()


def last_contact(machine):
	cached = frappe.cache().get_value(contact_key(machine))

	if cached:
		return cached

	stored = frappe.db.get_value("TimeBridge Machine", machine, "last_contact_at")

	if not stored:
		return {}

	return {"at": str(stored)[:19], "kind": "recorded"}
