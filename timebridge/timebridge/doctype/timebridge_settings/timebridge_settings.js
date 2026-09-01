// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

const ADMS_POLL_MS = 10000;
const INFO_POLL_MS = 2000;
const INFO_TIMEOUT_SECONDS = 120;
let adms_poll_timer = null;

frappe.ui.form.on("TimeBridge Settings", {
	refresh(frm) {
		setup_adms_console(frm);
	},

	adms_server_enabled(frm) {
		setup_adms_console(frm);
	},

	onload(frm) {
		frm.trigger("refresh");
	},
});

function setup_adms_console(frm) {
	stop_adms_poll();
	const $host = $(frm.fields_dict.adms_console_html?.wrapper || []);
	$host.find(".tb-adms-console").remove();

	if (!frm.doc.adms_server_enabled) {
		return;
	}

	const $console = $(`
		<div class="tb-adms-console">
			<div class="tb-adms-toolbar" style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">
				<button type="button" class="btn btn-default btn-sm tb-adms-refresh">${__("Refresh")}</button>
				<span class="text-muted tb-adms-updated" style="font-size:12px;"></span>
			</div>
			<div class="tb-adms-table-wrap" style="overflow-x:auto;"></div>
		</div>
	`);
	$host.append($console);

	$console.on("click", ".tb-adms-refresh", () => load_adms_roster(frm, $console));
	$console.on("click", ".tb-adms-menu-btn", function () {
		const $btn = $(this);
		show_adms_menu(frm, $btn.data(), $btn);
	});

	load_adms_roster(frm, $console);
	adms_poll_timer = setInterval(() => load_adms_roster(frm, $console), ADMS_POLL_MS);
}

function stop_adms_poll() {
	if (adms_poll_timer) {
		clearInterval(adms_poll_timer);
		adms_poll_timer = null;
	}
}

function load_adms_roster(frm, $console) {
	frappe.call({
		method: "timebridge.timebridge.iclock.api.list_adms_peers",
		callback(r) {
			const rows = r.message || [];
			const $wrap = $console.find(".tb-adms-table-wrap");
			if (!rows.length) {
				$wrap.html(`<p class="text-muted">${__("No devices have contacted the server yet.")}</p>`);
			} else {
				$wrap.html(render_adms_table(rows));
			}
			$console.find(".tb-adms-updated").text(
				__("Updated {0}", [frappe.datetime.now_datetime()])
			);
		},
	});
}

function render_adms_table(rows) {
	const head = `
		<table class="table table-bordered table-condensed" style="font-size:12px;">
			<thead><tr>
				<th>${__("Serial")}</th>
				<th>${__("Status")}</th>
				<th>${__("Machine")}</th>
				<th>${__("IP")}</th>
				<th>${__("Last seen")}</th>
				<th>${__("Activity")}</th>
				<th style="width:40px;"></th>
			</tr></thead><tbody>`;
	const body = rows.map((row) => `
		<tr>
			<td>${frappe.utils.escape_html(row.serial_number || "")}</td>
			<td>${frappe.utils.escape_html(row.status || "")}</td>
			<td>${frappe.utils.escape_html(row.machine_name || row.machine || "—")}</td>
			<td>${frappe.utils.escape_html(row.remote_ip || "")}</td>
			<td>${format_last_seen(row.last_seen_at)}</td>
			<td>${frappe.utils.escape_html(row.last_category || "—")}</td>
			<td>
				<button type="button" class="btn btn-default btn-xs tb-adms-menu-btn"
					data-serial="${frappe.utils.escape_html(row.serial_number || "")}"
					data-peer="${frappe.utils.escape_html(row.peer || "")}"
					data-machine="${frappe.utils.escape_html(row.machine || "")}"
					data-status="${frappe.utils.escape_html(row.status || "")}">
					&#8942;
				</button>
			</td>
		</tr>`).join("");
	return `${head}${body}</tbody></table>`;
}

function format_last_seen(value) {
	if (!value) return "—";
	if (typeof frappe.datetime.str_to_user === "function") {
		return frappe.utils.escape_html(frappe.datetime.str_to_user(value));
	}
	return frappe.utils.escape_html(value);
}

function show_adms_menu(frm, data, $anchor) {
	const items = [];
	const status = data.status;

	if (status === "Registered" && data.machine) {
		items.push({
			label: __("Reboot"),
			action: () => queue_device_cmd(data.machine, "REBOOT"),
		});
		items.push({
			label: __("Get info"),
			action: () => get_device_info(data.machine, data.serial),
		});
		items.push({
			label: __("Open machine"),
			action: () => frappe.set_route("Form", "TimeBridge Machine", data.machine),
		});
	} else if (status === "Pending" && data.machine) {
		items.push({
			label: __("Reboot"),
			action: () => queue_peer_cmd(data.serial),
		});
		items.push({
			label: __("Open machine"),
			action: () => frappe.set_route("Form", "TimeBridge Machine", data.machine),
		});
	} else {
		items.push({
			label: __("Reboot"),
			action: () => queue_peer_cmd(data.serial),
		});
		items.push({
			label: __("Register"),
			action: () => {
				frappe.route_options = { mode: "push" };
				frappe.set_route("add-machine");
			},
		});
	}

	if (status !== "Registered") {
		items.push({
			label: __("Dismiss"),
			action: () => dismiss_adms_peer(data, frm),
		});
	}

	const d = new frappe.ui.Dialog({
		title: __("Device: {0}", [data.serial]),
	});
	const $body = $('<div style="display:flex;flex-direction:column;gap:6px;"></div>');
	items.forEach((item) => {
		$body.append(
			$("<button type='button' class='btn btn-default btn-sm'></button>")
				.text(item.label)
				.on("click", () => {
					d.hide();
					item.action();
				})
		);
	});
	d.$body.append($body);
	d.show();
}

