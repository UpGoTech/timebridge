frappe.pages["add-machine"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Add Machine"),
		single_column: true,
	});
	const $main = $(`<div class="tb-add-machine"></div>`).appendTo(page.main);
	frappe.pages["add-machine"].$main = $main;
};

frappe.pages["add-machine"].on_page_show = function () {
	$("body").removeClass("full-width");
	set_breadcrumbs();
	inject_styles();
	const $main = frappe.pages["add-machine"].$main;
	$main.off(".addm");
	render_shell($main);
	bind_events($main);
	load_push_hint($main);
	load_signals($main);
};

function set_breadcrumbs() {
	const $nb = $("#navbar-breadcrumbs");
	if (!$nb.length) return;
	$nb.empty().append(
		`<li><a href="/app/timebridge">${__("TimeBridge")}</a></li>`,
		`<li><a href="/app/timebridge-machine">${__("TimeBridge Machine")}</a></li>`,
		`<li><a href="/app/add-machine">${__("Add Machine")}</a></li>`
	);
	document.title = __("Add Machine");
}

function inject_styles() {
	$("#tb-addm-styles").remove();
	const s = document.createElement("style");
	s.id = "tb-addm-styles";
	s.textContent = `
		.tb-add-machine { max-width: 920px; margin: 0 auto; padding: 0 8px 24px; }
		.tb-am-card {
			background: var(--card-bg, #fff);
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 8px;
			padding: 16px 20px;
			margin-bottom: 16px;
			overflow: visible;
			z-index: 20;
		}
		.tb-am-intro { color: var(--text-muted); font-size: 13px; line-height: 1.5; margin: 0 0 12px; }
		.tb-am-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
		.tb-am-fg { display: flex; flex-direction: column; min-width: 160px; flex: 1; }
		.tb-am-fg-label {
			font-size: 11px; font-weight: 600; letter-spacing: .04em;
			text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px;
		}
		.tb-am-fg input, .tb-am-fg select {
			height: 32px; border-radius: 6px; border: 1px solid var(--border-color);
			padding: 0 8px;
		}
		.tb-am-fg .btn { height: 32px; }
		.tb-am-choice { display: flex; gap: 8px; margin-bottom: 12px; }
		.tb-am-pane { display: none; }
		.tb-am-pane.active { display: block; }
		.tb-am-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.tb-am-table th, .tb-am-table td { padding: 8px 10px; border-bottom: 1px solid var(--border-color); text-align: left; }
		.tb-am-empty { text-align: center; padding: 24px; color: var(--text-muted); }
		.tb-am-msg { font-size: 13px; margin-top: 10px; }
		@media (max-width: 720px) {
			.tb-am-row { flex-direction: column; }
			.tb-am-fg { min-width: 100%; }
			.tb-am-table thead { display: none; }
			.tb-am-table tr { display: block; margin-bottom: 10px; border: 1px solid var(--border-color); border-radius: 6px; }
			.tb-am-table td { display: block; border: none; }
			.tb-am-table td::before { content: attr(data-label); font-weight: 600; color: var(--text-muted); margin-right: 8px; }
		}
	`;
	document.head.appendChild(s);
}

function render_shell($main) {
	$main.html(`
		<div class="tb-am-card">
			<p class="tb-am-intro">${__(
				"Pull: this server dials the device on port 4370. Push: the device POSTs to /iclock. You choose — we cannot detect that with one probe."
			)}</p>
			<div class="tb-am-choice">
				<button type="button" class="btn btn-primary btn-sm tb-am-pick" data-mode="pull">${__("Pull (PyZK)")}</button>
				<button type="button" class="btn btn-default btn-sm tb-am-pick" data-mode="push">${__("Push (ADMS)")}</button>
			</div>
			<div class="tb-am-pane" data-pane="pull">
				<div class="tb-am-row">
					<div class="tb-am-fg"><span class="tb-am-fg-label">${__("Machine ID")}</span><input class="tb-am-mid" type="text"></div>
					<div class="tb-am-fg"><span class="tb-am-fg-label">${__("Name")}</span><input class="tb-am-mname" type="text"></div>
				</div>
				<div class="tb-am-row" style="margin-top:10px;">
					<div class="tb-am-fg"><span class="tb-am-fg-label">${__("IP")}</span><input class="tb-am-ip" type="text"></div>
					<div class="tb-am-fg"><span class="tb-am-fg-label">${__("Port")}</span><input class="tb-am-port" type="number" value="4370"></div>
					<div class="tb-am-fg"><span class="tb-am-fg-label">${__("Comm key")}</span><input class="tb-am-key" type="number" value="0"></div>
					<div class="tb-am-fg"><span class="tb-am-fg-label">&nbsp;</span>
						<button type="button" class="btn btn-default btn-sm tb-am-probe">${__("Probe")}</button>
					</div>
				</div>
				<div class="tb-am-msg tb-am-probe-msg"></div>
				<div class="tb-am-row" style="margin-top:10px;">
					<div class="tb-am-fg"><span class="tb-am-fg-label">&nbsp;</span>
						<button type="button" class="btn btn-primary btn-sm tb-am-save-pull">${__("Save and fetch")}</button>
					</div>
				</div>
			</div>
			<div class="tb-am-pane" data-pane="push">
				<p class="tb-am-intro tb-am-push-hint"></p>
				<div class="tb-am-status">${__("Waiting for device signals…")}</div>
				<div class="tb-dr-table-wrap" style="overflow-x:auto;">
					<table class="tb-am-table">
						<thead>
							<tr>
								<th>${__("Serial")}</th>
								<th>${__("Signal")}</th>
								<th>${__("IP")}</th>
								<th>${__("Last seen")}</th>
								<th>${__("Hits")}</th>
								<th></th>
							</tr>
						</thead>
						<tbody class="tb-am-rows"></tbody>
					</table>
				</div>
			</div>
		</div>
	`);
}

