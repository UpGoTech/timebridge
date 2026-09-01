# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Desk → device USERINFO when a Machine User is edited on an ADMS machine."""

import frappe

from timebridge.timebridge.services.connection import is_push_device
from timebridge.timebridge.services.user_write import write_user_to_device


def on_machine_user_update(doc, method=None):
	if getattr(doc.flags, "adms_inbound", False):
		return

	if not (
		doc.has_value_changed("user_name")
		or doc.has_value_changed("card_number")
		or doc.has_value_changed("privilege")
		or doc.has_value_changed("password")
	):
		return

	if not doc.machine:
		return

	device = frappe.get_doc("TimeBridge Machine", doc.machine)
	if not is_push_device(device):
		return

	write_user_to_device(
		doc.machine,
		doc.user_id,
		doc.user_name or "",
		privilege=doc.privilege or "User",
		password=doc.password or "",
		card=doc.card_number or "",
	)
