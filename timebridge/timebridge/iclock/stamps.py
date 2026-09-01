# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Stamp cursors echoed on handshake. Never persist placeholder 9999."""

from frappe.utils import now_datetime

DEFAULT_STAMP = "9999"
PLACEHOLDERS = frozenset({"9999", "0", ""})


def is_placeholder(value):
	if value is None:
		return True
	clean = str(value).strip()
	if clean in PLACEHOLDERS:
		return True
	return clean.isdigit() and set(clean) == {"9"}


def usable(value):
	if is_placeholder(value):
		return None
	return str(value).strip()


def handshake_stamps(machine_row):
	if not machine_row:
		return DEFAULT_STAMP, DEFAULT_STAMP, DEFAULT_STAMP

	att = usable(machine_row.get("adms_stamp")) or DEFAULT_STAMP
	oper = usable(machine_row.get("adms_op_stamp")) or DEFAULT_STAMP
	photo = usable(machine_row.get("adms_photo_stamp")) or DEFAULT_STAMP
	return att, oper, photo


def _from_args(args, *keys):
	for key in keys:
		if args.get(key) is not None:
			got = usable(args.get(key))
			if got:
				return got
	return None


def record_attlog_stamp(machine_name, args, records):
	stamp = _from_args(args, "Stamp", "ATTLOGStamp")
	if not stamp and records:
		stamp = records[-1].get("timestamp")
	if not stamp:
		stamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	_set(machine_name, "adms_stamp", stamp)


def record_operlog_stamp(machine_name, args, op_rows=None):
	stamp = _from_args(args, "OpStamp", "OPERLOGStamp", "Stamp")
	if not stamp and op_rows:
		stamp = op_rows[-1].get("op_time")
	if not stamp:
		stamp = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	_set(machine_name, "adms_op_stamp", stamp)


def _set(machine_name, field, value):
	import frappe

	if not machine_name or not value:
		return
	frappe.db.set_value(
		"TimeBridge Machine",
		machine_name,
		field,
		value,
		update_modified=False,
	)
