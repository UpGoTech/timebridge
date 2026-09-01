# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Write every inbound /iclock request while the server is On."""

import frappe
from frappe.utils import now_datetime

DOCTYPE = "TimeBridge ADMS Log"


def classify(endpoint, method, table=None):
	endpoint = (endpoint or "").lower()
	method = (method or "").upper()
	table = (table or "").upper()

	if endpoint == "cdata" and method in ("GET", "HEAD"):
		return "Handshake"
	if endpoint == "getrequest":
		return "Heartbeat"
	if endpoint == "ping":
		return "Ping"
	if endpoint == "devicecmd":
		return "Commands"
	if endpoint == "fdata" or table in ("ATTPHOTO", "USERPIC", "USERPHOTO", "FACE", "BIOPHOTO"):
		return "Photos"
	if table == "ATTLOG":
		return "Attendance"
	if table in ("OPERLOG", "USERINFO"):
		return "Users"
	if table == "OPTIONS":
		return "Options"
	if endpoint == "cdata":
		return "Upload"
	return "Other"


def write_log(
	serial,
	endpoint,
	method,
	args=None,
	body=None,
	response=None,
	machine=None,
	remote=None,
):
	table = None
	query = ""
	if args:
		table = args.get("table") or args.get("Table")
		try:
			import json

			query = json.dumps(args, sort_keys=True)[:2000]
		except TypeError:
			query = str(args)[:2000]

	frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"machine": machine,
			"serial_number": serial,
			"logged_at": now_datetime(),
			"category": classify(endpoint, method, table),
			"method": method,
			"endpoint": endpoint,
			"remote_ip": remote,
			"query_string": query,
			"body_preview": (body or "")[:2000] or None,
			"response_preview": (response or "")[:2000] or None,
		}
	).insert(ignore_permissions=True)


def clear_old_logs():
	days = frappe.db.get_single_value("TimeBridge Settings", "log_retention_days")
	from frappe.utils import add_days, now_datetime, cint

	days = cint(days) or 90
	cutoff = add_days(now_datetime(), -days)
	frappe.db.delete(DOCTYPE, {"logged_at": ("<", cutoff)})
