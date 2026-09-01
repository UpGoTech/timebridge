// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.listview_settings["TimeBridge Machine User"] = {

	onload(listview) {
		// Menu items (standard=false) sit above the divider — first added stays on top.
		listview.page.add_menu_item(
			__("Create Employee"),
			() => open_employee_create_dialog(listview)
		);
		listview.page.add_menu_item(
			__("Shift Update"),
			() => open_employee_update_dialog(listview)
		);
		listview.page.add_menu_item(
			__("Rebuild"),
			() => open_rebuild_attendance_dialog()
		);
	},

};


function open_rebuild_attendance_dialog() {

	const dialog = new frappe.ui.Dialog({
		title: __("Rebuild Attendance"),
		fields: [
			{
				fieldname: "info",
				fieldtype: "HTML",
				options:
					`<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">` +
					__(
						"Recalculates in/out times and hours from stored punches. Existing rows are updated, never duplicated — safe to run again."
					) +
					`</div>`,
			},
			{
				fieldname: "from_date",
				fieldtype: "Date",
				label: __("From Date"),
				description: __("Leave both dates empty to rebuild everything."),
			},
			{
				fieldname: "to_date",
				fieldtype: "Date",
				label: __("To Date"),
			},
		],
		primary_action_label: __("Rebuild"),
		primary_action(values) {
			dialog.get_primary_btn().prop("disabled", true).text(__("Working…"));

			frappe.call({
				method: "timebridge.timebridge.api.rebuild_attendance",
				args: {
					from_date: values.from_date || null,
					to_date: values.to_date || null,
				},
				callback(r) {
					const res = r.message || {};
					dialog.hide();
					frappe.msgprint({
						title: __("Attendance Rebuilt"),
						indicator: "green",
						message:
							`<div>${__("Days processed")}: <b>${res.days || 0}</b></div>` +
							`<div>${__("New rows")}: <b>${res.created || 0}</b></div>` +
							`<div>${__("Updated rows")}: <b>${res.updated || 0}</b></div>` +
							`<div>${__("Punches read")}: <b>${res.punches_considered || 0}</b></div>` +
							`<div style="margin-top:6px;color:var(--text-muted);">` +
							__("Repeat punches within {0}s were counted once.", [
								res.duplicate_window || 0,
							]) +
							`</div>`,
					});
				},
				error() {
					dialog.get_primary_btn().prop("disabled", false).text(__("Rebuild"));
				},
			});
		},
	});

	dialog.show();
}


function list_default_machine(listview) {
	const machine_filter = (listview.filter_area?.get?.() || [])
		.find((f) => f[1] === "machine" && f[2] === "=");
	return machine_filter ? machine_filter[3] : null;
}


