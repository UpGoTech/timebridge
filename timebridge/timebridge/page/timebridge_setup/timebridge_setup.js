frappe.pages["timebridge-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Timebridge Setup"),
		single_column: true,
	});

	frappe.breadcrumbs.add("TimeBridge");
	page.set_primary_action(__("Download"), download_setup_guide);
	$(frappe.render_template("timebridge_setup")).appendTo(page.body.addClass("no-border"));
};

function download_setup_guide() {
	open_url_post(frappe.request.url, {
		cmd: "timebridge.timebridge.page.timebridge_setup.timebridge_setup.download_setup_guide",
	});
}
