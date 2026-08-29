frappe.pages["device-mirror"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Device Mirror"),
		single_column: true,
	});

	const $main = $(`<div class="tb-device-mirror"></div>`).appendTo(page.main);
	$main.data("page", page);
	frappe.pages["device-mirror"].$main = $main;
	frappe.pages["device-mirror"].page = page;
};

frappe.pages["device-mirror"].on_page_show = function () {
	$("body").removeClass("full-width");
	set_breadcrumbs();
	inject_styles();

	const $main = frappe.pages["device-mirror"].$main;
	$main.off(".mirror");

	if (!$main.find(".tb-dm-card").length) {
		render_shell($main);
	}

	bind_events($main);
	load_mirror();
};

frappe.pages["device-mirror"].on_page_hide = function () {
	stop_poll();
};

const MIRROR_POLL_SECONDS = 2;
let poll_timer = null;
let verifying = false;

const ASSET_ROWS = [
	{ key: "users", label: __("Users"), fetch: "users" },
	{ key: "punches", label: __("Punches"), fetch: "punches", windowed: true },
	{ key: "photos", label: __("Photos"), fetch: "photos" },
	{ key: "fingerprints", label: __("Fingerprints"), fetch: "templates" },
	{ key: "faces", label: __("Faces"), fetch: "templates" },
];

function machine_from_route() {
	const qs = frappe.utils.get_query_params(window.location.search || "");
	return (frappe.route_options && frappe.route_options.machine) || qs.machine || null;
}

function set_breadcrumbs(machine_name) {
	const $nb = $("#navbar-breadcrumbs");
	if (!$nb.length) return;
	const machine = machine_from_route();
	$nb.empty().append(
		`<li><a href="/app/timebridge">${__("TimeBridge")}</a></li>`,
		`<li><a href="/app/timebridge-machine">${__("Machines")}</a></li>`,
		`<li><a href="/app/device-mirror${machine ? "?machine=" + encodeURIComponent(machine) : ""}">${__("Device Mirror")}</a></li>`
	);
	if (machine_name) {
		$nb.append(`<li>${frappe.utils.escape_html(machine_name)}</li>`);
	}
	document.title = machine_name ? `${machine_name} — ${__("Device Mirror")}` : __("Device Mirror");
}

function inject_styles() {
	if ($("#tb-device-mirror-styles").length) return;
	$(`<style id="tb-device-mirror-styles">
		.tb-device-mirror { max-width: 1200px; margin: 0 auto; padding: 0 8px 24px; }
		.tb-dm-card {
			background: var(--card-bg, #fff);
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 8px;
			padding: 16px 20px;
			margin-bottom: 16px;
		}
		.tb-dm-header { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between; }
		.tb-dm-meta { font-size: 13px; color: var(--text-muted); }
		.tb-dm-cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 16px 0; }
		.tb-dm-summary {
			flex: 1 1 120px; min-width: 100px; padding: 12px; border-radius: 6px;
			border: 1px solid var(--border-color); text-align: center;
		}
		.tb-dm-summary .label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; }
		.tb-dm-summary .value { font-size: 18px; font-weight: 600; margin-top: 4px; }
		.tb-dm-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.tb-dm-table th {
			text-align: left; font-weight: 600; color: var(--text-muted);
			padding: 8px 10px; border-bottom: 1px solid var(--border-color);
		}
		.tb-dm-table td { padding: 10px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
		.tb-dm-badge {
			display: inline-block; padding: 2px 8px; border-radius: 4px;
			font-size: 11px; font-weight: 600;
		}
		.tb-dm-badge.in-sync { background: #e8f5e9; color: #2e7d32; }
		.tb-dm-badge.drift { background: #ffebee; color: #c62828; }
		.tb-dm-badge.ahead { background: #e3f2fd; color: #1565c0; }
		.tb-dm-badge.unknown { background: #eceff1; color: #546e7a; }
		.tb-dm-badge.stale { background: #fff3e0; color: #ef6c00; }
		.tb-dm-badge.error { background: #ffebee; color: #b71c1c; }
		.tb-dm-window { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin: 12px 0; }
		.tb-dm-empty { text-align: center; padding: 40px; color: var(--text-muted); }
	</style>`).appendTo("head");
}

