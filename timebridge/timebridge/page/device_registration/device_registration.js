frappe.pages["device-registration"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Device Registration"),
		single_column: true,
	});

	page.set_primary_action(__("Refresh"), () => load_signals());
	page.set_secondary_action(__("Auto-refresh"), toggle_auto_refresh, "octicon octicon-sync");

	const $main = $(`<div class="tb-device-reg"></div>`).appendTo(page.main);
	$main.data("page", page);

	frappe.pages["device-registration"].$main = $main;
};

frappe.pages["device-registration"].on_page_show = function () {
	$("body").removeClass("full-width");
	set_breadcrumbs();
	inject_styles();

	const $main = frappe.pages["device-registration"].$main;
	$main.off(".devreg");

	if (!$main.find(".tb-dr-card").length) {
		render_shell($main);
	}

	bind_events($main);
	load_signals();
	start_auto_refresh();
};

frappe.pages["device-registration"].on_page_hide = function () {
	stop_auto_refresh();
};

let auto_refresh_timer = null;
let auto_refresh_on = true;

function set_breadcrumbs() {
	const $nb = $("#navbar-breadcrumbs");
	if (!$nb.length) return;
	$nb.empty().append(
		`<li><a href="/app/timebridge">${__("TimeBridge")}</a></li>`,
		`<li><a href="/app/device-registration">${__("Device Registration")}</a></li>`
	);
	document.title = __("Device Registration");
}

function inject_styles() {
	if ($("#tb-device-reg-styles").length) return;
	$(`<style id="tb-device-reg-styles">
		.tb-device-reg { max-width: 1200px; margin: 0 auto; padding: 0 8px 24px; }
		.tb-dr-card {
			background: var(--card-bg, #fff);
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 8px;
			padding: 16px 20px;
			margin-bottom: 16px;
			overflow: visible;
		}
		.tb-dr-intro { color: var(--text-muted); font-size: 13px; line-height: 1.5; margin: 0 0 12px; }
		.tb-dr-status { font-size: 12px; color: var(--text-muted); margin-bottom: 12px; }
		.tb-dr-status.live { color: var(--green-600, #28a745); }
		.tb-dr-table-wrap { overflow-x: auto; }
		.tb-dr-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.tb-dr-table th {
			text-align: left; font-weight: 600; color: var(--text-muted);
			padding: 8px 10px; border-bottom: 1px solid var(--border-color);
			white-space: nowrap;
		}
		.tb-dr-table td { padding: 10px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
		.tb-dr-table tr:last-child td { border-bottom: none; }
		.tb-dr-empty { text-align: center; padding: 32px 16px; color: var(--text-muted); }
		.tb-dr-actions { display: flex; gap: 6px; flex-wrap: wrap; }
		.tb-dr-badge {
			display: inline-block; padding: 2px 8px; border-radius: 4px;
			font-size: 11px; font-weight: 600; text-transform: uppercase;
		}
		.tb-dr-badge.handshake { background: #e3f2fd; color: #1565c0; }
		.tb-dr-badge.heartbeat { background: #e8f5e9; color: #2e7d32; }
		.tb-dr-badge.upload { background: #fff3e0; color: #ef6c00; }
		.tb-dr-badge.ping { background: #f3e5f5; color: #7b1fa2; }
		.tb-dr-badge.other { background: #eceff1; color: #546e7a; }
		@media (max-width: 720px) {
			.tb-dr-table thead { display: none; }
			.tb-dr-table tr { display: block; margin-bottom: 12px; border: 1px solid var(--border-color); border-radius: 6px; padding: 8px; }
			.tb-dr-table td { display: block; border: none; padding: 4px 8px; }
			.tb-dr-table td::before { content: attr(data-label); font-weight: 600; color: var(--text-muted); display: inline-block; min-width: 90px; }
		}
	</style>`).appendTo("head");
}

function render_shell($main) {
	$main.html(`
		<div class="tb-dr-card">
			<p class="tb-dr-intro">${__(
				"ADMS push devices dial out to this server on their own schedule. " +
				"When a device sends a handshake or heartbeat whose serial number is not " +
				"registered yet, it appears here. Configure the device with your server " +
				"address and port, then watch this page while it connects."
			)}</p>
			<div class="tb-dr-status live">${__("Waiting for device signals…")}</div>
			<div class="tb-dr-table-wrap">
				<table class="tb-dr-table">
					<thead>
						<tr>
							<th>${__("Serial")}</th>
							<th>${__("Signal")}</th>
							<th>${__("Remote IP")}</th>
							<th>${__("First Seen")}</th>
							<th>${__("Last Seen")}</th>
							<th>${__("Hits")}</th>
							<th>${__("Actions")}</th>
						</tr>
					</thead>
					<tbody class="tb-dr-rows"></tbody>
				</table>
			</div>
		</div>
	`);
}

function bind_events($main) {
	$main.on("click.devreg", ".tb-dr-register", function () {
		const row = $(this).closest("tr").data("row");
		open_register_dialog(row);
	});
	$main.on("click.devreg", ".tb-dr-dismiss", function () {
		const name = $(this).data("name");
		dismiss_row(name);
	});
}

