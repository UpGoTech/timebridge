// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.provide("timebridge.dashboard");

const TODAYS_PUNCH_SUMMARY_METHOD =
	"timebridge.timebridge.services.dashboard.get_users_punched_today";

function patch_todays_punch_summary_card() {
	if (frappe.widget?.__tb_todays_punch_summary_patched) {
		return;
	}

	frappe
		.require("frappe/public/js/frappe/widgets/number_card_widget.js")
		.then((module) => {
			if (frappe.widget?.__tb_todays_punch_summary_patched) {
				return;
			}

			const NumberCardWidget = module.default;
			const original_set_route = NumberCardWidget.prototype.set_route;

			NumberCardWidget.prototype.set_route = function () {
				if (this.card_doc?.method === TODAYS_PUNCH_SUMMARY_METHOD) {
					timebridge.daily_punch_summary.show({
						date: frappe.datetime.get_today(),
					});
					return;
				}
				return original_set_route.call(this);
			};

			frappe.widget.__tb_todays_punch_summary_patched = true;
		});
}

(function bootstrap_timebridge_desk() {
	if (typeof frappe === "undefined") {
		setTimeout(bootstrap_timebridge_desk, 50);
		return;
	}
	frappe.require("/assets/timebridge/js/daily_punch_summary.js").then(() => {
		frappe.ready(patch_todays_punch_summary_card);
		patch_todays_punch_summary_card();
	});
})();
