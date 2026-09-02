frappe.pages["adms-debug"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("ADMS Command Lab"),
		single_column: true,
	});
	const $main = $(`<div class="tb-adms-debug"></div>`).appendTo(page.main);
	frappe.pages["adms-debug"].$main = $main;
	frappe.pages["adms-debug"].machine_control = null;
	frappe.pages["adms-debug"].session = null;
};

frappe.pages["adms-debug"].on_page_show = function () {
	$("body").removeClass("full-width");
	set_breadcrumbs();
	inject_styles();
	const $main = frappe.pages["adms-debug"].$main;
	$main.off(".admsdbg");
	render_shell($main);
	bind_events($main);
	mount_machine_control($main);
	prefill_machine($main);
};

frappe.pages["adms-debug"].on_page_hide = function () {
	stop_poll();
};

const PRESETS = [
	{ label: "USERINFO (bare)", command: "DATA QUERY USERINFO" },
	{ label: "USERINFO PIN=1", command: "DATA QUERY USERINFO PIN=1" },
	{
		label: "user comma",
		command: "DATA QUERY tablename=user,fielddesc=*,filter=*",
	},
	{
		label: "user tab",
		command: "DATA QUERY tablename=user\tfielddesc=*\tfilter=*",
	},
	{ label: "BIODATA Type=9", command: "DATA QUERY BIODATA Type=9" },
	{ label: "INFO", command: "INFO" },
	{ label: "CHECK", command: "CHECK" },
];

let poll_timer = null;

function start_poll($main) {
	stop_poll();
	poll_timer = setInterval(() => poll_feed($main), 2000);
	poll_feed($main);
}

function stop_poll() {
	if (poll_timer) {
		clearInterval(poll_timer);
		poll_timer = null;
	}
}

function set_breadcrumbs() {
	const $nb = $("#navbar-breadcrumbs");
	if (!$nb.length) return;
	$nb.empty().append(
		`<li><a href="/app/timebridge">${__("TimeBridge")}</a></li>`,
		`<li><a href="/app/adms-debug">${__("ADMS Command Lab")}</a></li>`
	);
	document.title = __("ADMS Command Lab");
}

function inject_styles() {
	$("#tb-admsdbg-styles").remove();
	const s = document.createElement("style");
	s.id = "tb-admsdbg-styles";
	s.textContent = `
		.tb-adms-debug { max-width: 1100px; margin: 0 auto; padding: 0 8px 24px; }
		.tb-ad-card {
			background: var(--card-bg, #fff);
			border: 1px solid var(--border-color, #d1d8dd);
			border-radius: 8px;
			padding: 16px 20px;
			margin-bottom: 16px;
			overflow: visible;
		}
		.tb-ad-intro { color: var(--text-muted); font-size: 13px; line-height: 1.5; margin: 0 0 12px; }
		.tb-ad-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; }
		.tb-ad-fg { display: flex; flex-direction: column; min-width: 180px; flex: 1; }
		.tb-ad-fg-narrow { flex: 0 0 140px; min-width: 120px; }
		.tb-ad-fg-label {
			font-size: 11px; font-weight: 600; letter-spacing: .04em;
			text-transform: uppercase; color: var(--text-muted); margin-bottom: 4px;
		}
		.tb-ad-fg textarea, .tb-ad-fg select {
			border-radius: 6px; border: 1px solid var(--border-color); padding: 8px;
			font-family: var(--font-stack-monospace, monospace); font-size: 12px;
		}
		.tb-ad-fg textarea { min-height: 72px; resize: vertical; width: 100%; }
		.tb-ad-fg select { height: 32px; padding: 0 8px; }
		.tb-ad-fg .btn { height: 32px; }
		.tb-ad-link-wrap { overflow: visible; position: relative; }
		.tb-ad-link-wrap .awesomplete { z-index: 30; width: 100%; }
		.tb-ad-link-wrap .awesomplete > ul { z-index: 40; }
		.tb-ad-presets { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
		.tb-ad-presets .btn { font-size: 11px; padding: 2px 8px; }
		.tb-ad-status {
			display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
			font-size: 13px; margin-bottom: 12px; padding: 10px 12px;
			background: var(--control-bg, #f7f7f7); border-radius: 6px;
		}
		.tb-ad-status-idle { color: var(--text-muted); }
		.tb-ad-badge {
			display: inline-block; padding: 2px 8px; border-radius: 4px;
			font-size: 11px; font-weight: 600; text-transform: uppercase;
		}
		.tb-ad-badge-Queued { background: #fff3cd; color: #856404; }
		.tb-ad-badge-Sent { background: #cce5ff; color: #004085; }
		.tb-ad-badge-Done { background: #d4edda; color: #155724; }
		.tb-ad-badge-Failed { background: #f8d7da; color: #721c24; }
		.tb-ad-feed { width: 100%; border-collapse: collapse; font-size: 12px; }
		.tb-ad-feed th, .tb-ad-feed td {
			padding: 8px 10px; border-bottom: 1px solid var(--border-color); text-align: left;
			vertical-align: top;
		}
		.tb-ad-feed tr.tb-ad-warn { background: #fff8e6; }
		.tb-ad-feed tr.tb-ad-alert { background: #fdecea; }
		.tb-ad-pre {
			font-family: var(--font-stack-monospace, monospace); font-size: 11px;
			white-space: pre-wrap; word-break: break-word; max-height: 200px;
			overflow: auto; margin: 4px 0 0; color: var(--text-muted);
		}
		.tb-ad-empty { text-align: center; padding: 24px; color: var(--text-muted); }
		@media (max-width: 720px) {
			.tb-ad-row { flex-direction: column; }
			.tb-ad-fg { min-width: 100%; }
			.tb-ad-feed thead { display: none; }
			.tb-ad-feed tr { display: block; margin-bottom: 10px; border: 1px solid var(--border-color); border-radius: 6px; }
			.tb-ad-feed td { display: block; border: none; }
			.tb-ad-feed td::before { content: attr(data-label); font-weight: 600; color: var(--text-muted); margin-right: 8px; }
		}
	`;
	document.head.appendChild(s);
}