function open_employee_create_dialog(listview) {

	const prechecked = new Set(
		(listview.get_checked_items() || [])
			.filter((row) => !row.employee)
			.map((row) => row.name)
	);

	const dialog = new frappe.ui.Dialog({
		title: __("Create TimeBridge Employees"),
		size: "large",
		fields: [
			{
				fieldname: "intro",
				fieldtype: "HTML",
				options:
					`<div style="font-size:12px;color:var(--text-muted);margin:0 0 2px;">` +
					__("Pick users to create as TimeBridge Employees. Linked users are hidden.") +
					`</div>`,
			},
			{ fieldname: "counts", fieldtype: "HTML" },
			{ fieldname: "cb_machine", fieldtype: "Column Break" },
			{
				fieldname: "machine",
				fieldtype: "Link",
				label: __("TimeBridge Machine"),
				options: "TimeBridge Machine",
				default: list_default_machine(listview) || undefined,
			},
			{ fieldname: "sb_picker", fieldtype: "Section Break" },
			{ fieldname: "picker", fieldtype: "HTML" },
			{ fieldname: "sb_defaults", fieldtype: "Section Break", label: __("New Employee defaults") },
			{
				fieldname: "date_of_joining",
				fieldtype: "Date",
				label: __("Date of Joining"),
				reqd: 1,
				default: frappe.datetime.get_today(),
			},
			{
				fieldname: "organization",
				fieldtype: "Link",
				label: __("TimeBridge Organization"),
				options: "TimeBridge Organization",
				reqd: 1,
			},
			{ fieldname: "cb_org", fieldtype: "Column Break" },
			{
				fieldname: "branch",
				fieldtype: "Link",
				label: __("TimeBridge Branch"),
				options: "TimeBridge Branch",
				reqd: 1,
			},
			{
				fieldname: "shift",
				fieldtype: "Link",
				label: __("TimeBridge Shift"),
				options: "TimeBridge Shift",
			},
			{ fieldname: "sb_options", fieldtype: "Section Break", hide_border: 1 },
			{
				fieldname: "merge_same_name",
				fieldtype: "Check",
				label: __("Treat identical names as one person"),
				default: 1,
			},
			{ fieldname: "cb_opts", fieldtype: "Column Break" },
			{
				fieldname: "skip_non_person",
				fieldtype: "Check",
				label: __("Skip accounts that are not people"),
				default: 1,
			},
		],
		primary_action_label: __("Create & Link"),
		primary_action(values) {
			const selected = selected_machine_users(dialog);
			if (!selected.length) {
				frappe.msgprint({
					title: __("Nothing Selected"),
					indicator: "orange",
					message: __("Check at least one Machine User."),
				});
				return;
			}

			dialog.get_primary_btn().prop("disabled", true).text(__("Working…"));

			frappe.call({
				method: "timebridge.timebridge.api.create_and_link_selected_employees",
				args: {
					machine_users: selected,
					date_of_joining: values.date_of_joining,
					organization: values.organization,
					branch: values.branch,
					shift: values.shift || null,
					merge_same_name: values.merge_same_name ? 1 : 0,
					skip_non_person: values.skip_non_person ? 1 : 0,
				},
				callback(r) {
					const res = r.message || {};
					dialog.hide();
					const failures = res.failures || [];
					frappe.msgprint({
						title: __("TimeBridge Employees Linked"),
						indicator: failures.length ? "orange" : "green",
						message:
							`<div>${__("TimeBridge Employees created")}: <b>${res.created || 0}</b></div>` +
							`<div>${__("TimeBridge Machine Users linked")}: <b>${res.linked || 0}</b></div>` +
							`<div>${__("Existing punches attached")}: <b>${res.punches_linked || 0}</b></div>` +
							(failures.length
								? `<div class="alert alert-warning" style="margin-top:8px;padding:8px;">` +
								  __("{0} could not be saved:", [failures.length]) +
								  " " +
								  frappe.utils.escape_html(failures.map((f) => f.user_name).join(", ")) +
								  `</div>`
								: "") +
							`<div style="margin-top:8px;">` +
							__("Run Rebuild Attendance on the machine to turn punches into attendance.") +
							`</div>`,
					});
					listview.refresh();
				},
				error() {
					dialog.get_primary_btn().prop("disabled", false).text(__("Create & Link"));
				},
			});
		},
		secondary_action_label: __("Update defaults"),
		secondary_action() {
			dialog.hide();
			open_employee_update_dialog(listview);
		},
	});

	dialog._prechecked = prechecked;
	dialog._candidates = [];
	dialog._picker_mode = "create";

	dialog.fields_dict.machine.df.onchange = () => reload_candidates(dialog);
	dialog.show();
	reload_candidates(dialog);
}


