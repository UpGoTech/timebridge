import frappe


def execute():
	if not frappe.db.exists("Workspace", "TimeBridge"):
		return

	if frappe.db.exists(
		"Workspace Link",
		{"parent": "TimeBridge", "link_to": "Employee Working Hours", "link_type": "Report"},
	):
		return

	reports_break = frappe.db.get_value(
		"Workspace Link",
		{"parent": "TimeBridge", "label": "Reports", "type": "Card Break"},
		["name", "idx"],
		as_dict=True,
	)

	if not reports_break:
		return

	punch_idx = frappe.db.get_value(
		"Workspace Link",
		{"parent": "TimeBridge", "link_to": "Punch Register", "link_type": "Report"},
		"idx",
	)

	insert_idx = (punch_idx or reports_break.idx) + 1

	for row in frappe.get_all(
		"Workspace Link",
		filters={"parent": "TimeBridge", "idx": [">=", insert_idx]},
		fields=["name", "idx"],
		order_by="idx desc",
	):
		frappe.db.set_value("Workspace Link", row.name, "idx", row.idx + 1)

	frappe.get_doc(
		{
			"doctype": "Workspace Link",
			"parent": "TimeBridge",
			"parenttype": "Workspace",
			"parentfield": "links",
			"idx": insert_idx,
			"type": "Link",
			"label": "Employee Working Hours",
			"link_type": "Report",
			"link_to": "Employee Working Hours",
			"is_query_report": 1,
			"hidden": 0,
			"onboard": 0,
			"link_count": 0,
		}
	).insert(ignore_permissions=True)

	frappe.db.set_value(
		"Workspace Link",
		reports_break.name,
		"link_count",
		frappe.db.count(
			"Workspace Link",
			{
				"parent": "TimeBridge",
				"parentfield": "links",
				"idx": [">", reports_break.idx],
				"type": "Link",
				"link_type": "Report",
			},
		),
	)
