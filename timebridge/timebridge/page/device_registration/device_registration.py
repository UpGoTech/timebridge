# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe

from timebridge.timebridge.adms import pending


@frappe.whitelist()
def list_pending_signals():
    return pending.list_pending()


@frappe.whitelist()
def dismiss_signal(name):
    pending.dismiss_signal(name)
    return {"ok": True}


@frappe.whitelist()
def register_device(
    name,
    machine_id,
    machine_name,
    device_brand="ZKTeco",
    ip_address=None,
):
    return pending.register_machine(
        name,
        machine_id,
        machine_name,
        device_brand,
        ip_address or "0.0.0.0",
    )
