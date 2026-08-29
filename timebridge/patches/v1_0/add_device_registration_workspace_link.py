import frappe


def execute():
	if not frappe.db.exists("Workspace", "TimeBridge"):
		return

	if frappe.db.exists(
		"Workspace Link",
		{"parent": "TimeBridge", "link_to": "device-registration", "link_type": "Page"},
	):
		return

	devices_break = frappe.db.get_value(
		"Workspace Link",
		{"parent": "TimeBridge", "label": "Devices", "type": "Card Break"},
		["name", "idx"],
		as_dict=True,
	)

	if not devices_break:
		return

	machine_idx = frappe.db.get_value(
		"Workspace Link",
		{"parent": "TimeBridge", "link_to": "TimeBridge Machine", "link_type": "DocType"},
		"idx",
	)

	insert_idx = (machine_idx or devices_break.idx) + 1

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
			"label": "Device Registration",
			"link_type": "Page",
			"link_to": "device-registration",
			"is_query_report": 0,
			"hidden": 0,
			"onboard": 0,
			"link_count": 0,
		}
	).insert(ignore_permissions=True)

	frappe.db.set_value(
		"Workspace Link",
		devices_break.name,
		"link_count",
		frappe.db.count(
			"Workspace Link",
			{
				"parent": "TimeBridge",
				"parentfield": "links",
				"idx": [">", devices_break.idx],
				"type": "Link",
				"link_type": ["in", ["DocType", "Page"]],
			},
		),
	)
