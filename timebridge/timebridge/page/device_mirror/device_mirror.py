# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe


@frappe.whitelist()
def get_mirror_data(machine, window_days=None):
	"""Page-scoped wrapper around get_device_mirror."""

	from timebridge.timebridge.services.device_mirror import get_device_mirror

	return get_device_mirror(machine, window_days=window_days)
