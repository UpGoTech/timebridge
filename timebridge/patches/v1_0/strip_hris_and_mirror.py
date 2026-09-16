import frappe


# DocTypes removed from the codebase. NEVER delete them here — delete_doc on a
# DocType drops the table and destroys every row (TimeBridge Employee, etc.).
# Leave orphans in the DB; operators can archive after export if they want.
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
		_delete_meta("Report", name)

	for name in DISCONTINUED_PAGES:
		_delete_meta("Page", name)

	# Intentionally do not delete DISCONTINUED_DOCTYPES — see list comment.

	for name in (
		"TimeBridge Active Employees",
		"TimeBridge Total Employees",
	):
		_delete_meta("Number Card", name)

	for name in (
		"TimeBridge Attendance Status",
		"TimeBridge Employees By Department",
	):
		_delete_meta("Dashboard Chart", name)


def _delete_meta(dt, name):
	"""Remove Desk chrome only (reports/pages/cards). Never DocTypes or documents."""
	if dt == "DocType":
		frappe.logger("timebridge").warning(
			"refusing to delete DocType %s from strip_hris_and_mirror", name
		)
		return
	if frappe.db.exists(dt, name):
		frappe.delete_doc(dt, name, force=1, ignore_permissions=True, delete_permanently=True)