function render_shell($main) {
	$main.html(`
		<div class="tb-ad-card">
			<p class="tb-ad-intro">${__(
				"Queue a raw ADMS command against a registered push device. The device picks it up on the next /iclock/getrequest poll. Responses appear in the live feed below."
			)}</p>
			<div class="tb-ad-row">
				<div class="tb-ad-fg">
					<span class="tb-ad-fg-label">${__("Machine")}</span>
					<div class="tb-ad-link-wrap tb-ad-machine"></div>
				</div>
				<div class="tb-ad-fg tb-ad-fg-narrow">
					<span class="tb-ad-fg-label">${__("Kind")}</span>
					<select class="tb-ad-kind">
						<option value="Fetch">${__("Fetch")}</option>
						<option value="Photo">${__("Photo")}</option>
						<option value="Other">${__("Other")}</option>
					</select>
				</div>
			</div>
			<div class="tb-ad-row" style="margin-top:12px;">
				<div class="tb-ad-fg">
					<span class="tb-ad-fg-label">${__("Command")}</span>
					<textarea class="tb-ad-command" placeholder="DATA QUERY USERINFO PIN=1"></textarea>
				</div>
			</div>
			<div class="tb-ad-presets"></div>
			<div class="tb-ad-row" style="margin-top:12px;">
				<div class="tb-ad-fg tb-ad-fg-narrow">
					<span class="tb-ad-fg-label">&nbsp;</span>
					<button type="button" class="btn btn-primary btn-sm tb-ad-send">${__("Send")}</button>
				</div>
			</div>
		</div>
		<div class="tb-ad-card">
			<div class="tb-ad-status tb-ad-status-idle">${__(
				"Pick a machine and send a command to start the feed."
			)}</div>
			<div class="tb-ad-feed-wrap" style="overflow-x:auto;">
				<table class="tb-ad-feed">
					<thead>
						<tr>
							<th>${__("Time")}</th>
							<th>${__("Endpoint")}</th>
							<th>${__("Category")}</th>
							<th>${__("Query")}</th>
							<th>${__("Body")}</th>
							<th>${__("Response")}</th>
						</tr>
					</thead>
					<tbody class="tb-ad-feed-body"></tbody>
				</table>
			</div>
		</div>
	`);

	const $presets = $main.find(".tb-ad-presets");
	PRESETS.forEach((preset) => {
		$('<button type="button" class="btn btn-default btn-xs"></button>')
			.text(preset.label)
			.attr("data-command", preset.command)
			.appendTo($presets);
	});
}

function mount_machine_control($main) {
	const $mount = $main.find(".tb-ad-machine");
	$mount.empty();
	const control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			fieldname: "machine",
			options: "TimeBridge Machine",
			get_query() {
				return {
					filters: { sdk_type: "ADMS", adms_status: "Registered" },
				};
			},
			only_select: 1,
			change() {
				frappe.pages["adms-debug"].session = null;
				stop_poll();
				$main.find(".tb-ad-status")
					.addClass("tb-ad-status-idle")
					.text(__("Pick a command preset or type one, then Send."));
				$main.find(".tb-ad-feed-body").html(
					`<tr><td colspan="6" class="tb-ad-empty">${__("No traffic yet.")}</td></tr>`
				);
			},
		},
		parent: $mount,
		render_input: true,
	});
	control.$wrapper.find(".control-label, .help-box").hide();
	control.$wrapper.find(".form-group").css({ margin: 0 });
	control.$wrapper.find("input").css({ height: "32px", borderRadius: "6px" });
	frappe.pages["adms-debug"].machine_control = control;
}

function prefill_machine($main) {
	const machine =
		(frappe.route_options && frappe.route_options.machine) ||
		(frappe.route_options && frappe.route_options.machine_id);
	const control = frappe.pages["adms-debug"].machine_control;
	if (machine && control) {
		control.set_value(machine);
	}
	if (frappe.route_options) {
		delete frappe.route_options.machine;
		delete frappe.route_options.machine_id;
	}
}

