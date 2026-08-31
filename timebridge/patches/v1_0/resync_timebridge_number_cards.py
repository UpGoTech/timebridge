# Re-import TimeBridge Number Card fixtures (fixes stale Biometric Machine filters).

import os

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
	base = os.path.join(
		frappe.get_app_path("timebridge"),
		"timebridge",
		"number_card",
	)
	for folder in sorted(os.listdir(base)):
		path = os.path.join(base, folder, f"{folder}.json")
		if os.path.isfile(path):
			import_file_by_path(path, force=True, ignore_version=True)

	frappe.db.commit()
