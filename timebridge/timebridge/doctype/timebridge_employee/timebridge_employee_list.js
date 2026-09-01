(function remap_employee_name() {
	if (frappe._timebridge_employee_name_patched) return;
	frappe._timebridge_employee_name_patched = true;
	const orig = frappe.get_user_settings;
	frappe.get_user_settings = function (doctype, key) {
		if (doctype === "TimeBridge Employee") {
			const us = frappe.model.user_settings["TimeBridge Employee"];
			if (us && us.List && us.List.sort_by === "employee_name") {
				us.List.sort_by = "employee";
				frappe.model.user_settings.save("TimeBridge Employee", "List", {
					sort_by: "employee",
				});
			}
		}
		return orig(doctype, key);
	};
})();

frappe.listview_settings["TimeBridge Employee"] = {};