function bind_events($main) {
	$main.on("click.addm", ".tb-am-pick", function () {
		if ($main.data("busy")) return;
		const mode = $(this).data("mode");
		$main.find(".tb-am-pane").removeClass("active");
		$main.find(`.tb-am-pane[data-pane="${mode}"]`).addClass("active");
		$main.find(".tb-am-pick").removeClass("btn-primary").addClass("btn-default");
		$(this).removeClass("btn-default").addClass("btn-primary");
		if (mode === "push") load_signals($main);
	});

	$main.on("click.addm", ".tb-am-probe", function () {
		if ($main.data("busy")) return;
		$main.data("busy", true);
		frappe.call({
			method: "timebridge.timebridge.page.add_machine.add_machine.probe_pull",
			args: {
				ip_address: $main.find(".tb-am-ip").val(),
				port: $main.find(".tb-am-port").val(),
				communication_password: $main.find(".tb-am-key").val(),
			},
			callback(r) {
				$main.data("busy", false);
				const msg = r.message || {};
				$main.find(".tb-am-probe-msg").text(msg.message || "");
				if (msg.status === "success" && msg.info) {
					const serial = msg.info.serial_number;
					if (serial && !$main.find(".tb-am-mid").val()) {
						$main.find(".tb-am-mid").val(serial);
					}
					if (serial && !$main.find(".tb-am-mname").val()) {
						$main.find(".tb-am-mname").val(msg.info.device_name || serial);
					}
					$main.data("serial", serial);
				}
			},
			error() {
				$main.data("busy", false);
			},
		});
	});

	$main.on("click.addm", ".tb-am-save-pull", function () {
		if ($main.data("busy")) return;
		$main.data("busy", true);
		frappe.call({
			method: "timebridge.timebridge.page.add_machine.add_machine.create_pull_machine",
			args: {
				machine_id: $main.find(".tb-am-mid").val(),
				machine_name: $main.find(".tb-am-mname").val(),
				ip_address: $main.find(".tb-am-ip").val(),
				port: $main.find(".tb-am-port").val(),
				communication_password: $main.find(".tb-am-key").val(),
				serial_number: $main.data("serial"),
				fetch: 1,
			},
			callback(r) {
				$main.data("busy", false);
				frappe.set_route("Form", "TimeBridge Machine", r.message.machine);
			},
			error() {
				$main.data("busy", false);
			},
		});
	});

	$main.on("click.addm", ".tb-am-register", function () {
		if ($main.data("busy")) return;
		const name = $(this).data("name");
		const serial = $(this).data("serial");
		const ip = $(this).data("ip") || "0.0.0.0";
		frappe.prompt(
			[
				{ fieldname: "machine_id", fieldtype: "Data", label: __("Machine ID"), reqd: 1, default: serial },
				{ fieldname: "machine_name", fieldtype: "Data", label: __("Name"), reqd: 1, default: serial },
				{ fieldname: "ip_address", fieldtype: "Data", label: __("IP (informational)"), default: ip },
			],
			(values) => {
				$main.data("busy", true);
				frappe.call({
					method: "timebridge.timebridge.page.add_machine.add_machine.register_push_device",
					args: { name, ...values },
					callback(r) {
						$main.data("busy", false);
						frappe.set_route("Form", "TimeBridge Machine", r.message.machine);
					},
					error() {
						$main.data("busy", false);
					},
				});
			},
			__("Register push device")
		);
	});

	$main.on("click.addm", ".tb-am-dismiss", function () {
		frappe.call({
			method: "timebridge.timebridge.page.add_machine.add_machine.dismiss_signal",
			args: { name: $(this).data("name") },
			callback() {
				load_signals($main);
			},
		});
	});
}

function load_push_hint($main) {
	frappe.call({
		method: "timebridge.timebridge.page.add_machine.add_machine.push_server_hint",
		callback(r) {
			$main.find(".tb-am-push-hint").text((r.message || {}).hint || "");
		},
	});
}

function load_signals($main) {
	frappe.call({
		method: "timebridge.timebridge.page.add_machine.add_machine.list_pending_signals",
		callback(r) {
			const rows = r.message || [];
			const $tb = $main.find(".tb-am-rows");
			if (!rows.length) {
				$tb.html(`<tr><td colspan="6" class="tb-am-empty">${__("No unregistered push devices yet.")}</td></tr>`);
				return;
			}
			$tb.html(rows.map((row) => `
				<tr>
					<td data-label="${__("Serial")}">${frappe.utils.escape_html(row.serial_number || "")}</td>
					<td data-label="${__("Signal")}">${frappe.utils.escape_html(row.signal_type || "")}</td>
					<td data-label="${__("IP")}">${frappe.utils.escape_html(row.remote_ip || "")}</td>
					<td data-label="${__("Last seen")}">${frappe.utils.escape_html(row.last_seen || "")}</td>
					<td data-label="${__("Hits")}">${row.hit_count || 0}</td>
					<td>
						<button type="button" class="btn btn-xs btn-primary tb-am-register"
							data-name="${frappe.utils.escape_html(row.name)}"
							data-serial="${frappe.utils.escape_html(row.serial_number || "")}"
							data-ip="${frappe.utils.escape_html(row.remote_ip || "")}">${__("Register")}</button>
						<button type="button" class="btn btn-xs btn-default tb-am-dismiss"
							data-name="${frappe.utils.escape_html(row.name)}">${__("Dismiss")}</button>
					</td>
				</tr>
			`).join(""));
		},
	});
}
