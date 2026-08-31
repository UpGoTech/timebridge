// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.ui.form.on("TimeBridge Machine User", {
	refresh(frm) {
		if (frm.is_new()) return;

		frm.add_custom_button(__("Save to Device"), () => {
			frappe.call({
				method: "timebridge.timebridge.api.update_device_user",
				args: {
					machine_user: frm.doc.name,
					user_name: frm.doc.user_name,
					privilege: frm.doc.privilege,
					card: frm.doc.card_number,
					apply_same_pin: 0,
				},
				freeze: true,
				callback(r) {
					const failed = (r.message.results || []).filter((x) => !x.ok);
					frappe.show_alert({
						message: failed.length ? failed[0].message : __("Sent to device"),
						indicator: failed.length ? "red" : "green",
					});
				},
			});
		});

		frm.add_custom_button(__("Delete from Device"), () => {
			frappe.confirm(__("Delete this PIN from Desk and from the device?"), () => {
				frappe.prompt(
					[
						{
							fieldname: "apply_same_pin",
							fieldtype: "Check",
							label: __("Also other machines with this PIN"),
						},
					],
					(values) => {
						frappe.call({
							method: "timebridge.timebridge.api.delete_device_user",
							args: {
								machine_user: frm.doc.name,
								apply_same_pin: values.apply_same_pin ? 1 : 0,
							},
							freeze: true,
							callback() {
								frappe.set_route("List", "TimeBridge Machine User");
							},
						});
					},
					__("Delete User")
				);
			});
		});
	},
});
