# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Helpers for the ADMS Command Lab debug page."""

import re

import frappe
from frappe.utils import cint, now_datetime

from timebridge.timebridge.iclock import commands, parser

COMMAND_PREFIX = re.compile(r"^C:\d+:", re.I)
MAX_COMMAND_LEN = 500
ALLOWED_KINDS = frozenset({"Fetch", "Photo", "Other", "User Update", "User Delete"})

RETURN_LABELS = {
	"0": "OK",
	"-1": "Failed",
	"-1004": "Data and equipment configuration inconsistent",
	"-1005": "Data too long",
	"-1006": "Memory error",
}


def normalize_raw_command(command):
	command = (command or "").strip()
	if COMMAND_PREFIX.match(command):
		command = COMMAND_PREFIX.sub("", command, count=1).strip()
	return command


def return_label(code):
	if code is None or code == "":
		return ""
	text = str(code).strip()
	label = RETURN_LABELS.get(text)
	return f"{text} ({label})" if label else text


def queue_raw_command(machine_id, command, kind="Fetch"):
	command = normalize_raw_command(command)
	if not command:
		frappe.throw("Command is required.")
	if len(command) > MAX_COMMAND_LEN:
		frappe.throw(f"Command must be at most {MAX_COMMAND_LEN} characters.")

	kind = (kind or "Fetch").strip()
	if kind not in ALLOWED_KINDS:
		frappe.throw(f"Unsupported kind: {kind}")

	queued_at = now_datetime()
	command_id = commands.queue_command(machine_id, command, kind=kind)
	return {
		"status": "queued",
		"command_id": command_id,
		"command": command,
		"kind": kind,
		"queued_at": queued_at,
		"pending_commands": commands.pending_count(machine_id),
	}


def _command_row(machine_id, command_id):
	if not command_id:
		return None
	rows = frappe.get_all(
		"TimeBridge Device Command",
		filters={"machine": machine_id, "command_id": cint(command_id)},
		fields=["name", "command_id", "command", "kind", "status", "queued_at", "sent_at"],
		limit=1,
	)
	return rows[0] if rows else None


def _parse_devicecmd_from_logs(logs):
	parsed = []
	seen = set()
	for row in logs:
		body = row.get("body_preview") or ""
		if "Return=" not in body and "ID=" not in body:
			continue
		for result in parser.parse_devicecmd_results(body):
			key = (
				result.get("ID"),
				result.get("RETURN"),
				result.get("CMD"),
			)
			if key in seen:
				continue
			seen.add(key)
			parsed.append(
				{
					"id": result.get("ID"),
					"return_code": result.get("RETURN"),
					"return_label": return_label(result.get("RETURN")),
					"cmd": result.get("CMD"),
					"log": row.get("name"),
					"logged_at": row.get("logged_at"),
				}
			)
	return parsed


def poll_debug_feed(machine_id, since=None, command_id=None, limit=50):
	limit = min(cint(limit) or 50, 200)
	filters = {"machine": machine_id}
	if since:
		filters["logged_at"] = [">=", since]

	logs = frappe.get_all(
		"TimeBridge ADMS Log",
		filters=filters,
		fields=[
			"name",
			"logged_at",
			"endpoint",
			"category",
			"method",
			"query_string",
			"body_preview",
			"response_preview",
		],
		order_by="logged_at asc",
		limit=limit,
	)

	machine_users_count = frappe.db.count(
		"TimeBridge Machine User", {"machine": machine_id}
	)

	return {
		"command": _command_row(machine_id, command_id),
		"logs": logs,
		"parsed_devicecmd": _parse_devicecmd_from_logs(logs),
		"machine_users_count": machine_users_count,
		"pending_commands": commands.pending_count(machine_id),
	}