function render_shell($main) {
	$main.html(`
		<div class="tb-dm-card tb-dm-header-card">
			<div class="tb-dm-header">
				<div>
					<h4 class="tb-dm-title margin-0">${__("Device Mirror")}</h4>
					<div class="tb-dm-meta tb-dm-subtitle"></div>
				</div>
				<div class="tb-dm-actions">
					<button class="btn btn-primary btn-sm tb-dm-verify">${__("Verify now")}</button>
					<button class="btn btn-default btn-sm tb-dm-settings">${__("Open Machine settings")}</button>
				</div>
			</div>
			<div class="tb-dm-window">
				<label>${__("Compare window (punches):")}</label>
				<select class="form-control input-sm tb-dm-window-select" style="width:auto;display:inline-block;">
					<option value="45">${__("Last 45 days")}</option>
					<option value="30">${__("Last 30 days")}</option>
					<option value="7">${__("Last 7 days")}</option>
					<option value="90">${__("Last 90 days")}</option>
				</select>
			</div>
			<div class="tb-dm-cards"></div>
		</div>
		<div class="tb-dm-card">
			<h5>${__("Comparison")}</h5>
			<div class="tb-dm-table-wrap" style="overflow-x:auto;">
				<table class="tb-dm-table">
					<thead>
						<tr>
							<th>${__("Asset")}</th>
							<th>${__("Device")}</th>
							<th>${__("Server")}</th>
							<th>${__("Delta")}</th>
							<th>${__("Status")}</th>
							<th>${__("Action")}</th>
						</tr>
					</thead>
					<tbody class="tb-dm-rows"></tbody>
				</table>
			</div>
		</div>
		<div class="tb-dm-card">
			<h5>${__("Verification history")}</h5>
			<div class="tb-dm-history"></div>
		</div>
	`);
}

function bind_events($main) {
	$main.on("click.mirror", ".tb-dm-verify", () => start_verify());
	$main.on("click.mirror", ".tb-dm-settings", () => open_settings());
	$main.on("change.mirror", ".tb-dm-window-select", () => load_mirror());
	$main.on("click.mirror", ".tb-dm-fetch", function () {
		const action = $(this).data("fetch");
		run_fetch(action);
	});
}

function window_days() {
	return cint($(".tb-dm-window-select").val()) || 45;
}

function load_mirror() {
	const machine = machine_from_route();

	if (!machine) {
		frappe.pages["device-mirror"].$main.html(
			`<div class="tb-dm-empty">${__("Select a machine from the Machine list, or open")} ` +
			`<a href="/app/timebridge-machine">${__("Machines")}</a>.</div>`
		);
		return;
	}

	frappe.call({
		method: "timebridge.timebridge.page.device_mirror.device_mirror.get_mirror_data",
		args: { machine, window_days: window_days() },
		callback(r) {
			render_data(r.message || {});
		},
	});
}

function render_data(data) {
	const m = data.machine || {};
	set_breadcrumbs(m.machine_name || m.name);

	const snap = data.snapshot || {};
	const asset = snap.asset_status || {};
	const server = data.server_counts || {};
	const device = (snap.device_counts || {});

	$(".tb-dm-subtitle").html(
		`${frappe.utils.escape_html(m.machine_name || "")} · ${frappe.utils.escape_html(m.sdk_type || "")}` +
		(m.serial_number ? ` · SN ${frappe.utils.escape_html(m.serial_number)}` : "") +
		(data.contact && data.contact.at ? ` · ${__("Contact")} ${data.contact.at}` : "") +
		(snap.verified_at ? `<br>${__("Last verified")}: ${snap.verified_at}` : `<br>${__("Last verified")}: —`)
	);

	const overall = snap.status || m.mirror_status || "Unknown";
	render_summary_cards(overall, asset, server, device);

	const $rows = $(".tb-dm-rows").empty();

	ASSET_ROWS.forEach((row) => {
		const a = asset[row.key] || {};
		const dev = a.device !== undefined && a.device !== null ? a.device : device[row.key];
		const srv = a.server !== undefined ? a.server : server[row.key];
		const status = a.status || "Unknown";
		const label = row.windowed
			? `${row.label} (${window_days()}d)`
			: row.label;

		$rows.append(`
			<tr>
				<td>${label}</td>
				<td>${fmt_count(dev)}</td>
				<td>${fmt_count(srv)}</td>
				<td>${fmt_delta(a.delta)}</td>
				<td>${status_badge(status)}</td>
				<td><button class="btn btn-xs btn-default tb-dm-fetch" data-fetch="${row.fetch}">${fetch_label(row.fetch)}</button></td>
			</tr>
		`);
	});

	render_history(data.history || []);
}

