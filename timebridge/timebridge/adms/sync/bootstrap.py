# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Post-registration ADMS bootstrap — queue users, recent ATTLOG, and photo fetch.
"""

import frappe

from frappe.utils import add_days, cint, now_datetime

from timebridge.timebridge.adms import commands


def queue_initial_sync(machine_name):
	"""
	Ask a newly registered push device for its roster, recent punches, and photos.

	ATTLOG window uses TimeBridge Settings.default_fetch_days (same idea as pull
	first sync). Commands wait on the next /iclock/getrequest poll.
	"""

	if not machine_name:
		return None

	sdk = frappe.db.get_value("TimeBridge Machine", machine_name, "sdk_type")
	if sdk != "ADMS":
		return None

	days = cint(frappe.db.get_single_value("TimeBridge Settings", "default_fetch_days")) or 30
	end = now_datetime()
	start = add_days(end, -days)

	frappe.db.set_value(
		"TimeBridge Machine",
		machine_name,
		"adms_bootstrap_status",
		"Pending",
		update_modified=False,
	)

	commands.queue_command(machine_name, commands.request_users(), kind="Fetch")
	commands.queue_command(
		machine_name,
		commands.resend_attendance_between(
			start.strftime("%Y-%m-%d 00:00:00"),
			end.strftime("%Y-%m-%d 23:59:59"),
		),
		kind="Fetch",
	)
	commands.start_enroll_photo_fetch(machine_name)

	frappe.db.set_value(
		"TimeBridge Machine",
		machine_name,
		"adms_bootstrap_status",
		"Queued",
		update_modified=False,
	)

	return {
		"machine": machine_name,
		"days": days,
		"status": "Queued",
	}