function open_employee_update_dialog(listview) {

	const prechecked = new Set(
		(listview.get_checked_items() || [])
			.filter((row) => row.employee)
			.map((row) => row.name)
	);

	const dialog = new frappe.ui.Dialog({
		title: __("Update Employee defaults"),
		size: "large",
		fields: [
			{
				fieldname: "intro",
				fieldtype: "HTML",
				options:
					`<div style="font-size:12px;color:var(--text-muted);margin:0 0 2px;">` +
					__("Correct Date of Joining / Organization / Branch / Shift on already linked TimeBridge Employees. Empty fields are left unchanged.") +
					`</div>`,
			},
			{ fieldname: "counts", fieldtype: "HTML" },
			{ fieldname: "cb_machine", fieldtype: "Column Break" },
			{
				fieldname: "machine",
				fieldtype: "Link",
				label: __("TimeBridge Machine"),
				options: "TimeBridge Machine",
				default: list_default_machine(listview) || undefined,
			},
			{ fieldname: "sb_picker", fieldtype: "Section Break" },
			{ fieldname: "picker", fieldtype: "HTML" },
			{ fieldname: "sb_defaults", fieldtype: "Section Break", label: __("New values") },
			{
				fieldname: "date_of_joining",
				fieldtype: "Date",
				label: __("Date of Joining"),
			},
			{
				fieldname: "organization",
				fieldtype: "Link",
				label: __("TimeBridge Organization"),
				options: "TimeBridge Organization",
			},
			{ fieldname: "cb_org", fieldtype: "Column Break" },
			{
				fieldname: "branch",
				fieldtype: "Link",
				label: __("TimeBridge Branch"),
				options: "TimeBridge Branch",
			},
			{
				fieldname: "shift",
				fieldtype: "Link",
				label: __("TimeBridge Shift"),
				options: "TimeBridge Shift",
				description: __("Changing shift may need Rebuild Attendance afterwards."),
			},
		],
		primary_action_label: __("Update"),
		primary_action(values) {
			if (
				!values.date_of_joining &&
				!values.organization &&
				!values.branch &&
				!values.shift
			) {
				frappe.msgprint({
					title: __("Nothing Chosen"),
					indicator: "orange",
					message: __(
						"Pick at least one of Date of Joining, Organization, Branch or Shift."
					),
				});
				return;
			}

			const selected = selected_machine_users(dialog);
			if (!selected.length) {
				frappe.msgprint({
					title: __("Nothing Selected"),
					indicator: "orange",
					message: __("Check at least one linked Machine User."),
				});
				return;
			}

			dialog.get_primary_btn().prop("disabled", true).text(__("Working…"));

			frappe.call({
				method: "timebridge.timebridge.api.update_selected_employee_defaults",
				args: {
					machine_users: selected,
					date_of_joining: values.date_of_joining || null,
					organization: values.organization || null,
					branch: values.branch || null,
					shift: values.shift || null,
				},
				callback(r) {
					const res = r.message || {};
					dialog.hide();
					frappe.msgprint({
						title: __("TimeBridge Employees Updated"),
						indicator: "green",
						message:
							`<div>${__("TimeBridge Employees in selection")}: <b>${res.employees || 0}</b></div>` +
							`<div>${__("Changed")}: <b>${res.changed || 0}</b></div>` +
							(res.changed === 0
								? `<div style="margin-top:6px;color:var(--text-muted);">` +
								  __("They already held those values.") +
								  `</div>`
								: "") +
							(res.needs_rebuild
								? `<div class="alert alert-warning" style="margin-top:8px;padding:8px;">` +
								  __(
										"TimeBridge Shift changed. Run Rebuild Attendance — late and half-day were worked out from the old shift."
								  ) +
								  `</div>`
								: ""),
					});
					listview.refresh();
				},
				error() {
					dialog.get_primary_btn().prop("disabled", false).text(__("Update"));
				},
			});
		},
	});

	dialog._prechecked = prechecked;
	dialog._candidates = [];
	dialog._picker_mode = "update";

	dialog.fields_dict.machine.df.onchange = () => reload_candidates(dialog);
	dialog.show();
	reload_candidates(dialog);
}


function selected_machine_users(dialog) {
	const root = dialog.fields_dict.picker.$wrapper;
	return root
		.find("input.tb-mu-pick:checked")
		.map((_, el) => el.value)
		.get();
}


function reload_candidates(dialog) {
	const machine = dialog.get_value("machine") || null;
	const picker = dialog.fields_dict.picker.$wrapper;
	const counts = dialog.fields_dict.counts.$wrapper;
	const mode = dialog._picker_mode || "create";

	picker.html(
		`<div style="padding:16px;color:var(--text-muted);">${__("Loading…")}</div>`
	);

	frappe.call({
		method: "timebridge.timebridge.api.list_machine_users_for_employee_create",
		args: { machine },
		callback(r) {
			const data = r.message || {};
			const rows =
				mode === "update"
					? data.linked_candidates || []
					: data.candidates || [];
			dialog._candidates = rows;

			if (mode === "create") {
				const defaults = data.defaults || {};
				if (defaults.organization && !dialog.get_value("organization")) {
					dialog.set_value("organization", defaults.organization);
				}
				if (defaults.branch && !dialog.get_value("branch")) {
					dialog.set_value("branch", defaults.branch);
				}
				if (defaults.shift && !dialog.get_value("shift")) {
					dialog.set_value("shift", defaults.shift);
				}
			}

			counts.html(render_counts(data, mode));
			picker.html(
				render_picker(rows, dialog._prechecked, mode)
			);
			wire_picker(dialog);
		},
	});
}


function render_counts(data, mode) {
	const total = data.total || 0;
	const linked = data.linked || 0;
	const unlinked = data.unlinked || 0;

	if (mode === "update") {
		return (
			`<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:stretch;margin:0;">` +
			count_chip(__("On list"), total, "var(--text-muted)") +
			count_chip(__("Linked (editable)"), linked, "var(--blue-600, #2563eb)") +
			`</div>`
		);
	}

	return (
		`<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:stretch;margin:0;">` +
		count_chip(__("On list"), total, "var(--text-muted)") +
		count_chip(__("Already linked"), linked, "var(--green-600, #16a34a)") +
		count_chip(__("Ready to create"), unlinked, "var(--blue-600, #2563eb)") +
		`</div>`
	);
}


