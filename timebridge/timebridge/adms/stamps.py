# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS upload stamp bookkeeping (Stamp / OpStamp).

Legacy HTTP PUSH expects the server to remember the latest attendance and
operation markers a device reported, then echo them back on the next GET
handshake. Fixed placeholders make some firmware re-send the same log forever
even when every POST was answered with OK.
"""

import frappe

from frappe.utils import get_datetime

DEFAULT_STAMP = "9999"

ATTLOG_FIELD = "adms_stamp"
OPERLOG_FIELD = "adms_op_stamp"


def handshake_stamps(machine):
	"""Stamp values to return on GET /iclock/cdata?options=all."""

	if not machine:
		return DEFAULT_STAMP, DEFAULT_STAMP

	row = frappe.db.get_value(
		"TimeBridge Machine",
		machine,
		[ATTLOG_FIELD, OPERLOG_FIELD],
		as_dict=True,
	) or {}

	return (
		(row.get(ATTLOG_FIELD) or "").strip() or DEFAULT_STAMP,
		(row.get(OPERLOG_FIELD) or "").strip() or DEFAULT_STAMP,
	)


def parse_upload_stamp(args, table, table_raw=None):
	"""
	Read Stamp / OpStamp from query args or a compound table parameter.

	Firmware varies: ``?table=ATTLOG&Stamp=123`` vs ``?table=ATTLOG Stamp=123``.
	"""

	table = (table or "").upper()

	if table == "ATTLOG":
		keys = ("Stamp", "stamp")
	elif table in ("OPERLOG", "USERINFO"):
		keys = ("OpStamp", "opstamp", "Stamp", "stamp")
	else:
		return None

	for key in keys:
		value = (args or {}).get(key)
		if value is not None and str(value).strip():
			return str(value).strip()

	raw = table_raw if table_raw is not None else (args or {}).get("table")
	if not raw:
		return None

	for part in str(raw).split():
		if "=" not in part:
			continue
		key, _, value = part.partition("=")
		if key.strip().lower() in ("stamp", "opstamp") and value.strip():
			return value.strip()

	return None


def stamp_from_attlog_records(records):
	"""Fallback when a batch omits Stamp: latest punch time in the batch."""

	if not records:
		return None

	latest = None

	for record in records:
		try:
			stamp = get_datetime(record["timestamp"])
		except Exception:
			continue
		if latest is None or stamp > latest:
			latest = stamp

	if latest is None:
		return None

	# PUSH 3.2 manuals use yyyy-mm-ddThh:mm:ss; legacy docs also accept this shape.
	return latest.strftime("%Y-%m-%dT%H:%M:%S")


def record_attlog_stamp(machine, args, table, records):
	"""Persist attendance stamp after a batch was accepted."""

	stamp = parse_upload_stamp(args, table, (args or {}).get("table"))
	if not stamp:
		stamp = stamp_from_attlog_records(records)

	if stamp:
		_persist_stamp(machine, ATTLOG_FIELD, stamp)


def record_operlog_stamp(machine, args, table):
	"""Persist operation stamp after a user batch was accepted."""

	stamp = parse_upload_stamp(args, table, (args or {}).get("table"))
	if stamp:
		_persist_stamp(machine, OPERLOG_FIELD, stamp)


def _persist_stamp(machine, fieldname, value):
	frappe.db.set_value(
		"TimeBridge Machine",
		machine,
		fieldname,
		str(value).strip(),
		update_modified=False,
	)