function dismiss_adms_peer(data, frm) {
	frappe.confirm(
		__(
			"Remove {0} from Connected Devices? The peer record is deleted; a device that is still polling will reappear.",
			[data.serial]
		),
		() => {
			frappe.call({
				method: "timebridge.timebridge.iclock.api.dismiss_adms_peer",
				args: { serial: data.serial, peer: data.peer },
				callback() {
					frappe.show_alert({ message: __("Device dismissed"), indicator: "green" });
					const $console = $(frm.fields_dict.adms_console_html?.wrapper || []).find(
						".tb-adms-console"
					);
					if ($console.length) load_adms_roster(frm, $console);
				},
			});
		}
	);
}

function queue_peer_cmd(serial) {
	frappe.call({
		method: "timebridge.timebridge.iclock.api.queue_peer_command",
		args: { serial, command: "REBOOT" },
		callback() {
			frappe.show_alert({ message: __("Reboot queued"), indicator: "green" });
		},
	});
}

function queue_device_cmd(machine, command) {
	frappe.call({
		method: "timebridge.timebridge.iclock.api.queue_device_command",
		args: { machine_id: machine, command },
		callback() {
			frappe.show_alert({
				message: __("{0} queued", [command]),
				indicator: "green",
			});
		},
	});
}

function get_device_info(machine, serial) {
	let poll_timer = null;
	let command_id = null;
	let can_close = false;

	const d = new frappe.ui.Dialog({
		title: __("Get info — {0}", [serial || machine]),
		size: "large",
	});

	d.$body.html(`
		<div class="tb-info-status text-muted" style="font-size:13px;margin-bottom:12px;"></div>
		<div class="tb-info-wait text-muted" style="font-size:12px;margin-bottom:12px;"></div>
		<div class="tb-info-result hidden"></div>
	`);

	d.footer.empty();
	const $close_btn = $(`<button type="button" class="btn btn-primary btn-sm">${__("Close")}</button>`)
		.prop("disabled", true)
		.appendTo(d.footer);
	$close_btn.on("click", () => {
		if (!can_close) return;
		stop_info_poll();
		d.hide();
	});

	d.$wrapper.modal({ backdrop: "static", keyboard: false });
	d.$wrapper.find(".modal-header .btn-close, .modal-header .close").hide();

	d.show();

	const $status = d.$body.find(".tb-info-status");
	const $wait = d.$body.find(".tb-info-wait");
	const $result = d.$body.find(".tb-info-result");

	function set_status(text, indicator) {
		const color =
			indicator === "green"
				? "var(--green-500)"
				: indicator === "orange"
					? "var(--orange-500)"
					: indicator === "red"
						? "var(--red-500)"
						: "var(--text-muted)";
		$status.html(`<span style="color:${color};">${frappe.utils.escape_html(text)}</span>`);
	}

	function render_info(info) {
		const rows = Object.entries(info || {});
		if (!rows.length) {
			return `<p class="text-muted">${__("No info fields were returned.")}</p>`;
		}
		const body = rows
			.map(
				([label, value]) =>
					`<tr><td style="width:40%;font-weight:600;">${frappe.utils.escape_html(label)}</td>` +
					`<td>${frappe.utils.escape_html(String(value))}</td></tr>`
			)
			.join("");
		return `<table class="table table-bordered table-condensed" style="font-size:13px;margin:0;"><tbody>${body}</tbody></table>`;
	}

	function finish(message, info, indicator) {
		stop_info_poll();
		can_close = true;
		$close_btn.prop("disabled", false);
		set_status(message, indicator || "green");
		$wait.text("");
		if (info && Object.keys(info).length) {
			$result.removeClass("hidden").html(render_info(info));
		}
	}

	function stop_info_poll() {
		if (poll_timer) {
			clearInterval(poll_timer);
			poll_timer = null;
		}
	}

	function poll_progress() {
		if (!command_id) return;
		frappe.call({
			method: "timebridge.timebridge.iclock.api.device_info_progress",
			args: { machine_id: machine, command_id },
			callback(r) {
				const st = r.message || {};
				if (st.phase === "done") {
					finish(st.message || __("Info received from device."), st.info, "green");
					return;
				}
				if (st.phase === "timeout" || st.phase === "error") {
					finish(st.message || __("Could not get device info."), null, "orange");
					return;
				}
				set_status(st.message || __("Waiting for device…"));
				if (st.wait_seconds != null) {
					$wait.text(__("Elapsed: {0}s / {1}s", [st.wait_seconds, INFO_TIMEOUT_SECONDS]));
				}
			},
		});
	}

	set_status(__("Queueing INFO command…"));

	frappe.call({
		method: "timebridge.timebridge.iclock.api.request_device_info",
		args: { machine_id: machine },
		callback(r) {
			const res = r.message || {};
			if (res.status !== "queued" || !res.command_id) {
				finish(__("Could not queue INFO command."), null, "red");
				return;
			}
			command_id = res.command_id;
			set_status(__("INFO command queued — waiting for device to poll…"));
			$wait.text(
				__(
					"The device checks in roughly every 30 seconds. It must poll before it can receive the command."
				)
			);
			poll_progress();
			poll_timer = setInterval(poll_progress, INFO_POLL_MS);
		},
		error() {
			finish(__("Could not reach the server."), null, "red");
		},
	});

	d.$wrapper.on("hide.bs.modal", function (e) {
		if (!can_close) {
			e.preventDefault();
			e.stopImmediatePropagation();
		} else {
			stop_info_poll();
		}
	});
}

$(window).on("hashchange", () => stop_adms_poll());
