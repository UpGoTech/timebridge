// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

// Legacy Script Report route — redirect to the Desk Page.
frappe.query_reports["Employee Monthly Punch Summary"] = {
	onload() {
		const options = { ...(frappe.route_options || {}) };
		frappe.route_options = null;
		frappe.set_route("employee-monthly-punch-summary", options);
	},
};