function render_summary_cards(overall, asset, server, device) {
	const $cards = $(".tb-dm-cards").empty();
	const items = [
		{ label: __("Overall"), status: overall },
		...ASSET_ROWS.map((r) => ({
			label: r.label,
			status: (asset[r.key] || {}).status || "Unknown",
			count: (asset[r.key] || {}).server ?? server[r.key],
		})),
	];

	items.forEach((item) => {
		$cards.append(`
			<div class="tb-dm-summary">
				<div class="label">${item.label}</div>
				<div class="value">${item.status ? status_badge(item.status) : fmt_count(item.count)}</div>
			</div>
		`);
	});
}

function render_history(rows) {
	const $h = $(".tb-dm-history").empty();

	if (!rows.length) {
		$h.html(`<p class="text-muted">${__("No verifications yet — run Verify now.")}</p>`);
		return;
	}

	const html = rows.map((r) =>
		`<div style="padding:6px 0;border-bottom:1px solid var(--border-color);font-size:13px;">
			${r.verified_at} — ${status_badge(r.status)} · ${window_days()}d window
			${r.duration_seconds ? ` · ${r.duration_seconds.toFixed(1)}s` : ""}
		</div>`
	).join("");

	$h.html(html);
}

function fmt_count(v) {
	return v === null || v === undefined ? "—" : v;
}

function fmt_delta(d) {
	if (d === null || d === undefined) return "—";
	if (d === 0) return "0";
	return d > 0 ? `+${d}` : String(d);
}

function status_badge(status) {
	const cls = (status || "unknown").toLowerCase().replace(/\s+/g, "-");
	return `<span class="tb-dm-badge ${cls}">${frappe.utils.escape_html(status || "Unknown")}</span>`;
}

function fetch_label(action) {
	const map = {
		users: __("Fetch users"),
		punches: __("Fetch punches"),
		photos: __("Fetch photos"),
		templates: __("Fetch templates"),
	};
	return map[action] || __("Fetch");
}

function start_verify() {
	const machine = machine_from_route();
	if (!machine) return;

	verifying = true;
	frappe.call({
		method: "timebridge.timebridge.api.start_mirror_verify",
		args: { machine_id: machine, window_days: window_days() },
		freeze: true,
		freeze_message: __("Starting verify…"),
		callback() {
			start_poll(machine);
		},
	});
}

function start_poll(machine) {
	stop_poll();
	poll_timer = setInterval(() => poll_progress(machine), MIRROR_POLL_SECONDS * 1000);
	poll_progress(machine);
}

function stop_poll() {
	if (poll_timer) {
		clearInterval(poll_timer);
		poll_timer = null;
	}
}

function poll_progress(machine) {
	frappe.call({
		method: "timebridge.timebridge.api.mirror_verify_progress",
		args: { machine_id: machine },
		callback(r) {
			const p = r.message || {};

			if (p.complete || p.status === "complete" || p.status === "failed") {
				stop_poll();
				verifying = false;
				load_mirror();

				if (p.status === "failed" && p.error_message) {
					frappe.msgprint({ title: __("Verify failed"), message: p.error_message, indicator: "red" });
				} else if (p.status === "complete") {
					frappe.show_alert({ message: __("Verify complete"), indicator: "green" });
				}
			}
		},
	});
}

function run_fetch(action) {
	const machine = machine_from_route();
	if (!machine) return;

	const methods = {
		users: { method: "timebridge.timebridge.api.request_device_users", args: { machine_id: machine } },
		punches: { method: "timebridge.timebridge.api.request_all_data", args: { machine_id: machine, days: window_days() } },
		photos: { method: "timebridge.timebridge.api.request_photos", args: { machine_id: machine } },
		templates: { method: "timebridge.timebridge.api.request_template_fetch", args: { machine_id: machine } },
	};

	const cfg = methods[action];
	if (!cfg) return;

	frappe.call({
		...cfg,
		freeze: true,
		freeze_message: __("Fetching…"),
		callback() {
			frappe.show_alert({ message: __("Fetch queued — re-verify when complete."), indicator: "blue" });
		},
	});
}

function open_settings() {
	const machine = machine_from_route();
	if (machine) frappe.set_route("Form", "TimeBridge Machine", machine);
}

function cint(v) {
	return parseInt(v, 10) || 0;
}
