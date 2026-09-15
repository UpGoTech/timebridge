import frappe


# Old names collide with ERPNext / HR. Rename only if TimeBridge owns them.
MODULE = "TimeBridge"

RENAMES = [
	("Organization", "TimeBridge Organization"),
	("Branch", "TimeBridge Branch"),
	("Department", "TimeBridge Department"),
	("Shift", "TimeBridge Shift"),
	("Employee", "TimeBridge Employee"),
	("Biometric Machine", "TimeBridge Machine"),
	("Machine User", "TimeBridge Machine User"),
]


def execute():
	for old, new in RENAMES:
		_rename_if_ours(old, new)


def _rename_if_ours(old, new):
	if not frappe.db.exists("DocType", old):
		return
	if frappe.db.exists("DocType", new):
		return
	if frappe.db.get_value("DocType", old, "module") != MODULE:
		return

	# rename_doc rewrites Link/Table options site-wide (every app). Snapshot
	# non-TimeBridge rows first and put them back so Saral HR / ERPNext Links
	# keep pointing at Branch, Employee, etc.
	foreign = _foreign_option_rows(old)

	# In developer_mode, rename_doc also saves touched DocTypes to disk — that
	# would write TimeBridge names into other apps' JSON. Keep it off briefly.
	had_dev = frappe.conf.developer_mode
	frappe.conf.developer_mode = 0
	try:
		frappe.rename_doc("DocType", old, new, force=True, show_alert=False)
	finally:
		frappe.conf.developer_mode = had_dev

	_restore_option_rows(foreign)


def _foreign_option_rows(old):
	"""DocField / Custom Field / Property Setter options outside TimeBridge."""
	rows = []
	rows.extend(
		frappe.db.sql(
			"""
			select 'DocField' as doctype, df.name as name, df.options as value
			from `tabDocField` df
			inner join `tabDocType` dt on dt.name = df.parent
			where df.options = %s and dt.module != %s
			""",
			(old, MODULE),
			as_dict=True,
		)
	)
	rows.extend(
		frappe.db.sql(
			"""
			select 'Custom Field' as doctype, cf.name as name, cf.options as value
			from `tabCustom Field` cf
			left join `tabDocType` dt on dt.name = cf.dt
			where cf.options = %s and ifnull(dt.module, '') != %s
			""",
			(old, MODULE),
			as_dict=True,
		)
	)
	rows.extend(
		frappe.db.sql(
			"""
			select 'Property Setter' as doctype, ps.name as name, ps.value as value
			from `tabProperty Setter` ps
			left join `tabDocType` dt on dt.name = ps.doc_type
			where ps.property = 'options' and ps.value = %s
			  and ifnull(dt.module, '') != %s
			""",
			(old, MODULE),
			as_dict=True,
		)
	)
	return rows


def _restore_option_rows(rows):
	for row in rows:
		field = "value" if row.doctype == "Property Setter" else "options"
		frappe.db.set_value(row.doctype, row.name, field, row.value, update_modified=False)
