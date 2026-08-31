// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

const TODAYS_PUNCH_SUMMARY_METHOD =
	"timebridge.timebridge.services.dashboard.get_users_punched_today";

function patch_number_card_widgets() {
	const NumberCardWidget = frappe.widget?.widget_factory?.number_card;
	if (!NumberCardWidget || NumberCardWidget.__tb_number_card_patched) {
		return !!NumberCardWidget?.__tb_number_card_patched;
	}

	const original_set_route = NumberCardWidget.prototype.set_route;
	NumberCardWidget.prototype.set_route = function () {
		if (this.card_doc?.method === TODAYS_PUNCH_SUMMARY_METHOD) {
			frappe.route_options = {
				date:
					this.data?.route_options?.date ||
					frappe.datetime.get_today(),
			};
			frappe.set_route(this.data?.route || "daily-punch-summary");
			return;
		}
		return original_set_route.call(this);
	};

	NumberCardWidget.__tb_number_card_patched = true;
	return true;
}

function bind_number_card_clicks() {
	if (document.body.dataset.tbNumberCardClicks) {
		return;
	}
	document.addEventListener(
		"click",
		(e) => {
			const card = e.target.closest(".number-widget-box");
			if (!card) {
				return;
			}
			if (
				e.target.closest(
					".widget-control, .drag-handle, .dropdown-menu, .menu-btn-group"
				)
			) {
				return;
			}
			const body = card.querySelector(".widget-body");
			if (body && !body.contains(e.target)) {
				e.preventDefault();
				body.click();
			}
		},
		true
	);
	document.body.dataset.tbNumberCardClicks = "1";
}

(function bootstrap_timebridge_desk() {
	if (typeof frappe === "undefined" || typeof jQuery === "undefined") {
		setTimeout(bootstrap_timebridge_desk, 50);
		return;
	}
	const try_patch = () => {
		bind_number_card_clicks();
		if (!patch_number_card_widgets()) {
			setTimeout(try_patch, 100);
		}
	};
	frappe.ready(try_patch);
	try_patch();
})();
