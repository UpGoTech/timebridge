frappe.provide("frappe.dashboards.chart_sources");

frappe.dashboards.chart_sources["TimeBridge Active Users Per Day"] = {
	method: "timebridge.timebridge.services.dashboard.get_active_users_per_day_chart",
	filters: [],
};