function bind_events($main) {
	$main.on("click.admsdbg", ".tb-ad-presets .btn", function () {
		const command = $(this).attr("data-command") || "";
		$main.find(".tb-ad-command").val(command);
	});

	$main.on("click.admsdbg", ".tb-ad-send", function () {
		if ($main.data("busy")) return;
		const machine = get_machine($main);
		if (!machine) {
			frappe.msgprint(__("Select a registered ADMS machine."));
			return;
		}
		const command = ($main.find(".tb-ad-command").val() || "").trim();
		if (!command) {
			frappe.msgprint(__("Enter a command."));
			return;
		}
		$main.data("busy", true);
		frappe.call({
			method: "timebridge.timebridge.iclock.api.queue_raw_command",
			args: {
				machine_id: machine,
				command,
				kind: $main.find(".tb-ad-kind").val() || "Fetch",
			},
			callback(r) {
				$main.data("busy", false);
				const msg = r.message || {};
				frappe.pages["adms-debug"].session = {
					machine,
					command_id: msg.command_id,
					since: msg.queued_at,
					started_at: Date.now(),
				};
				frappe.show_alert({
					message: __("Command #{0} queued", [msg.command_id]),
					indicator: "green",
				});
				start_poll($main);
			},
			error() {
				$main.data("busy", false);
			},
		});
	});
}

function get_machine($main) {
	const control = frappe.pages["adms-debug"].machine_control;
	return control ? control.get_value() : null;
}

function poll_feed($main) {
	const session = frappe.pages["adms-debug"].session;
	if (!session || !session.machine) return;

	frappe.call({
		method: "timebridge.timebridge.iclock.api.poll_debug_feed",
		args: {
			machine_id: session.machine,
			since: session.since,
			command_id: session.command_id,
		},
		callback(r) {
			render_status($main, r.message || {}, session);
			render_feed($main, r.message || {});
		},
	});
}

function render_status($main, data, session) {
	const cmd = data.command || {};
	const elapsed = Math.floor((Date.now() - session.started_at) / 1000);
	const parts = [
		`<strong>${__("Command")} #${session.command_id || cmd.command_id || "—"}</strong>`,
	];

	if (cmd.status) {
		parts.push(
			`<span class="tb-ad-badge tb-ad-badge-${frappe.utils.escape_html(cmd.status)}">${frappe.utils.escape_html(cmd.status)}</span>`
		);
	}
	if (cmd.command) {
		parts.push(
			`<code>${frappe.utils.escape_html(cmd.command)}</code>`
		);
	}
	parts.push(`<span>${__("Elapsed")}: ${elapsed}s</span>`);
	parts.push(
		`<span>${__("Machine users")}: ${cint(data.machine_users_count)}</span>`
	);
	if (data.pending_commands) {
		parts.push(
			`<span>${__("Pending")}: ${cint(data.pending_commands)}</span>`
		);
	}

	const devicecmd = (data.parsed_devicecmd || [])[0];
	if (devicecmd) {
		const label = devicecmd.return_label || devicecmd.return_code || "";
		const cls = String(devicecmd.return_code) === "0" ? "" : " style='color:#c0392b'";
		parts.push(`<span${cls}><strong>${__("devicecmd")}:</strong> ${frappe.utils.escape_html(label)}</span>`);
	}

	$main.find(".tb-ad-status").removeClass("tb-ad-status-idle").html(parts.join(" · "));
}

function render_feed($main, data) {
	const logs = data.logs || [];
	const $body = $main.find(".tb-ad-feed-body");
	if (!logs.length) {
		$body.html(
			`<tr><td colspan="6" class="tb-ad-empty">${__("Waiting for device traffic…")}</td></tr>`
		);
		return;
	}

	$body.empty();
	logs.forEach((row) => {
		const warn =
			(row.endpoint || "").toLowerCase() === "querydata" ||
			(row.body_preview || "").includes("Return=-1004");
		const alert =
			(row.body_preview || "").includes("Return=") &&
			!(row.body_preview || "").includes("Return=0");
		let tr_class = "";
		if (alert) tr_class = "tb-ad-alert";
		else if (warn) tr_class = "tb-ad-warn";

		const body = frappe.utils.escape_html(row.body_preview || "");
		const response = frappe.utils.escape_html(row.response_preview || "");
		const $tr = $(`
			<tr class="${tr_class}">
				<td data-label="${__("Time")}">${frappe.utils.escape_html(format_time(row.logged_at))}</td>
				<td data-label="${__("Endpoint")}">${frappe.utils.escape_html(row.endpoint || "")}</td>
				<td data-label="${__("Category")}">${frappe.utils.escape_html(row.category || "")}</td>
				<td data-label="${__("Query")}"><pre class="tb-ad-pre">${frappe.utils.escape_html(row.query_string || "")}</pre></td>
				<td data-label="${__("Body")}"><pre class="tb-ad-pre">${body}</pre></td>
				<td data-label="${__("Response")}"><pre class="tb-ad-pre">${response}</pre></td>
			</tr>
		`);
		$body.append($tr);
	});
}

function format_time(value) {
	if (!value) return "";
	try {
		return frappe.datetime.str_to_user(value);
	} catch (e) {
		return value;
	}
}
