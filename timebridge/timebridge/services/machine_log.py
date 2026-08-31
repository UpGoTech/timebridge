# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Per-machine diagnostic log for connection, ADMS, and pull faults."""

import frappe

from frappe.utils import add_days, cint, now_datetime, today

DOCTYPE = "TimeBridge Machine Log"
MAX_DETAILS = 8000

# Routine ADMS contact at Info level — gated by enable_debug_log.
DEBUG_ONLY_EVENTS = frozenset({"Handshake", "Heartbeat", "Ping"})


def _debug_enabled():
	return cint(frappe.db.get_single_value("TimeBridge Settings", "enable_debug_log"))


def _resolve_machine(machine=None, serial=None):
	if machine:
		if not serial:
			serial = frappe.db.get_value("TimeBridge Machine", machine, "serial_number")
		return machine, serial

	serial = (serial or "").strip()
	if not serial:
		return None, None

	machine = frappe.db.get_value("TimeBridge Machine", {"serial_number": serial}, "name")
	return machine, serial


def write_machine_log(
	machine=None,
	serial=None,
	level="Info",
	event="Other",
	message="",
	details=None,
):
	"""Append one diagnostic row. Never raises."""

	try:
		level = level or "Info"
		event = event or "Other"
		message = (message or "").strip() or event

		if level == "Info" and event in DEBUG_ONLY_EVENTS and not _debug_enabled():
			return None

		machine, serial = _resolve_machine(machine, serial)

		if details:
			details = str(details)[:MAX_DETAILS]

		doc = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"machine": machine,
				"serial_number": serial,
				"logged_at": now_datetime(),
				"level": level,
				"event": event,
				"message": message[:140],
				"details": details,
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name

	except Exception:
		frappe.logger().error("TimeBridge: failed to write machine log", exc_info=True)
		return None


def clear_old_machine_logs():
	"""Drop rows older than log_retention_days. Returns count deleted."""

	days = cint(frappe.db.get_single_value("TimeBridge Settings", "log_retention_days")) or 90
	if days <= 0:
		return 0

	cutoff = add_days(today(), -days)
	old = frappe.get_all(
		DOCTYPE,
		filters=[["creation", "<", cutoff]],
		pluck="name",
		limit=5000,
	)

	for name in old:
		frappe.delete_doc(DOCTYPE, name, ignore_permissions=True, force=True)

	if old:
		frappe.db.commit()

	return len(old)
