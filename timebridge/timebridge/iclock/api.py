# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Desk APIs for ADMS register / download / stats."""

import frappe
from frappe.utils import add_days, cint, now_datetime

from timebridge.timebridge.iclock import commands, discovery
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
def refresh_stats(machine_id):
	commands.queue_command(machine_id, commands.request_info(), kind="Fetch")
	return {"status": "queued", "pending_commands": commands.pending_count(machine_id)}
