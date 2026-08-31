# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Keep push-device Status in step with last contact."""

import frappe

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
