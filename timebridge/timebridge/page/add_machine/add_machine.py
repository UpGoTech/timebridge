# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe

from frappe.utils import cint

from timebridge.timebridge.iclock import discovery
from timebridge.timebridge.iclock.server import adms_server_enabled, web_port
from timebridge.timebridge.sdk_connectors.pyzk_connector import PyZKConnector
from timebridge.timebridge.services.device_info import probe_socket
from timebridge.timebridge.services.pull_sync import enqueue_pull_sync


@frappe.whitelist()
def list_pending_signals():
	return discovery.list_pending()


@frappe.whitelist()
def dismiss_signal(name):
	return discovery.dismiss_machine(name)


@frappe.whitelist()
def push_server_hint():
	port = web_port()
	enabled = adms_server_enabled()
	if not enabled:
		return {
			"web_port": port,
			"iclock_path": "/iclock/cdata",
			"enabled": False,
			"hint": (
				"ADMS Server is off. Enable it in TimeBridge Settings before devices "
				"can appear here. While it is off, /iclock replies with a 404."
			),
		}
	return {
		"web_port": port,
		"iclock_path": "/iclock/cdata",
		"enabled": True,
		"hint": (
			f"On the device, set Cloud / ADMS server to this Frappe host, port {port}. "
			"Unregistered serials that GET /iclock/cdata?options=all appear below as Pending machines."
		),
	}


@frappe.whitelist()
def register_push_device(name, machine_id=None, machine_name=None, device_brand=None, ip_address=None):
	doc = frappe.get_doc("TimeBridge Machine", name)
	if machine_id:
		doc.machine_id = machine_id
	if machine_name:
		doc.machine_name = machine_name
	if ip_address:
		doc.ip_address = ip_address
	if device_brand:
		doc.device_brand = device_brand
	doc.save()
	return discovery.register_machine(name)


@frappe.whitelist()
def probe_pull(ip_address, port=4370, communication_password=0, force_udp=0):
	ip_address = (ip_address or "").strip()
	port = cint(port) or 4370

	if not ip_address:
		frappe.throw("IP address is required.")

	ok, detail = probe_socket(ip_address, port)
	if not ok:
		return {
			"status": "failed",
			"step": "network",
			"message": (
				f"Nothing answered on {ip_address}:{port} ({detail}). "
				"Wrong IP/port/password, a firewall, or a push-only unit — not proof of ADMS."
			),
		}

	device = frappe._dict(
		ip_address=ip_address,
		port=port,
		communication_password=cint(communication_password),
		force_udp=cint(force_udp),
		sdk_type="PyZK",
	)

	connector = PyZKConnector()
	conn = None
	try:
		conn = connector.connect(device)
		info = connector.get_device_info(conn)
		return {"status": "success", "info": info, "message": "Device answered ZK pull."}
	except Exception as e:
		return {
			"status": "failed",
			"step": "connect",
			"message": (
				f"Port is open but ZK pull failed: {e}. "
				"Check the comm key, or this unit may only speak ADMS push."
			),
		}
	finally:
		try:
			connector.disconnect(conn)
		except Exception:
			pass


@frappe.whitelist()
def create_pull_machine(
	machine_id,
	machine_name,
	ip_address,
	port=4370,
	communication_password=0,
	force_udp=0,
	device_brand="ZKTeco",
	serial_number=None,
	fetch=1,
):
	if frappe.db.exists("TimeBridge Machine", {"machine_id": machine_id}):
		frappe.throw(f"Machine ID {machine_id!r} already exists.")

	doc = frappe.get_doc(
		{
			"doctype": "TimeBridge Machine",
			"machine_id": machine_id,
			"machine_name": machine_name,
			"device_brand": device_brand,
			"ip_address": ip_address,
			"port": cint(port) or 4370,
			"communication_password": cint(communication_password),
			"force_udp": cint(force_udp),
			"serial_number": serial_number,
			"sdk_type": "PyZK",
			"sync_enabled": 1,
		}
	)
	doc.insert()

	queued = None
	if cint(fetch):
		queued = enqueue_pull_sync(doc.name)

	return {
		"machine": doc.name,
		"machine_id": doc.machine_id,
		"fetch": queued,
	}
