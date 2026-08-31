# Spec 005: Active Users Per Day chart default timespan is Last Week.

import json
import os

import frappe
from frappe.modules.import_file import import_file_by_path

CHART_NAME = "TimeBridge Active Users Per Day"


def execute():
	path = os.path.join(
		frappe.get_app_path("timebridge"),
		"timebridge",
		"dashboard_chart",
		"timebridge_active_users_per_day",
		"timebridge_active_users_per_day.json",
	)
	import_file_by_path(path, force=True, ignore_version=True)

	if frappe.db.exists("Dashboard Chart", CHART_NAME):
		frappe.db.set_value("Dashboard Chart", CHART_NAME, "timespan", "Last Week")

	for row in frappe.get_all("Dashboard Settings", fields=["name", "chart_config"]):
		if not row.chart_config:
			continue

		config = json.loads(row.chart_config)
		chart_cfg = config.get(CHART_NAME)
		if not chart_cfg or chart_cfg.get("timespan") != "Last Month":
			continue

		chart_cfg.pop("timespan", None)
		if not chart_cfg:
			config.pop(CHART_NAME, None)

		frappe.db.set_value(
			"Dashboard Settings",
			row.name,
			"chart_config",
			json.dumps(config) if config else None,
		)

	frappe.db.commit()
