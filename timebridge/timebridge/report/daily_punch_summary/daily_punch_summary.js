// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

// Legacy Script Report route — redirect to the Desk Page with the modal UI.
frappe.query_reports["Daily Punch Summary"] = {
	onload() {
		const options = { ...(frappe.route_options || {}) };
		frappe.route_options = null;
		frappe.set_route("daily-punch-summary", options);
	},
};
