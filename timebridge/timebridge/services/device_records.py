# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Shared Punch Log / Machine User writes for pull and push.

Idempotency is the unique punch_key. Inbound USERINFO must not overwrite
Desk-owned name, card, or privilege.
"""

import frappe

from frappe.utils import cint, get_datetime, now_datetime

from timebridge.timebridge.doctype.timebridge_punch_log.timebridge_punch_log import (
	build_punch_key,
)

SOURCE_ADMS = "ADMS Push"
SOURCE_PYZK = "PyZK Pull"


def get_machine_by_serial(serial):
	if not serial:
		return None

	return frappe.db.get_value(
		"TimeBridge Machine",
		{"serial_number": serial},
		"name",
	)


def save_punches(machine, records, sync_batch=None, save_raw=None, source=SOURCE_ADMS):
	if save_raw is None:
		save_raw = cint(
			frappe.db.get_single_value("TimeBridge Settings", "save_raw_events")
		)

	sync_batch = sync_batch or now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	created = duplicates = invalid = unmatched = 0

	for record in records:
		try:
			timestamp = get_datetime(record["timestamp"])
		except Exception:
			invalid += 1
			continue

		punch_key = build_punch_key(machine, record["device_user_id"], timestamp)

		if frappe.db.exists("TimeBridge Punch Log", {"punch_key": punch_key}):
			duplicates += 1
			continue

		machine_user = frappe.db.get_value(
			"TimeBridge Machine User",
			{"machine": machine, "user_id": record["device_user_id"]},
			"name",
		)
		if not machine_user:
			unmatched += 1

		try:
			frappe.get_doc(
				{
					"doctype": "TimeBridge Punch Log",
					"machine": machine,
					"device_user_id": record["device_user_id"],
					"machine_user": machine_user,
					"timestamp": timestamp,
					"punch_direction": record.get("punch_direction") or "Unknown",
					"verify_mode": record.get("verify_mode"),
					"device_status": record.get("device_status"),
					"source": source,
					"sync_batch": sync_batch,
					"raw_payload": record.get("raw") if save_raw else None,
				}
			).insert(ignore_permissions=True)
			created += 1
		except frappe.exceptions.UniqueValidationError:
			duplicates += 1

	return {
		"created": created,
		"duplicates": duplicates,
		"invalid": invalid,
		"unmatched": unmatched,
		"sync_batch": sync_batch,
	}


def save_users(machine, records):
	created = updated = 0

	for record in records:
		existing = frappe.db.get_value(
			"TimeBridge Machine User",
			{"machine": machine, "user_id": record["user_id"]},
			"name",
		)

		if existing:
			flag_changes = {}
			if record.get("finger_count") is not None:
				flag_changes["finger_count"] = cint(record.get("finger_count"))
			if record.get("face_registered") is not None:
				flag_changes["face_registered"] = cint(record.get("face_registered"))
			if flag_changes:
				frappe.db.set_value("TimeBridge Machine User", existing, flag_changes)
				updated += 1
			continue

		doc = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine User",
				"machine": machine,
				"user_id": record["user_id"],
				"user_name": record["user_name"],
				"card_number": record.get("card_number"),
				"privilege": record.get("privilege") or "User",
				"finger_count": cint(record.get("finger_count")),
				"face_registered": cint(record.get("face_registered")),
				"is_active": 1,
			}
		)
		doc.flags.adms_inbound = True
		doc.insert(ignore_permissions=True)
		created += 1

	return {"created": created, "updated": updated}


def link_unmatched_punches(machine):
	unmatched = frappe.get_all(
		"TimeBridge Punch Log",
		filters={"machine": machine, "machine_user": ("is", "not set")},
		fields=["name", "device_user_id"],
		limit=20000,
	)
	linked = 0
	for punch in unmatched:
		machine_user = frappe.db.get_value(
			"TimeBridge Machine User",
			{"machine": machine, "user_id": punch.device_user_id},
			"name",
		)
		if not machine_user:
			continue
		frappe.db.set_value("TimeBridge Punch Log", punch.name, "machine_user", machine_user)
		linked += 1
	return linked


def open_sync_log(machine, sync_type, sync_batch):
	doc = frappe.get_doc(
		{
			"doctype": "TimeBridge Sync Log",
			"machine": machine,
			"sync_type": sync_type,
			"status": "Running",
			"started_at": now_datetime(),
			"sync_batch": sync_batch,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def close_sync_log(name, status, fetched=0, created=0, skipped=0, error=None):
	if not name:
		return
	frappe.db.set_value(
		"TimeBridge Sync Log",
		name,
		{
			"status": status,
			"records_fetched": fetched,
			"records_created": created,
			"records_skipped": skipped,
			"error_message": error,
			"finished_at": now_datetime(),
		},
	)
