// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.listview_settings["TimeBridge Machine Log"] = {
	get_indicator(doc) {
		const colors = {
			Error: "red",
			Warning: "orange",
			Info: "blue",
		};
		return [__(doc.level), colors[doc.level] || "grey", `level,=,${doc.level}`];
	},
};
