import frappe


DISCONTINUED_DOCTYPES = [
	"TimeBridge Attendance",
	"TimeBridge Leave",
	"TimeBridge Leave Type",
	"TimeBridge Holiday",
	"TimeBridge Shift",
	"TimeBridge Employee",
	"TimeBridge Department",
	"TimeBridge Branch",
	"TimeBridge Organization",
	"TimeBridge Biometric Template",
	"TimeBridge Device Snapshot",
	"TimeBridge Mirror Machine",
]

DISCONTINUED_PAGES = ["device-mirror", "timebridge-setup"]

DISCONTINUED_REPORTS = [
	"Attendance Report",
	"Punch Register",
	"Employee Attendance Detail",
	"Employee Working Hours",
]


def execute():
	frappe.flags.ignore_links = True

	for name in DISCONTINUED_REPORTS:
		_delete("Report", name)

	for name in DISCONTINUED_PAGES:
		_delete("Page", name)

	for name in DISCONTINUED_DOCTYPES:
		_delete("DocType", name)

	for name in (
		"TimeBridge Active Employees",
		"TimeBridge Total Employees",
	):
		_delete("Number Card", name)

	for name in (
		"TimeBridge Attendance Status",
		"TimeBridge Employees By Department",
	):
		_delete("Dashboard Chart", name)


def _delete(dt, name):
	if frappe.db.exists(dt, name):
		frappe.delete_doc(dt, name, force=1, ignore_permissions=True, delete_permanently=True)
