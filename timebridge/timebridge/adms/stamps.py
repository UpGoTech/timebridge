# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS upload stamp bookkeeping (Stamp / OpStamp / AttLogStamp).

Legacy HTTP PUSH expects the server to remember the latest attendance and
operation markers a device reported, then echo them back on the next GET
handshake. Fixed placeholders make some firmware re-send the same log forever
even when every POST was answered with OK.

The Attendance PUSH spec (§11.2) encodes punch times as YYYY-MM-DD HH:MM:SS.
When a device always sends placeholder Stamp=9999, fall back to the latest
punch or operation time in a format chosen per machine (Attendance DateTime
by default).
"""

import frappe

from frappe.utils import cint, get_datetime, now_datetime

DEFAULT_STAMP = "9999"

# Firmwares often send these instead of a real upload marker. Treating them as
# meaningful stamps leaves the handshake stuck at 9999 forever.
PLACEHOLDER_STAMPS = frozenset({"9999", "0", ""})

STAMP_FORMAT_UNIX = "Unix Timestamp"
STAMP_FORMAT_ISO = "ISO DateTime"
STAMP_FORMAT_ATTLOG = "Attendance DateTime"
STAMP_FORMAT_COMPACT = "Compact (YYYYMMDDHHMMSS)"
STAMP_FORMAT_AUTO = "Auto"

ATTLOG_FIELD = "adms_stamp"
OPERLOG_FIELD = "adms_op_stamp"
STAMP_FORMAT_FIELD = "adms_stamp_format"


def is_placeholder_stamp(value):
	"""True when the device sent a sentinel, not a real upload marker."""

	if value is None:
		return True

	clean = str(value).strip()
	if clean in PLACEHOLDER_STAMPS:
		return True

	# 9999, 99999999, and similar all-nine markers are never real cursors.
	if clean.isdigit() and set(clean) == {"9"}:
		return True

	return False


def normalize_upload_stamp(value):
	"""Return a stamp worth persisting, or None for placeholders / blanks."""

	if value is None:
		return None

	clean = str(value).strip()
	if is_placeholder_stamp(clean):
		return None

	return clean


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
		_normalize_handshake_stamp(row.get(ATTLOG_FIELD)),
		_normalize_handshake_stamp(row.get(OPERLOG_FIELD)),
	)


def _normalize_handshake_stamp(value):
	clean = normalize_upload_stamp(value)
	if clean:
		return clean
	return DEFAULT_STAMP


def parse_upload_stamp(args, table, table_raw=None):
	"""
	Read Stamp / AttLogStamp / OpStamp from query args or a compound table param.

	Firmware varies: ``?table=ATTLOG&Stamp=123`` vs ``?table=ATTLOG Stamp=123``.
	"""

	table = (table or "").upper()

	if table == "ATTLOG":
		keys = ("attlogstamp", "stamp")
	elif table in ("OPERLOG", "USERINFO"):
		keys = ("operlogstamp", "opstamp", "stamp")
	else:
		return None

	# Firmwares disagree on capitalisation — the spec writes ATTLOGStamp, this
	# device sends Stamp, others send AttLogStamp. Match on the lowered name so
	# a casing we have not seen is not read as a missing stamp.
	lowered = {str(key).strip().lower(): value for key, value in (args or {}).items()}

	for key in keys:
		value = lowered.get(key)
		if value is not None and str(value).strip():
			return normalize_upload_stamp(value)

	raw = table_raw if table_raw is not None else (args or {}).get("table")
	if not raw:
		return None

	for part in str(raw).split():
		if "=" not in part:
			continue
		key, _, value = part.partition("=")
		key_lower = key.strip().lower()
		if key_lower in ("stamp", "opstamp", "attlogstamp", "operlogstamp") and value.strip():
			return normalize_upload_stamp(value.strip())

	return None


def infer_stamp_format(stored_stamp):
	"""Guess how to encode punch-time fallbacks from an existing cursor."""

	clean = normalize_upload_stamp(stored_stamp)
	if not clean:
		return STAMP_FORMAT_ATTLOG

	if clean.isdigit():
		if len(clean) == 14:
			return STAMP_FORMAT_COMPACT
		return STAMP_FORMAT_UNIX

	if "T" in clean:
		return STAMP_FORMAT_ISO

	if " " in clean and "-" in clean and ":" in clean:
		return STAMP_FORMAT_ATTLOG

	return STAMP_FORMAT_ATTLOG


def resolve_stamp_format(machine):
	"""Effective stamp encoding for punch-time fallbacks on this machine."""

	if not machine:
		return STAMP_FORMAT_ATTLOG

	configured = frappe.db.get_value("TimeBridge Machine", machine, STAMP_FORMAT_FIELD)
	if configured and configured != STAMP_FORMAT_AUTO:
		return configured

	stored = frappe.db.get_value("TimeBridge Machine", machine, ATTLOG_FIELD)
	return infer_stamp_format(stored)


def resolve_operlog_stamp_format(machine):
	"""Stamp encoding for OPERLOG fallbacks — follow oper stamp, then attlog."""

	if not machine:
		return STAMP_FORMAT_ATTLOG

	stored = frappe.db.get_value("TimeBridge Machine", machine, OPERLOG_FIELD)
	if normalize_upload_stamp(stored):
		return infer_stamp_format(stored)

	return resolve_stamp_format(machine)


def format_datetime_stamp(value, stamp_format=None):
	"""Encode one datetime in the chosen stamp format."""

	stamp_format = stamp_format or STAMP_FORMAT_ATTLOG

	if stamp_format == STAMP_FORMAT_ISO:
		return value.strftime("%Y-%m-%dT%H:%M:%S")

	if stamp_format == STAMP_FORMAT_ATTLOG:
		return value.strftime("%Y-%m-%d %H:%M:%S")

	if stamp_format == STAMP_FORMAT_COMPACT:
		return value.strftime("%Y%m%d%H%M%S")

	return str(cint(value.timestamp()))


def stamp_from_attlog_records(records, stamp_format=None):
	"""Fallback when a batch omits Stamp: latest punch time in the chosen format."""

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

	return format_datetime_stamp(latest, stamp_format or STAMP_FORMAT_ATTLOG)


def stamp_from_operlog_rows(op_rows, stamp_format=None):
	"""Fallback when OPERLOG omits Stamp: latest OPLOG row time in the batch."""

	if not op_rows:
		return None

	latest = None

	for row in op_rows:
		try:
			stamp = get_datetime(row.get("op_time"))
		except Exception:
			continue
		if latest is None or stamp > latest:
			latest = stamp

	if latest is None:
		return None

	return format_datetime_stamp(latest, stamp_format or STAMP_FORMAT_ATTLOG)


def stamp_now(stamp_format=None):
	"""Last-resort cursor when a POST carried no usable Stamp or row times."""

	return format_datetime_stamp(now_datetime(), stamp_format or STAMP_FORMAT_ATTLOG)


def record_attlog_stamp(machine, args, table, records):
	"""Persist attendance stamp after a batch was accepted."""

	stamp_format = resolve_stamp_format(machine)
	stamp = parse_upload_stamp(args, table, (args or {}).get("table"))
	if not stamp:
		stamp = stamp_from_attlog_records(records, stamp_format)

	if stamp:
		_persist_stamp(machine, ATTLOG_FIELD, stamp)


def record_operlog_stamp(machine, args, table, op_rows=None, heartbeat=False):
	"""Persist operation stamp after an OPERLOG/USERINFO batch was accepted."""

	stamp_format = resolve_operlog_stamp_format(machine)
	stamp = parse_upload_stamp(args, table, (args or {}).get("table"))
	if not stamp:
		stamp = stamp_from_operlog_rows(op_rows or [], stamp_format)
	if not stamp:
		# Fabrixcel Gate always sends OpStamp=9999 on empty OPERLOG heartbeats
		# and ignores Attendance DateTime cursors in OPERLOGStamp.
		if heartbeat:
			stamp_format = STAMP_FORMAT_UNIX
		stamp = stamp_now(stamp_format)

	if stamp:
		_persist_stamp(machine, OPERLOG_FIELD, stamp)


def stamp_is_newer(candidate, current):
	"""True when candidate should replace current as the upload cursor."""

	if not candidate or is_placeholder_stamp(candidate):
		return False

	if not current or is_placeholder_stamp(current):
		return True

	candidate_s = str(candidate).strip()
	current_s = str(current).strip()

	if candidate_s == current_s:
		return False

	if candidate_s.isdigit() and current_s.isdigit():
		return int(candidate_s) > int(current_s)

	try:
		return get_datetime(candidate_s) > get_datetime(current_s)
	except Exception:
		pass

	# Unknown shape — accept the new value so duplicate batches still advance.
	return True


def _persist_stamp(machine, fieldname, value):
	clean = str(value).strip()
	if not clean or is_placeholder_stamp(clean):
		return

	current = frappe.db.get_value("TimeBridge Machine", machine, fieldname)
	if not stamp_is_newer(clean, current):
		return

	frappe.db.set_value(
		"TimeBridge Machine",
		machine,
		fieldname,
		clean,
		update_modified=False,
	)
