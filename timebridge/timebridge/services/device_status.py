# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Keep push-device Status in step with last contact; workspace Machine Status board."""

import frappe
from frappe.utils import format_datetime, get_datetime

from timebridge.timebridge.sdk_connectors.essl_connector import push_device_status
from timebridge.timebridge.services.connection import PUSH_SDK_TYPES


def refresh_push_device_status():
	changed = 0

	for machine in frappe.get_all(
		"TimeBridge Machine",
		filters={"sdk_type": ["in", list(PUSH_SDK_TYPES)]},
		fields=["name", "status"],
	):
		should_be = push_device_status(machine.name)

		if machine.status != should_be:
			frappe.db.set_value("TimeBridge Machine", machine.name, "status", should_be)
			changed += 1

	if changed:
		frappe.db.commit()

	return {"updated": changed}


def _live_status(row):
	"""Connected/Disconnected for the board — push uses contact age, pull uses stored status."""

	if (row.sdk_type or "") in PUSH_SDK_TYPES:
		return push_device_status(row.name)
	return row.status or "Disconnected"


def _sort_key(row):
	connected = 0 if row["status"] == "Connected" else 1
	at = get_datetime(row["last_contact_at"]) if row.get("last_contact_at") else None
	# Connected first; within each group newest contact first (None last).
	ts = -(at.timestamp()) if at else 0
	return (connected, ts)


@frappe.whitelist()
def get_machine_status_board():
	"""
	Rows for the TimeBridge workspace Machine Status custom block.

	Push status is recomputed from last contact so the board stays fresh between
	the 2-minute scheduler ticks.
	"""

	if not frappe.has_permission("TimeBridge Machine", "read"):
		frappe.throw("Not permitted", frappe.PermissionError)

	rows = frappe.get_all(
		"TimeBridge Machine",
		fields=[
			"name",
			"machine_name",
			"machine_id",
			"status",
			"sdk_type",
			"last_contact_at",
			"last_contact_kind",
		],
		order_by="machine_name asc",
	)

	board = []
	for row in rows:
		status = _live_status(row)
		at = row.last_contact_at
		board.append(
			{
				"name": row.name,
				"machine_name": row.machine_name or row.name,
				"machine_id": row.machine_id,
				"sdk_type": row.sdk_type,
				"status": status,
				"last_contact_at": format_datetime(at) if at else None,
				"last_contact_at_raw": str(at)[:19] if at else None,
				"last_contact_kind": row.last_contact_kind or None,
			}
		)

	board.sort(key=_sort_key)
	return {"machines": board}
