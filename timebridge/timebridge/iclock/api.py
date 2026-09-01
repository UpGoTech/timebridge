# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Desk APIs for ADMS register / download / stats."""

import frappe
from frappe.utils import add_days, cint, now_datetime

from timebridge.timebridge.iclock import commands, discovery, peers
from timebridge.timebridge.iclock.protocol import receives
from timebridge.timebridge.iclock.server import adms_server_enabled, web_port


@frappe.whitelist()
def server_status():
	return {
		"enabled": adms_server_enabled(),
		"web_port": web_port(),
		"iclock_path": "/iclock/cdata",
	}


@frappe.whitelist()
def list_adms_peers():
	return peers.list_roster()


@frappe.whitelist()
def dismiss_adms_peer(serial=None, peer=None):
	return peers.dismiss_peer(serial=serial, peer=peer)


@frappe.whitelist()
def queue_peer_command(serial, command="REBOOT"):
	return peers.queue_serial_command(serial, command)


@frappe.whitelist()
def queue_device_command(machine_id, command="INFO"):
	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	if machine.sdk_type != "ADMS":
		frappe.throw("Only ADMS machines accept device commands.")
	if machine.adms_status != "Registered":
		frappe.throw("Register the machine before sending device commands.")

	command = (command or "INFO").strip().upper()
	if command == "REBOOT":
		payload = commands.reboot()
		kind = "Control"
	elif command == "INFO":
		payload = commands.request_info()
		kind = "Fetch"
	else:
		frappe.throw(f"Unsupported command: {command}")

	commands.queue_command(machine_id, payload, kind=kind)
	return {
		"status": "queued",
		"command": command,
		"pending_commands": commands.pending_count(machine_id),
	}


@frappe.whitelist()
def list_pending():
	return discovery.list_pending()


@frappe.whitelist()
def register_machine(name):
	return discovery.register_machine(name)


@frappe.whitelist()
def dismiss_machine(name):
	return discovery.dismiss_machine(name)


@frappe.whitelist()
def download_data(machine_id, days=30, start=None, end=None):
	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	if machine.sdk_type != "ADMS":
		frappe.throw("Download is for ADMS machines.")
	if machine.adms_status != "Registered":
		frappe.throw("Register the device before downloading.")
	if not machine.serial_number:
		frappe.throw("Serial Number is required.")

	queued = []
	if not end:
		end_dt = now_datetime()
		start_dt = add_days(end_dt, -(cint(days) or 30))
		start = start or start_dt.strftime("%Y-%m-%d 00:00:00")
		end = end_dt.strftime("%Y-%m-%d 23:59:59")

	if receives(machine.as_dict(), "receive_enrolluser") or receives(
		machine.as_dict(), "receive_chguser"
	):
		commands.queue_command(machine_id, commands.request_users(), kind="Fetch")
		queued.append("USERINFO")

	if receives(machine.as_dict(), "receive_attlog"):
		commands.queue_command(
			machine_id,
			commands.resend_attendance_between(start, end),
			kind="Fetch",
		)
		queued.append("ATTLOG")

	if any(
		receives(machine.as_dict(), field)
		for field in ("receive_userpic", "receive_face", "receive_biophoto")
	):
		for command in commands.photo_queries(machine_id):
			commands.queue_command(machine_id, command, kind="Photo")
		queued.append("photos")

	if not queued:
		return {
			"status": "empty",
			"message": "Tick at least one Receive type before downloading.",
		}

	return {
		"status": "queued",
		"queued": queued,
		"start": start,
		"end": end,
		"pending_commands": commands.pending_count(machine_id),
	}


@frappe.whitelist()
def request_device_info(machine_id):
	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	if machine.sdk_type != "ADMS":
		frappe.throw("Only ADMS machines accept INFO commands.")
	if machine.adms_status != "Registered":
		frappe.throw("Register the machine before requesting device info.")
	return commands.start_info_request(machine_id)


@frappe.whitelist()
def device_info_progress(machine_id, command_id):
	return commands.info_progress(machine_id, command_id)


@frappe.whitelist()
def refresh_stats(machine_id):
	return commands.start_info_request(machine_id)


def _require_registered_adms(machine_id):
	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	if machine.sdk_type != "ADMS":
		frappe.throw("This action is for ADMS machines only.")
	if machine.adms_status != "Registered":
		frappe.throw("Register the device before downloading data.")
	return machine


@frappe.whitelist()
def download_progress(machine_id, session_id):
	_require_registered_adms(machine_id)
	return commands.download_progress(machine_id, session_id)


@frappe.whitelist()
def download_users(machine_id):
	_require_registered_adms(machine_id)
	command_id = commands.queue_command(
		machine_id, commands.request_users(), kind="Fetch"
	)
	return commands.start_download_session(machine_id, "users", [command_id])


@frappe.whitelist()
def download_transactions(machine_id, days=30):
	_require_registered_adms(machine_id)
	end_dt = now_datetime()
	start_dt = add_days(end_dt, -(cint(days) or 30))
	start = start_dt.strftime("%Y-%m-%d 00:00:00")
	end = end_dt.strftime("%Y-%m-%d 23:59:59")
	command_id = commands.queue_command(
		machine_id,
		commands.resend_attendance_between(start, end),
		kind="Fetch",
	)
	result = commands.start_download_session(
		machine_id,
		"transactions",
		[command_id],
		meta={"start": start, "end": end, "days": cint(days) or 30},
	)
	result.update({"type": "transactions", "start": start, "end": end})
	return result


@frappe.whitelist()
def download_faces(machine_id):
	_require_registered_adms(machine_id)
	command_ids = []
	for command in commands.photo_queries(machine_id):
		command_ids.append(commands.queue_command(machine_id, command, kind="Photo"))
	return commands.start_download_session(machine_id, "faces", command_ids)


@frappe.whitelist()
def set_receive_flags(machine_id, receive_flags=None):
	_require_registered_adms(machine_id)
	flags = receive_flags or frappe.form_dict.get("receive_flags")
	if isinstance(flags, str):
		import json

		flags = json.loads(flags)
	from timebridge.timebridge.iclock.protocol import RECEIVE_FIELDS

	updates = {}
	for field in RECEIVE_FIELDS:
		if flags and field in flags:
			updates[field] = cint(flags[field])
	if not updates:
		frappe.throw("No receive flags supplied.")
	frappe.db.set_value("TimeBridge Machine", machine_id, updates, update_modified=False)
	return {"status": "ok", "updated": list(updates.keys())}
