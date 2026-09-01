// Copyright (c) 2026, UPGO and contributors
// Machine form console — clean ADMS / PyZK operator panel.

frappe.provide("timebridge.machine_console");

(function () {
	const POLL_MS = 2000;
	const INFO_TIMEOUT_SECONDS = 120;
	const DOWNLOAD_TIMEOUT_SECONDS = 180;

	const ADMS_FEATURES = [
		{
			id: "realtime",
			label: __("Realtime attendance"),
			help: __("Device may push punches as they happen."),
			fields: { receive_attlog: 1 },
		},
		{
			id: "users",
			label: __("Users"),
			help: __("Accept enrolled user uploads from the device."),
			fields: { receive_enrolluser: 1, receive_chguser: 1 },
		},
		{
			id: "faces",
			label: __("Faces & photos"),
			help: __("Accept face templates and user pictures."),
			fields: { receive_face: 1, receive_userpic: 1, receive_biophoto: 1 },
		},
	];

	const HIDDEN_ALWAYS = [
		"adms_stamp",
		"adms_op_stamp",
		"adms_stamp_format",
		"adms_photo_stamp",
		"adms_handshake_at",
		"adms_last_init_at",
		"adms_pushver",
		"adms_language",
		"adms_pushcommkey",
		"adms_last_query",
		"adms_firmware",
		"adms_user_count",
		"adms_attlog_count",
		"adms_face_count",
		"adms_fp_count",
		"adms_photo_count",
		"adms_device_ip",
		"adms_receive_section",
		"receive_attlog",
		"receive_oplog",
		"receive_attphoto",
		"receive_enrolluser",
		"receive_chguser",
		"receive_enrollfp",
		"receive_chgfp",
		"receive_fpimage",
		"receive_face",
		"receive_userpic",
		"receive_workcode",
		"receive_biophoto",
		"status",
		"last_contact_at",
		"sync_enabled",
		"last_sync",
		"last_user_sync",
		"adms_status",
		"adms_stats_section",
		"description",
	];

	timebridge.machine_console.setup = function (frm) {
		inject_styles();
		hide_clutter(frm);
		const $host = $(frm.fields_dict.machine_console_html?.wrapper || []);
		$host.find(".tb-machine-console").remove();
		if (frm.is_new()) {
			return;
		}
		if ((frm.doc.sdk_type || "") === "ADMS") {
			setup_adms_console(frm, $host);
		} else {
			setup_pyzk_console(frm, $host);
		}
	};

	function hide_clutter(frm) {
		HIDDEN_ALWAYS.forEach((field) => {
			if (frm.fields_dict[field]) {
				frm.toggle_display(field, false);
			}
		});
		frm.toggle_display("connection_information", (frm.doc.sdk_type || "") !== "ADMS");
		if ((frm.doc.sdk_type || "") === "ADMS") {
			["port", "communication_type", "communication_password", "force_udp"].forEach((f) => {
				if (frm.fields_dict[f]) frm.toggle_display(f, false);
			});
		}
	}

	function inject_styles() {
		if ($("#tb-machine-console-styles").length) return;
		const s = document.createElement("style");
		s.id = "tb-machine-console-styles";
		s.textContent = `
			.tb-machine-console {
				max-width: 920px;
				margin: 8px 0 16px;
				font-size: 13px;
				color: var(--text-color);
			}
			.tb-mc-card {
				background: var(--card-bg, #fff);
				border: 1px solid var(--border-color, #d1d8dd);
				border-radius: 8px;
				padding: 16px 18px;
				margin-bottom: 12px;
			}
			.tb-mc-head {
				display: flex;
				flex-wrap: wrap;
				align-items: center;
				justify-content: space-between;
				gap: 10px;
				margin-bottom: 12px;
			}
			.tb-mc-title { font-size: 15px; font-weight: 600; margin: 0; }
			.tb-mc-badge {
				display: inline-block;
				padding: 2px 10px;
				border-radius: 999px;
				font-size: 11px;
				font-weight: 600;
				text-transform: uppercase;
				letter-spacing: .04em;
			}
			.tb-mc-badge.pending { background: var(--orange-100, #fef3e2); color: var(--orange-700, #c45c00); }
			.tb-mc-badge.registered { background: var(--green-100, #e8f5e9); color: var(--green-700, #2e7d32); }
			.tb-mc-badge.dismissed { background: var(--gray-100, #f5f5f5); color: var(--gray-700, #666); }
			.tb-mc-muted { color: var(--text-muted); font-size: 12px; line-height: 1.5; }
			.tb-mc-stats {
				display: grid;
				grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
				gap: 10px;
				margin: 12px 0;
			}
			.tb-mc-stat {
				border: 1px solid var(--border-color);
				border-radius: 6px;
				padding: 10px 12px;
				background: var(--control-bg, #f8f9fa);
			}
			.tb-mc-stat-val { font-size: 18px; font-weight: 600; line-height: 1.2; }
			.tb-mc-stat-lbl { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
			.tb-mc-section-title {
				font-size: 11px;
				font-weight: 600;
				text-transform: uppercase;
				letter-spacing: .05em;
				color: var(--text-muted);
				margin: 14px 0 8px;
			}
			.tb-mc-toggles { display: flex; flex-direction: column; gap: 8px; }
			.tb-mc-toggle {
				display: flex;
				align-items: center;
				justify-content: space-between;
				gap: 12px;
				padding: 10px 12px;
				border: 1px solid var(--border-color);
				border-radius: 6px;
				background: var(--card-bg, #fff);
			}
			.tb-mc-toggle-label { font-weight: 500; }
			.tb-mc-toggle-help { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
			.tb-mc-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 4px; }
			.tb-mc-banner {
				padding: 12px 14px;
				border-radius: 6px;
				border: 1px solid var(--orange-200, #ffd699);
				background: var(--orange-50, #fff8f0);
				margin-bottom: 12px;
			}
		`;
		document.head.appendChild(s);
	}

	function stat_card(label, value) {
		const v = value == null || value === "" ? "—" : value;
		return `<div class="tb-mc-stat"><div class="tb-mc-stat-val">${frappe.utils.escape_html(String(v))}</div>` +
			`<div class="tb-mc-stat-lbl">${frappe.utils.escape_html(label)}</div></div>`;
	}

	function setup_adms_console(frm, $host) {
		const status = frm.doc.adms_status || "Pending";
		const registered = status === "Registered";

		let banner = "";
		if (status === "Pending") {
			banner = `
				<div class="tb-mc-banner">
					<strong>${__("Awaiting registration")}</strong>
					<p class="tb-mc-muted" style="margin:6px 0 10px;">
						${__(
							"This device was added from discovery but has not completed the ADMS handshake yet. Register to enable downloads and feature toggles."
						)}
					</p>
					<div class="tb-mc-actions">
						<button type="button" class="btn btn-primary btn-sm tb-mc-register">${__("Register")}</button>
						<button type="button" class="btn btn-default btn-sm tb-mc-dismiss">${__("Dismiss")}</button>
					</div>
				</div>`;
		} else if (status === "Dismissed") {
			banner = `<div class="tb-mc-banner"><strong>${__("Dismissed")}</strong>
				<p class="tb-mc-muted">${__("This machine was dismissed during onboarding.")}</p></div>`;
		}

		const $console = $(`
			<div class="tb-machine-console">
				<div class="tb-mc-card">
					<div class="tb-mc-head">
						<h4 class="tb-mc-title">${frappe.utils.escape_html(frm.doc.machine_name || frm.doc.name)}</h4>
						<span class="tb-mc-badge ${status.toLowerCase()}">${frappe.utils.escape_html(status)}</span>
					</div>
					<p class="tb-mc-muted tb-mc-contact-line"></p>
					${banner}
					<div class="tb-mc-stats tb-mc-stats-row">
						${stat_card(__("Users"), frm.doc.adms_user_count)}
						${stat_card(__("Transactions"), frm.doc.adms_attlog_count)}
						${stat_card(__("Faces"), frm.doc.adms_face_count)}
						${stat_card(__("Firmware"), frm.doc.adms_firmware || "—")}
					</div>
					${registered ? `
						<div class="tb-mc-section-title">${__("Auto-receive from device")}</div>
						<div class="tb-mc-toggles tb-mc-toggle-list"></div>
						<div class="tb-mc-section-title">${__("Download from device")}</div>
						<div class="tb-mc-actions">
							<button type="button" class="btn btn-default btn-sm tb-mc-dl-users">${__("Users")}</button>
							<button type="button" class="btn btn-default btn-sm tb-mc-dl-txn">${__("Transactions")}</button>
							<button type="button" class="btn btn-default btn-sm tb-mc-dl-faces">${__("Faces")}</button>
							<button type="button" class="btn btn-default btn-sm tb-mc-get-info">${__("Get info")}</button>
							<button type="button" class="btn btn-default btn-sm tb-mc-reboot">${__("Reboot")}</button>
						</div>
						<p class="tb-mc-muted" style="margin-top:8px;">
							${__(
								"Toggles apply on the next device handshake. Downloads queue commands for the next poll (~30s)."
							)}
						</p>
					` : ""}
				</div>
			</div>
		`);

		$host.append($console);

		frappe.call({
			method: "timebridge.timebridge.iclock.api.server_status",
			callback(r) {
				const port = (r.message || {}).web_port;
				const enabled = (r.message || {}).enabled;
				if (!enabled) {
					$console.find(".tb-mc-contact-line").html(
						`<span style="color:var(--orange-600)">${__(
							"ADMS Server is off — enable it in TimeBridge Settings."
						)}</span>`
					);
				} else if (frm.doc.last_contact_at) {
					$console.find(".tb-mc-contact-line").text(
						__("Last contact {0}", [frappe.datetime.str_to_user(frm.doc.last_contact_at)])
					);
				} else {
					$console.find(".tb-mc-contact-line").text(__("Device has not contacted the server yet."));
				}
			},
		});

		if (registered) {
			render_toggles(frm, $console);
		}

		$console.on("click", ".tb-mc-register", () => register_machine(frm));
		$console.on("click", ".tb-mc-dismiss", () => dismiss_machine(frm));
		$console.on("click", ".tb-mc-dl-users", () =>
			start_download_modal(frm, {
				title: __("Download users"),
				queue_method: "timebridge.timebridge.iclock.api.download_users",
				hint: __(
					"The device may include face photos with user data — they will be saved on each Machine User when possible."
				),
			})
		);
		$console.on("click", ".tb-mc-dl-txn", () => prompt_txn_download(frm));
		$console.on("click", ".tb-mc-dl-faces", () =>
			start_download_modal(frm, {
				title: __("Download faces"),
				queue_method: "timebridge.timebridge.iclock.api.download_faces",
				hint: __("Photos attach to existing Machine Users — download users first if needed."),
			})
		);
		$console.on("click", ".tb-mc-get-info", () => get_device_info(frm));
		$console.on("click", ".tb-mc-reboot", () => queue_reboot(frm));
	}

	function setup_pyzk_console(frm, $host) {
		const $console = $(`
			<div class="tb-machine-console">
				<div class="tb-mc-card">
					<div class="tb-mc-head">
						<h4 class="tb-mc-title">${__("Pull device")}</h4>
						<span class="tb-mc-badge registered">${frappe.utils.escape_html(frm.doc.status || "—")}</span>
					</div>
					<p class="tb-mc-muted">${__("This server dials the device on port {0}.", [frm.doc.port || 4370])}</p>
					<div class="tb-mc-actions" style="margin-top:12px;">
						<button type="button" class="btn btn-primary btn-sm tb-mc-pyzk-test">${__("Test connection")}</button>
						<button type="button" class="btn btn-default btn-sm tb-mc-pyzk-fetch">${__("Fetch all data")}</button>
						<button type="button" class="btn btn-default btn-sm tb-mc-pyzk-photos">${__("Fetch photos")}</button>
						<button type="button" class="btn btn-default btn-sm tb-mc-pyzk-collect">${__("Collect photos")}</button>
					</div>
				</div>
			</div>
		`);
		$host.append($console);
		$console.on("click", ".tb-mc-pyzk-test", () => {
			if (typeof start_connection_test === "function") start_connection_test(frm);
		});
		$console.on("click", ".tb-mc-pyzk-fetch", () => {
			if (typeof start_fetch_all === "function") start_fetch_all(frm);
		});
		$console.on("click", ".tb-mc-pyzk-photos", () => {
			if (typeof start_photo_fetch === "function") start_photo_fetch(frm);
		});
		$console.on("click", ".tb-mc-pyzk-collect", () => {
			if (typeof start_photo_collection === "function") start_photo_collection(frm);
		});
	}

	function feature_on(frm, feature) {
		return Object.keys(feature.fields).every((field) => cint(frm.doc[field]));
	}

	function render_toggles(frm, $console) {
		const $list = $console.find(".tb-mc-toggle-list");
		$list.empty();
		ADMS_FEATURES.forEach((feature) => {
			const on = feature_on(frm, feature);
			const $row = $(`
				<div class="tb-mc-toggle" data-feature="${feature.id}">
					<div>
						<div class="tb-mc-toggle-label">${frappe.utils.escape_html(feature.label)}</div>
						<div class="tb-mc-toggle-help">${frappe.utils.escape_html(feature.help)}</div>
					</div>
					<div class="form-check form-switch" style="margin:0;">
						<input class="form-check-input tb-mc-switch" type="checkbox" ${on ? "checked" : ""}>
					</div>
				</div>
			`);
			$row.find(".tb-mc-switch").on("change", function () {
				const enabled = $(this).prop("checked");
				const flags = {};
				Object.keys(feature.fields).forEach((field) => {
					flags[field] = enabled ? 1 : 0;
				});
				frappe.call({
					method: "timebridge.timebridge.iclock.api.set_receive_flags",
					args: {
						machine_id: frm.doc.name,
						receive_flags: JSON.stringify(flags),
					},
					callback() {
						Object.assign(frm.doc, flags);
						frappe.show_alert({
							message: enabled ? __("Enabled") : __("Disabled"),
							indicator: "green",
						});
					},
				});
			});
			$list.append($row);
		});
	}

	function register_machine(frm) {
		frappe.call({
			method: "timebridge.timebridge.iclock.api.register_machine",
			args: { name: frm.doc.name },
			callback() {
				frm.reload_doc();
			},
		});
	}

	function dismiss_machine(frm) {
		frappe.confirm(__("Dismiss this machine from onboarding?"), () => {
			frappe.call({
				method: "timebridge.timebridge.iclock.api.dismiss_machine",
				args: { name: frm.doc.name },
				callback() {
					frm.reload_doc();
				},
			});
		});
	}

	function prompt_txn_download(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Download transactions"),
			fields: [
				{
					fieldname: "days",
					fieldtype: "Select",
					label: __("How far back"),
					default: "30",
					options: [
						{ value: "7", label: __("Last 7 days") },
						{ value: "30", label: __("Last 30 days") },
						{ value: "90", label: __("Last 90 days") },
					],
				},
			],
			primary_action_label: __("Download"),
			primary_action(values) {
				d.hide();
				start_download_modal(frm, {
					title: __("Download transactions"),
					queue_method: "timebridge.timebridge.iclock.api.download_transactions",
					queue_args: { days: cint(values.days) },
					hint: __("The device will upload attendance records for the selected range."),
				});
			},
		});
		d.show();
	}

	function render_stats_table(stats) {
		const rows = Object.entries(stats || {});
		if (!rows.length) {
			return `<p class="text-muted">${__("No counts returned.")}</p>`;
		}
		const body = rows
			.map(
				([label, value]) =>
					`<tr><td style="width:45%;font-weight:600;">${frappe.utils.escape_html(label)}</td>` +
					`<td>${frappe.utils.escape_html(String(value))}</td></tr>`
			)
			.join("");
		return `<table class="table table-bordered table-condensed" style="font-size:13px;margin:0;"><tbody>${body}</tbody></table>`;
	}

	function open_wait_dialog({ title, hint, on_queue, on_poll, timeout_seconds }) {
		let poll_timer = null;
		let can_close = false;

		const d = new frappe.ui.Dialog({ title, size: "large" });
		d.$body.html(`
			${hint ? `<p class="tb-dl-hint text-muted" style="font-size:12px;margin-bottom:12px;">${frappe.utils.escape_html(hint)}</p>` : ""}
			<div class="tb-dl-status text-muted" style="font-size:13px;margin-bottom:12px;"></div>
			<div class="tb-dl-wait text-muted" style="font-size:12px;margin-bottom:12px;"></div>
			<div class="tb-dl-result hidden"></div>
		`);
		d.footer.empty();
		const $close = $(`<button type="button" class="btn btn-primary btn-sm">${__("Close")}</button>`)
			.prop("disabled", true)
			.appendTo(d.footer);
		$close.on("click", () => {
			if (!can_close) return;
			stop_poll();
			d.hide();
		});
		d.$wrapper.modal({ backdrop: "static", keyboard: false });
		d.$wrapper.find(".modal-header .btn-close, .modal-header .close").hide();
		d.show();

		const $status = d.$body.find(".tb-dl-status");
		const $wait = d.$body.find(".tb-dl-wait");
		const $result = d.$body.find(".tb-dl-result");

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

		function finish(message, stats, indicator) {
			stop_poll();
			can_close = true;
			$close.prop("disabled", false);
			set_status(message, indicator || "green");
			$wait.text("");
			if (stats && Object.keys(stats).length) {
				$result.removeClass("hidden").html(render_stats_table(stats));
			}
		}

		function stop_poll() {
			if (poll_timer) {
				clearInterval(poll_timer);
				poll_timer = null;
			}
		}

		function poll(session_id) {
			on_poll(session_id, { set_status, finish, $wait, timeout_seconds });
		}

		set_status(__("Queueing command…"));
		on_queue({
			set_status,
			finish,
			start_poll(session_id) {
				poll(session_id);
				poll_timer = setInterval(() => poll(session_id), POLL_MS);
			},
		});

		d.$wrapper.on("hide.bs.modal", function (e) {
			if (!can_close) {
				e.preventDefault();
				e.stopImmediatePropagation();
			} else {
				stop_poll();
			}
		});

		return { finish, set_status, stop_poll };
	}

	function start_download_modal(frm, { title, queue_method, queue_args, hint }) {
		open_wait_dialog({
			title,
			hint,
			timeout_seconds: DOWNLOAD_TIMEOUT_SECONDS,
			on_queue({ set_status, finish, start_poll }) {
				frappe.call({
					method: queue_method,
					args: Object.assign({ machine_id: frm.doc.name }, queue_args || {}),
					callback(r) {
						const res = r.message || {};
						if (res.status !== "queued" || !res.session_id) {
							finish(__("Could not queue download."), null, "red");
							return;
						}
						set_status(__("Download queued — waiting for device to poll…"));
						start_poll(res.session_id);
					},
					error() {
						finish(__("Could not reach the server."), null, "red");
					},
				});
			},
			on_poll(session_id, { set_status, finish, $wait, timeout_seconds }) {
				frappe.call({
					method: "timebridge.timebridge.iclock.api.download_progress",
					args: { machine_id: frm.doc.name, session_id },
					callback(r) {
						const st = r.message || {};
						if (st.phase === "done") {
							finish(st.message || __("Download complete."), st.stats, st.indicator || "green");
							frm.reload_doc();
							return;
						}
						if (st.phase === "timeout") {
							finish(st.message || __("Download timed out."), st.stats, "orange");
							if (st.stats && Object.keys(st.stats).length) {
								frm.reload_doc();
							}
							return;
						}
						if (st.phase === "error") {
							finish(st.message || __("Download failed."), null, "red");
							return;
						}
						set_status(st.message || __("Waiting for device…"));
						if (st.wait_seconds != null) {
							$wait.text(
								__("Elapsed: {0}s / {1}s", [st.wait_seconds, timeout_seconds])
							);
						}
					},
				});
			},
		});
	}

	function queue_reboot(frm) {
		frappe.call({
			method: "timebridge.timebridge.iclock.api.queue_device_command",
			args: { machine_id: frm.doc.name, command: "REBOOT" },
			callback() {
				frappe.show_alert({ message: __("Reboot queued"), indicator: "green" });
			},
		});
	}

	function get_device_info(frm) {
		open_wait_dialog({
			title: __("Get info"),
			hint: __(
				"The device checks in roughly every 30 seconds. It must poll before it can receive the command."
			),
			timeout_seconds: INFO_TIMEOUT_SECONDS,
			on_queue({ set_status, finish, start_poll }) {
				frappe.call({
					method: "timebridge.timebridge.iclock.api.request_device_info",
					args: { machine_id: frm.doc.name },
					callback(r) {
						const res = r.message || {};
						if (res.status !== "queued" || !res.command_id) {
							finish(__("Could not queue INFO."), null, "orange");
							return;
						}
						set_status(__("INFO queued — waiting for device to poll…"));
						start_poll(res.command_id);
					},
					error() {
						finish(__("Could not reach the server."), null, "red");
					},
				});
			},
			on_poll(command_id, { set_status, finish, $wait, timeout_seconds }) {
				frappe.call({
					method: "timebridge.timebridge.iclock.api.device_info_progress",
					args: { machine_id: frm.doc.name, command_id },
					callback(r) {
						const st = r.message || {};
						if (st.phase === "done") {
							finish(
								st.message || __("Info received."),
								st.info,
								"green"
							);
							frm.reload_doc();
							return;
						}
						if (st.phase === "timeout" || st.phase === "error") {
							finish(st.message || __("Could not get info."), null, "orange");
							return;
						}
						set_status(st.message || __("Waiting…"));
						if (st.wait_seconds != null) {
							$wait.text(
								__("Elapsed: {0}s / {1}s", [st.wait_seconds, timeout_seconds])
							);
						}
					},
				});
			},
		});
	}
})();
