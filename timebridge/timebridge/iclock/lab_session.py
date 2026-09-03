# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Command Lab scrap sessions — observe device traffic without persisting anything."""

import json

import frappe
from frappe.utils import cint, now_datetime

from timebridge.timebridge.iclock import audit, commands, discovery, handshake, parser, photos

LAB_SESSION_TTL = 900
LAB_CAPTURE_MAX = 200
PREVIEW_LIMIT = 4000


def _session_key(machine):
	return f"timebridge_adms_lab_session::{machine}"


def _command_id_key(machine):
	return f"timebridge_adms_lab_command_id::{machine}"


def _next_lab_command_id(machine):
	current = cint(
		frappe.cache().get_value(_command_id_key(machine), expires=True)
	)
	next_id = current + 1 if current else 1
	frappe.cache().set_value(
		_command_id_key(machine), next_id, expires_in_sec=LAB_SESSION_TTL
	)
	return next_id


def _save_session(machine, session):
	frappe.cache().set_value(
		_session_key(machine), session, expires_in_sec=LAB_SESSION_TTL
	)


def get_session(machine):
	# expires=True — TTL keys must not poison frappe.local.cache with a sticky None
	# after the first miss (set_value with expires_in_sec skips the local cache).
	return frappe.cache().get_value(_session_key(machine), expires=True)


def is_active(machine):
	return bool(machine and get_session(machine))


def is_active_serial(serial):
	row = discovery.machine_row(serial)
	return bool(row and is_active(row.name))


def queue_lab_command(machine, command):
	"""Queue a lab command in the scrap session (Redis only — never Device Command)."""

	command_id = _next_lab_command_id(machine)
	queued_at = now_datetime()
	session = get_session(machine) or {}
	pending = list(session.get("pending") or [])
	pending.append({"id": command_id, "command": command})
	session.update(
		{
			"command_id": cint(command_id),
			"command": command,
			"status": "Queued",
			"queued_at": str(queued_at)[:19],
			"sent_at": None,
			"done_at": None,
			"pending": pending,
			"captures": list(session.get("captures") or []),
		}
	)
	_save_session(machine, session)
	return {
		"status": "queued",
		"command_id": command_id,
		"command": command,
		"queued_at": queued_at,
		"pending_commands": len(pending),
		"scrap_mode": True,
	}


def pop_lab_commands(machine):
	session = get_session(machine) or {}
	pending = list(session.get("pending") or [])
	if not pending:
		return []
	session["pending"] = []
	session["status"] = "Sent"
	session["sent_at"] = str(now_datetime())[:19]
	_save_session(machine, session)
	return pending


def pending_lab_command_count(machine):
	session = get_session(machine) or {}
	return len(session.get("pending") or [])


def mark_lab_command_done(machine, command_id):
	session = get_session(machine)
	if not session or cint(session.get("command_id")) != cint(command_id):
		return
	session["status"] = "Done"
	session["done_at"] = str(now_datetime())[:19]
	_save_session(machine, session)


def _query_string(args):
	if not args:
		return ""
	try:
		return json.dumps(args, sort_keys=True)[:2000]
	except TypeError:
		return str(args)[:2000]


def capture(machine, *, endpoint, method, args=None, body=None, response=None):
	session = get_session(machine)
	if not session:
		return
	now = str(now_datetime())[:19]
	table = None
	if args:
		table = (
			args.get("table")
			or args.get("Table")
			or args.get("tablename")
			or args.get("TableName")
		)
	entry = {
		"name": f"lab-{machine}-{len(session.get('captures') or []) + 1}",
		"logged_at": now,
		"endpoint": endpoint,
		"category": audit.classify(endpoint, method, table),
		"method": method,
		"query_string": _query_string(args),
		"body_preview": (body or "")[:PREVIEW_LIMIT] or None,
		"response_preview": (response or "")[:PREVIEW_LIMIT] or None,
	}
	captures = list(session.get("captures") or [])
	captures.append(entry)
	if len(captures) > LAB_CAPTURE_MAX:
		captures = captures[-LAB_CAPTURE_MAX:]
	session["captures"] = captures
	_save_session(machine, session)


def get_captures(machine, since=None, limit=50):
	session = get_session(machine) or {}
	captures = list(session.get("captures") or [])
	if since:
		since_text = str(since)[:19]
		captures = [row for row in captures if (row.get("logged_at") or "") >= since_text]
	limit = min(cint(limit) or 50, LAB_CAPTURE_MAX)
	return captures[-limit:]


def session_command_row(machine):
	session = get_session(machine)
	if not session:
		return None
	return {
		"command_id": session.get("command_id"),
		"command": session.get("command"),
		"status": session.get("status"),
		"queued_at": session.get("queued_at"),
		"sent_at": session.get("sent_at"),
	}


def handle_scrap_request(serial, endpoint, args, body, method, raw=None):
	"""Ack device traffic without writing logs or ingesting into any DocType."""

	row = discovery.machine_row(serial)
	if not row or row.adms_status != "Registered":
		reply = "OK"
		capture_serial = row.name if row else None
		if capture_serial and is_active(capture_serial):
			capture(
				capture_serial,
				endpoint=endpoint,
				method=method,
				args=args,
				body=body,
				response=reply,
			)
		return reply

	machine = row.name
	endpoint = (endpoint or "").lower()

	if endpoint == "getrequest":
		pending = pop_lab_commands(machine)
		reply = commands.format_commands(pending)
	elif endpoint == "cdata":
		reply = _scrap_cdata(row, serial, args, body, method)
	elif endpoint == "devicecmd":
		for result in parser.parse_devicecmd_results(body):
			try:
				command_id = cint(result.get("ID"))
			except (TypeError, ValueError):
				continue
			if command_id:
				mark_lab_command_done(machine, command_id)
		reply = "OK"
	elif endpoint == "querydata":
		table = (args.get("tablename") or args.get("TableName") or "").lower()
		query_type = (args.get("type") or "").lower()
		if query_type == "tabledata" and table == "user":
			records, _skipped = parser.parse_querydata_users(body)
			reported = cint(args.get("count"))
			count = reported if reported else len(records)
			reply = f"user={count or 0}"
		else:
			count = parser.body_line_count(body)
			reply = handshake.ack(count or 1)
	elif endpoint == "fdata":
		reply = handshake.ack(1)
	elif endpoint == "ping":
		reply = "OK"
	else:
		count = parser.body_line_count(body)
		reply = handshake.ack(count or 1)

	capture(
		machine,
		endpoint=endpoint,
		method=method,
		args=args,
		body=body,
		response=reply,
	)
	return reply


def _scrap_cdata(row, serial, args, body, method):
	if method in ("GET", "HEAD"):
		if row.adms_status == "Registered":
			return handshake.build_handshake(serial, row)
		return "OK"

	table = parser.parse_table_name(args.get("table"))
	if table == "ATTLOG":
		records, skipped = parser.parse_attlog(body)
		return handshake.ack(len(records) + len(skipped) or 1)
	if table in ("OPERLOG", "USERINFO"):
		count = parser.body_line_count(body)
		return handshake.ack(count or 1)
	if table in photos.PHOTO_TABLES:
		rows = parser.parse_photo_fields(body)
		return handshake.ack(len(rows) or 1)
	if table == "OPTIONS":
		return "OK"
	return handshake.ack(parser.body_line_count(body) or 1)
