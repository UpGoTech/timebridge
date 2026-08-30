// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.query_reports["Device Roll"] = {
	filters: [
		{
			fieldname: "machine",
			label: __("Machine"),
			fieldtype: "Link",
			options: "TimeBridge Machine",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.month_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
	],
};
