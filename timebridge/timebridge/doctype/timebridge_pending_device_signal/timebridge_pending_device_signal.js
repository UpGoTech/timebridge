// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.ui.form.on("TimeBridge Pending Device Signal", {
	refresh(frm) {
		if (frm.doc.status === "Pending" && frm.doc.registered_machine) {
			frm.add_custom_button(__("Open Machine"), () => {
				frappe.set_route("Form", "TimeBridge Machine", frm.doc.registered_machine);
			});
		}
	},
});
