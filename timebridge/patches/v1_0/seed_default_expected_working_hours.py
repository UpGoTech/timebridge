# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Spec 013: seed TimeBridge Settings.default_expected_working_hours = 9."""

import frappe

from timebridge.timebridge.services.dashboard import (
	DEFAULT_EXPECTED_WORKING_HOURS,
	ensure_default_expected_working_hours,
)


def execute():
	ensure_default_expected_working_hours()
	value = frappe.db.get_single_value(
		"TimeBridge Settings", "default_expected_working_hours"
	)
	if not value:
		frappe.throw(
			f"default_expected_working_hours must be stored (expected {DEFAULT_EXPECTED_WORKING_HOURS})"
		)
