frappe.pages["daily-punch-summary"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Daily Punch Summary"),
		single_column: false,
	});
	wrapper._dps_page = page;
	frappe.pages["daily-punch-summary"].$wrapper = $(wrapper);
};

frappe.pages["daily-punch-summary"].on_page_show = function (wrapper) {
	$("body").removeClass("full-width");
	set_breadcrumbs();

	const page = wrapper._dps_page;
	const $main = $(wrapper).find(".layout-main-section");
	const $sidebar = page.sidebar;
	$main.empty();
	$sidebar.empty();

	const date =
		(frappe.route_options && frappe.route_options.date) || frappe.datetime.get_today();
	const machine = (frappe.route_options && frappe.route_options.machine) || "";
	frappe.route_options = null;

	frappe.require("/assets/timebridge/js/daily_punch_summary.js").then(() => {
		timebridge.daily_punch_summary.render_inline($main, {
			date,
			machine,
			$sidebar,
		});
	});
};

function set_breadcrumbs() {
	const $nb = $("#navbar-breadcrumbs");
	if (!$nb.length) return;
	$nb.empty().append(
		`<li><a href="/app/timebridge">${__("TimeBridge")}</a></li>`,
		`<li><a href="/app/daily-punch-summary">${__("Daily Punch Summary")}</a></li>`
	);
	document.title = __("Daily Punch Summary");
}
