# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Apply getrequest INFO and INFO-command key=value onto the machine."""

import frappe

from timebridge.timebridge.iclock import parser


def apply_info_tuple(machine_name, info):
	parsed = parser.parse_getrequest_info(info)
	if not parsed:
		return
	_write(machine_name, parsed)


def apply_options_body(machine_name, body):
	parsed = parser.parse_options(body)
	if not parsed:
		return
	_write(machine_name, parsed)


def apply_info_command_body(machine_name, body):
	parsed = parser.parse_options(body)
	if not parsed:
		return
	_write(machine_name, parsed)


def _write(machine_name, parsed):
	updates = {}
	if parsed.get("firmware"):
		updates["adms_firmware"] = str(parsed["firmware"])[:140]
	if parsed.get("users") is not None:
		updates["adms_user_count"] = parsed["users"]
	if parsed.get("punches_total") is not None:
		updates["adms_attlog_count"] = parsed["punches_total"]
	if parsed.get("faces") is not None:
		updates["adms_face_count"] = parsed["faces"]
	if parsed.get("fingerprints") is not None:
		updates["adms_fp_count"] = parsed["fingerprints"]
	if parsed.get("photos") is not None:
		updates["adms_photo_count"] = parsed["photos"]
	if parsed.get("device_ip"):
		updates["adms_device_ip"] = parsed["device_ip"]
	if not updates:
		return
	frappe.db.set_value(
		"TimeBridge Machine", machine_name, updates, update_modified=False
	)
