# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Desk-owned Machine User writes to the terminal.

Pull: pyzk set_user / delete_user on a live session.
Push: durable DATA UPDATE/DELETE USERINFO on the ADMS command queue.

Inbound USERINFO still creates unknown PINs; it must not overwrite Desk fields
(see logger.save_users).
"""

import frappe

from frappe.utils import cint

from timebridge.timebridge.iclock import commands
from timebridge.timebridge.services.connection import get_connector, is_push_device
from timebridge.timebridge.services.machine_log import write_machine_log

PRIVILEGE_ZK = {"User": 0, "Admin": 14}


def _machine_doc(machine):
	return frappe.get_doc("TimeBridge Machine", machine)


def _push_update(machine, user_id, user_name, privilege, password, card):
	cmd = commands.format_userinfo_update(
		user_id, user_name, privilege=privilege, password=password or "", card=card or ""
	)
	commands.queue_command(machine, cmd, kind="User Update", user_id=user_id)
	return {"ok": True, "queued": True, "machine": machine}


def _push_delete(machine, user_id):
	commands.queue_command(
		machine,
		commands.format_userinfo_delete(user_id),
		kind="User Delete",
		user_id=user_id,
	)
	return {"ok": True, "queued": True, "machine": machine}


def _pull_session(device):
	connector = get_connector(device)
	conn = connector.connect(device)
	return connector, conn


def _pull_update(device, user_id, user_name, privilege, password, card, uid=None):
	connector, conn = _pull_session(device)
	try:
		connector.set_user(
			conn,
			user_id=user_id,
			name=user_name or "",
			privilege=PRIVILEGE_ZK.get(privilege, 0),
			password=password or "",
			card=card or 0,
			uid=uid,
		)
	finally:
		connector.disconnect(conn)
	return {"ok": True, "queued": False, "machine": device.name}


def _pull_delete(device, user_id, uid=None):
	connector, conn = _pull_session(device)
	try:
		connector.delete_user(conn, user_id=user_id, uid=uid)
	finally:
		connector.disconnect(conn)
	return {"ok": True, "queued": False, "machine": device.name}


def write_user_to_device(machine, user_id, user_name, privilege="User", password="", card="", uid=None):
	device = _machine_doc(machine)
	if is_push_device(device):
		return _push_update(device.name, user_id, user_name, privilege, password, card)
	return _pull_update(device, user_id, user_name, privilege, password, card, uid=uid)


def delete_user_from_device(machine, user_id, uid=None):
	device = _machine_doc(machine)
	if is_push_device(device):
		return _push_delete(device.name, user_id)
	return _pull_delete(device, user_id, uid=uid)


def upsert_local_user(machine, user_id, user_name, privilege="User", card=None, password=None):
	"""Insert or update the Desk row without treating it as a device inbound."""

	existing = frappe.db.get_value(
		"TimeBridge Machine User",
		{"machine": machine, "user_id": str(user_id).strip()},
		"name",
	)

	if existing:
		values = {"user_name": user_name, "privilege": privilege or "User"}
		if card is not None:
			values["card_number"] = card
		frappe.db.set_value("TimeBridge Machine User", existing, values)
		if password:
			frappe.db.set_value("TimeBridge Machine User", existing, "password", password)
		return existing, False

	doc = frappe.get_doc(
		{
			"doctype": "TimeBridge Machine User",
			"machine": machine,
			"user_id": str(user_id).strip(),
			"user_name": user_name or f"User {user_id}",
			"privilege": privilege or "User",
			"card_number": card,
			"is_active": 1,
		}
	)
	if password:
		doc.password = password
	doc.flags.timebridge_from_device = True
	doc.insert()
	return doc.name, True


def create_users(user_id, user_name, machines, privilege="User", card=None, password=None):
	"""
	Create PIN+name on each selected machine. PIN clash on a machine is skipped.
	"""

	user_id = str(user_id or "").strip()
	if not user_id:
		frappe.throw("User ID (PIN) is required.")
	if not machines:
		frappe.throw("Pick at least one machine.")

	results = []

	for machine in machines:
		if frappe.db.exists(
			"TimeBridge Machine User", {"machine": machine, "user_id": user_id}
		):
			results.append(
				{
					"machine": machine,
					"ok": False,
					"skipped": True,
					"message": f"PIN {user_id} already exists on this machine.",
				}
			)
			continue

		try:
			name, _created = upsert_local_user(
				machine, user_id, user_name, privilege=privilege, card=card, password=password
			)
			device_result = write_user_to_device(
				machine, user_id, user_name, privilege=privilege, password=password or "", card=card or ""
			)
			results.append(
				{
					"machine": machine,
					"machine_user": name,
					"ok": True,
					**device_result,
				}
			)
		except Exception as e:
			write_machine_log(
				machine=machine,
				level="Error",
				event="User Write",
				message=str(e),
			)
			results.append({"machine": machine, "ok": False, "message": str(e)})

	return {"user_id": user_id, "results": results}


def same_pin_users(user_id, exclude=None):
	filters = {"user_id": str(user_id).strip()}
	rows = frappe.get_all(
		"TimeBridge Machine User",
		filters=filters,
		fields=["name", "machine", "user_id", "uid"],
	)
	if exclude:
		rows = [r for r in rows if r.name != exclude]
	return rows


def update_user(machine_user, user_name=None, privilege=None, card=None, password=None, apply_same_pin=0):
	doc = frappe.get_doc("TimeBridge Machine User", machine_user)
	targets = [doc]
	if cint(apply_same_pin):
		for row in same_pin_users(doc.user_id, exclude=doc.name):
			targets.append(frappe.get_doc("TimeBridge Machine User", row.name))

	results = []
	for target in targets:
		if user_name is not None:
			target.user_name = user_name
		if privilege is not None:
			target.privilege = privilege
		if card is not None:
			target.card_number = card
		if password:
			target.password = password
		target.flags.timebridge_from_device = True
		target.save()
		try:
			device_result = write_user_to_device(
				target.machine,
				target.user_id,
				target.user_name,
				privilege=target.privilege,
				password=password or "",
				card=target.card_number or "",
				uid=target.uid,
			)
			results.append({"machine_user": target.name, "ok": True, **device_result})
		except Exception as e:
			write_machine_log(
				machine=target.machine,
				level="Error",
				event="User Write",
				message=str(e),
			)
			results.append({"machine_user": target.name, "ok": False, "message": str(e)})

	return {"results": results}


def delete_users(machine_user, apply_same_pin=0):
	doc = frappe.get_doc("TimeBridge Machine User", machine_user)
	targets = same_pin_users(doc.user_id) if cint(apply_same_pin) else [
		frappe._dict(name=doc.name, machine=doc.machine, user_id=doc.user_id, uid=doc.uid)
	]

	results = []
	for row in targets:
		try:
			device_result = delete_user_from_device(row.machine, row.user_id, uid=row.uid)
			frappe.delete_doc("TimeBridge Machine User", row.name, ignore_permissions=True)
			results.append({"machine_user": row.name, "ok": True, **device_result})
		except Exception as e:
			write_machine_log(
				machine=row.machine,
				level="Error",
				event="User Write",
				message=str(e),
			)
			results.append({"machine_user": row.name, "ok": False, "message": str(e)})

	return {"results": results}
