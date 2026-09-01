// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

const ADMS_POLL_MS = 10000;
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
			<td>${frappe.utils.escape_html(row.last_seen_at || "—")}</td>
			<td>${frappe.utils.escape_html(row.last_category || "—")}</td>
			<td>
				<button type="button" class="btn btn-default btn-xs tb-adms-menu-btn"
					data-serial="${frappe.utils.escape_html(row.serial_number || "")}"
					data-machine="${frappe.utils.escape_html(row.machine || "")}"
					data-status="${frappe.utils.escape_html(row.status || "")}">
					&#8942;
				</button>
			</td>
		</tr>`).join("");
	return `${head}${body}</tbody></table>`;
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
			label: __("Refresh stats"),
			action: () => queue_device_cmd(data.machine, "INFO"),
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
			label: __("Add push machine"),
			action: () => add_push_machine(data.serial),
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

function add_push_machine(serial) {
	frappe.call({
		method: "timebridge.timebridge.page.add_machine.add_machine.create_push_machine",
		args: {
			serial_number: serial,
			machine_id: serial,
			machine_name: serial,
		},
		callback(r) {
			frappe.set_route("Form", "TimeBridge Machine", r.message.machine);
		},
	});
}

$(window).on("hashchange", () => stop_adms_poll());
