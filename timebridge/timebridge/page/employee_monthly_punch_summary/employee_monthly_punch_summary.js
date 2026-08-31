frappe.pages["employee-monthly-punch-summary"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Employee Monthly Punch Summary"),
		single_column: false,
	});
	wrapper._emps_page = page;
	frappe.pages["employee-monthly-punch-summary"].$wrapper = $(wrapper);
};

frappe.pages["employee-monthly-punch-summary"].on_page_show = function (wrapper) {
	$("body").removeClass("full-width");
	set_breadcrumbs();

	const page = wrapper._emps_page;
	const $main = $(wrapper).find(".layout-main-section");
	const $sidebar = page.sidebar;
	$main.empty();
	$sidebar.empty();

	const machine_user =
		(frappe.route_options && frappe.route_options.machine_user) || "";
	const month =
		(frappe.route_options && frappe.route_options.month) ||
		frappe.datetime.get_today().slice(0, 7) + "-01";
	frappe.route_options = null;

	frappe.require("/assets/timebridge/js/employee_monthly_punch_summary.js").then(() => {
		timebridge.employee_monthly_punch_summary.render_inline($main, {
			machine_user,
			month,
			$sidebar,
		});
	});
};

function set_breadcrumbs() {
	const $nb = $("#navbar-breadcrumbs");
	if (!$nb.length) return;
	$nb.empty().append(
		`<li><a href="/app/timebridge">${__("TimeBridge")}</a></li>`,
		`<li><a href="/app/employee-monthly-punch-summary">${__("Employee Monthly Punch Summary")}</a></li>`
	);
	document.title = __("Employee Monthly Punch Summary");
}