function load_signals() {
	const $main = frappe.pages["device-registration"].$main;
	if (!$main || !$main.find(".tb-dr-rows").length) return;

	frappe.call({
		method: "timebridge.timebridge.page.device_registration.device_registration.list_pending_signals",
		freeze: false,
		callback(r) {
			render_rows($main, r.message || []);
			const count = (r.message || []).length;
			const $status = $main.find(".tb-dr-status");
			$status.toggleClass("live", auto_refresh_on);
			$status.text(
				count
					? __("{0} unregistered device(s) detected — last checked {1}", [
							count,
							frappe.datetime.now_datetime(),
					  ])
					: __("No unregistered devices right now — last checked {0}", [
							frappe.datetime.now_datetime(),
					  ])
			);
		},
	});
}

function render_rows($main, rows) {
	const $tbody = $main.find(".tb-dr-rows");

	if (!rows.length) {
		$tbody.html(
			`<tr><td colspan="7" class="tb-dr-empty">${__(
				"No signals yet. Point a device at this server and wait for its first handshake."
			)}</td></tr>`
		);
		return;
	}

	$tbody.empty();

	rows.forEach((row) => {
		const badge = signal_badge(row.signal_type);
		const $tr = $(`
			<tr>
				<td data-label="${__("Serial")}"><strong>${frappe.utils.escape_html(row.serial_number)}</strong></td>
				<td data-label="${__("Signal")}">${badge}</td>
				<td data-label="${__("Remote IP")}">${frappe.utils.escape_html(row.remote_ip || "—")}</td>
				<td data-label="${__("First Seen")}">${format_dt(row.first_seen)}</td>
				<td data-label="${__("Last Seen")}">${format_dt(row.last_seen)}</td>
				<td data-label="${__("Hits")}">${row.hit_count || 0}</td>
				<td data-label="${__("Actions")}">
					<div class="tb-dr-actions">
						<button class="btn btn-primary btn-xs tb-dr-register">${__("Register")}</button>
						<button class="btn btn-default btn-xs tb-dr-dismiss" data-name="${frappe.utils.escape_html(row.name)}">${__("Dismiss")}</button>
					</div>
				</td>
			</tr>
		`);
		$tr.data("row", row);
		$tbody.append($tr);
	});
}

function signal_badge(type) {
	const key = (type || "other").toLowerCase().replace(/\s+/g, "-");
	const cls = ["handshake", "heartbeat", "upload", "ping"].includes(key.split("-")[0])
		? key.split("-")[0]
		: "other";
	return `<span class="tb-dr-badge ${cls}">${frappe.utils.escape_html(type || "Other")}</span>`;
}

function format_dt(value) {
	if (!value) return "—";
	return frappe.datetime.str_to_user(value);
}

function open_register_dialog(row) {
	const d = new frappe.ui.Dialog({
		title: __("Register Device"),
		fields: [
			{
				fieldname: "serial_number",
				fieldtype: "Data",
				label: __("Serial Number"),
				read_only: 1,
				default: row.serial_number,
			},
			{
				fieldname: "machine_id",
				fieldtype: "Data",
				label: __("Machine ID"),
				reqd: 1,
				description: __("Unique code, e.g. GATE-1"),
			},
			{
				fieldname: "machine_name",
				fieldtype: "Data",
				label: __("Machine Name"),
				reqd: 1,
			},
			{
				fieldname: "device_brand",
				fieldtype: "Select",
				label: __("Device Brand"),
				options: "ZKTeco\neSSL\nMatrix\nSuprema\nOther",
				default: "ZKTeco",
				reqd: 1,
			},
			{
				fieldname: "ip_address",
				fieldtype: "Data",
				label: __("IP Address"),
				reqd: 1,
				default: row.remote_ip || "0.0.0.0",
				description: __("Informational for ADMS — device dials out to us."),
			},
		],
		primary_action_label: __("Create Machine"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "timebridge.timebridge.page.device_registration.device_registration.register_device",
				args: {
					name: row.name,
					machine_id: values.machine_id,
					machine_name: values.machine_name,
					device_brand: values.device_brand,
					ip_address: values.ip_address,
				},
				freeze: true,
				freeze_message: __("Registering device…"),
				callback(r) {
					frappe.show_alert({
						message: __("Registered {0} as {1}", [
							r.message.serial_number,
							r.message.machine_id,
						]),
						indicator: "green",
					});
					load_signals();
					frappe.set_route("Form", "TimeBridge Machine", r.message.machine);
				},
			});
		},
	});
	d.show();
}

function dismiss_row(name) {
	frappe.confirm(__("Dismiss this signal? The device can reappear if it connects again."), () => {
		frappe.call({
			method: "timebridge.timebridge.page.device_registration.device_registration.dismiss_signal",
			args: { name },
			callback() {
				frappe.show_alert({ message: __("Signal dismissed"), indicator: "blue" });
				load_signals();
			},
		});
	});
}

function toggle_auto_refresh() {
	auto_refresh_on = !auto_refresh_on;
	if (auto_refresh_on) {
		start_auto_refresh();
		frappe.show_alert({ message: __("Auto-refresh on (every 10s)"), indicator: "green" });
	} else {
		stop_auto_refresh();
		frappe.show_alert({ message: __("Auto-refresh off"), indicator: "orange" });
	}
}

function start_auto_refresh() {
	stop_auto_refresh();
	if (!auto_refresh_on) return;
	auto_refresh_timer = setInterval(load_signals, 10000);
}

function stop_auto_refresh() {
	if (auto_refresh_timer) {
		clearInterval(auto_refresh_timer);
		auto_refresh_timer = null;
	}
}