function count_chip(label, value, color) {
	return (
		`<div style="flex:1;min-width:72px;padding:6px 10px;border:1px solid var(--border-color);border-radius:6px;background:var(--fg-color);">` +
		`<div style="font-size:10px;color:var(--text-muted);text-transform:uppercase;letter-spacing:.02em;">${frappe.utils.escape_html(label)}</div>` +
		`<div style="font-size:18px;font-weight:600;line-height:1.2;color:${color};">${value}</div>` +
		`</div>`
	);
}


function render_picker(candidates, prechecked, mode) {
	const empty_msg =
		mode === "update"
			? __("No linked Machine Users here. Create & Link first, or clear the machine filter.")
			: __(
					"No unlinked Machine Users here. Fetch users from the device, or clear the machine filter."
			  );

	if (!candidates.length) {
		return (
			`<div style="padding:12px;text-align:center;color:var(--text-muted);border:1px dashed var(--border-color);border-radius:6px;">` +
			empty_msg +
			`</div>`
		);
	}

	const rows = candidates
		.map((c) => {
			const checked = prechecked.has(c.name) ? "checked" : "";
			const uid = frappe.utils.escape_html(c.user_id || "");
			const uname = frappe.utils.escape_html(c.user_name || "");
			return (
				`<tr class="tb-mu-row" data-user-id="${uid.toLowerCase()}" data-user-name="${uname.toLowerCase()}">` +
				`<td style="width:36px;"><input type="checkbox" class="tb-mu-pick" value="${frappe.utils.escape_html(c.name)}" ${checked}></td>` +
				`<td>${uid}</td>` +
				`<td>${uname}</td>` +
				`<td>${frappe.utils.escape_html(c.machine_name || c.machine || "")}</td>` +
				`</tr>`
			);
		})
		.join("");

	const input_style =
		"height:24px;padding:2px 8px;font-size:12px;border:1px solid var(--border-color);" +
		"border-radius:4px;background:var(--control-bg,var(--fg-color));min-width:0;";

	return (
		`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:4px;">` +
		`<div style="font-size:12px;color:var(--text-muted);white-space:nowrap;">` +
		`<span class="tb-mu-selected-count">0</span> ` +
		__("selected") +
		`</div>` +
		`<div style="display:flex;gap:6px;flex:1;min-width:180px;justify-content:flex-end;align-items:center;">` +
		`<input type="text" class="tb-mu-filter-id form-control input-xs" ` +
		`placeholder="${__("ID")}" style="${input_style};width:72px;" autocomplete="off">` +
		`<input type="text" class="tb-mu-filter-name form-control input-xs" ` +
		`placeholder="${__("Name")}" style="${input_style};width:120px;" autocomplete="off">` +
		`<button type="button" class="btn btn-xs btn-default tb-mu-select-all">${__("Select all")}</button>` +
		`<button type="button" class="btn btn-xs btn-default tb-mu-select-none">${__("Clear")}</button>` +
		`</div>` +
		`</div>` +
		`<div style="max-height:160px;overflow:auto;border:1px solid var(--border-color);border-radius:6px;">` +
		`<table class="table table-sm" style="margin:0;">` +
		`<thead style="position:sticky;top:0;background:var(--fg-color);z-index:1;">` +
		`<tr>` +
		`<th></th>` +
		`<th>${__("User ID")}</th>` +
		`<th>${__("Name")}</th>` +
		`<th>${__("Machine")}</th>` +
		`</tr>` +
		`</thead>` +
		`<tbody>${rows}</tbody>` +
		`</table>` +
		`</div>`
	);
}


function wire_picker(dialog) {
	const root = dialog.fields_dict.picker.$wrapper;

	const refresh_count = () => {
		const n = root.find("input.tb-mu-pick:checked").length;
		root.find(".tb-mu-selected-count").text(n);
	};

	const apply_filter = () => {
		const id_q = (root.find(".tb-mu-filter-id").val() || "").trim().toLowerCase();
		const name_q = (root.find(".tb-mu-filter-name").val() || "").trim().toLowerCase();

		root.find("tr.tb-mu-row").each((_, el) => {
			const $row = $(el);
			const id_ok = !id_q || ($row.attr("data-user-id") || "").includes(id_q);
			const name_ok = !name_q || ($row.attr("data-user-name") || "").includes(name_q);
			$row.toggle(id_ok && name_ok);
		});
	};

	root.find(".tb-mu-filter-id, .tb-mu-filter-name").on("input", apply_filter);

	root.find(".tb-mu-select-all").on("click", () => {
		root.find("tr.tb-mu-row:visible input.tb-mu-pick").prop("checked", true);
		refresh_count();
	});

	root.find(".tb-mu-select-none").on("click", () => {
		root.find("tr.tb-mu-row:visible input.tb-mu-pick").prop("checked", false);
		refresh_count();
	});

	root.find("input.tb-mu-pick").on("change", refresh_count);
	refresh_count();
}
