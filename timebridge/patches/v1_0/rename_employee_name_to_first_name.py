import frappe


def execute():
	"""Keep existing names when employee_name becomes first_name."""
	doctype = "TimeBridge Employee"
	if not frappe.db.table_exists(doctype):
		return
	if not frappe.db.has_column(doctype, "employee_name"):
		return
	if frappe.db.has_column(doctype, "first_name"):
		frappe.db.sql(
			"""
			UPDATE `tabTimeBridge Employee`
			SET first_name = employee_name
			WHERE IFNULL(first_name, '') = '' AND IFNULL(employee_name, '') != ''
			"""
		)
		return

	frappe.db.sql(
		"ALTER TABLE `tabTimeBridge Employee` RENAME COLUMN `employee_name` TO `first_name`"
	)
	frappe.db.sql(
		"""
		UPDATE `tabDocField`
		SET fieldname = 'first_name', label = 'First Name'
		WHERE parent = 'TimeBridge Employee' AND fieldname = 'employee_name'
		"""
	)
