// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.provide("timebridge.daily_punch_summary");

const DPS_API = "timebridge.timebridge.services.dashboard.get_daily_punch_summary_list";

const DPS_COLUMNS = (show_machine) => {
	const cols = [];
	if (show_machine) {
		cols.push({ key: "machine", label: __("Machine"), sortable: true });
	}
	cols.push(
		{ key: "user_name", label: __("User Name"), sortable: true },
		{ key: "punched_in_display", label: __("Punched In"), sortable: true, sort_key: "punched_in" },
		{ key: "punched_out_display", label: __("Punched Out"), sortable: true, sort_key: "punched_out" },
		{ key: "punches", label: __("Punches"), sortable: true, align: "right" }
	);
	return cols;
};

timebridge.daily_punch_summary.show = function (options = {}) {
	inject_styles();
	$(".tb-dps-backdrop").remove();

	const state = {
		date: options.date || frappe.datetime.get_today(),
		machine: options.machine || "",
		rows: [],
		sort_field: "punched_in",
		sort_order: "desc",
		search: "",
	};

	const $backdrop = $('<div class="tb-dps-backdrop"></div>').appendTo("body");
	const $panel = $('<div class="tb-dps-panel"></div>').appendTo($backdrop);
	const ui = build_panel($panel, state, { modal: true });

	function close() {
		$backdrop.remove();
		$(document).off("keydown.tb-dps");
	}
	$backdrop.on("click", (e) => {
		if (e.target === $backdrop[0]) close();
	});
	$(document).on("keydown.tb-dps", (e) => {
		if (e.key === "Escape") close();
	});
	ui.$close.on("click", close);

	wire_panel(ui, state);
	load_rows(state, ui);
};

timebridge.daily_punch_summary.render_inline = function ($parent, options = {}) {
	inject_styles();
	const state = {
		date: options.date || frappe.datetime.get_today(),
		machine: options.machine || "",
		rows: [],
		sort_field: "punched_in",
		sort_order: "desc",
		search: "",
	};
	const $shell = $('<div class="tb-dps-inline"></div>').appendTo($parent);
	const ui = build_panel($shell, state, { modal: false });
	wire_panel(ui, state);
	load_rows(state, ui);
	return { state, ui, reload: () => load_rows(state, ui) };
};

function build_panel($root, state, { modal }) {
	const subtitle = format_subtitle(state.date, state.machine);
	$root.append(`
		<div class="tb-dps-header">
			<div>
				<div class="tb-dps-title">${__("Daily Punch Summary")}</div>
				<div class="tb-dps-subtitle">${subtitle}</div>
			</div>
			${modal ? '<button type="button" class="tb-dps-close" title="Close">&times;</button>' : ""}
		</div>
		<div class="tb-dps-toolbar">
			<div class="tb-dps-field tb-dps-field-machine">
				<label class="tb-dps-field-label">${__("Machine")}</label>
				<div class="tb-dps-link-wrap tb-dps-machine"></div>
			</div>
			<div class="tb-dps-field tb-dps-field-date">
				<label class="tb-dps-field-label">${__("Date")}</label>
				<div class="tb-dps-control-wrap tb-dps-date"></div>
			</div>
			<div class="tb-dps-field tb-dps-field-search">
				<label class="tb-dps-field-label">${__("Search")}</label>
				<div class="tb-dps-search-inner">
					<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
						<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
					</svg>
					<input type="text" class="tb-dps-search-input" placeholder="${__("Search...")}">
				</div>
			</div>
		</div>
		<div class="tb-dps-body">
			<div class="tb-dps-loading">${__("Loading")}...</div>
		</div>
		<div class="tb-dps-footer">
			<span class="tb-dps-count"></span>
			<button type="button" class="tb-dps-btn-export">&#11015; ${__("Export CSV")}</button>
		</div>
	`);

	const machine_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			fieldname: "machine",
			label: __("Machine"),
			options: "TimeBridge Machine",
			placeholder: __("All machines"),
			only_select: 1,
			change: () => {
				state.machine = machine_control.get_value() || "";
				update_subtitle($root, state);
				load_rows(state, ui);
			},
		},
		parent: $root.find(".tb-dps-machine"),
		render_input: true,
	});
	if (state.machine) {
		machine_control.set_value(state.machine);
	}
	normalize_frappe_control($root.find(".tb-dps-machine"));

	const date_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Date",
			fieldname: "date",
			label: __("Date"),
			default: state.date,
			change: () => {
				state.date = date_control.get_value();
				update_subtitle($root, state);
				load_rows(state, ui);
			},
		},
		parent: $root.find(".tb-dps-date"),
		render_input: true,
	});
	date_control.set_value(state.date);
	normalize_frappe_control($root.find(".tb-dps-date"));

	const ui = {
		$root,
		$body: $root.find(".tb-dps-body"),
		$count: $root.find(".tb-dps-count"),
		$search: $root.find(".tb-dps-search-input"),
		$export: $root.find(".tb-dps-btn-export"),
		$close: $root.find(".tb-dps-close"),
		date_control,
		machine_control,
	};
	return ui;
}

function normalize_frappe_control($wrap) {
	$wrap.find(".control-label, .help-box").hide();
	$wrap.find(".form-group").css({ margin: 0 });
	$wrap.find(".control-input").css({ minHeight: "32px" });
	$wrap.find("input").css({ height: "32px", borderRadius: "6px" });
}

function wire_panel(ui, state) {
	ui.$search.on("input", (e) => {
		state.search = (e.target.value || "").trim().toLowerCase();
		render_table(state, ui);
	});
	ui.$export.on("click", () => export_csv(state, ui));
}

function update_subtitle($root, state) {
	$root.find(".tb-dps-subtitle").text(format_subtitle(state.date, state.machine));
}

function format_subtitle(date, machine) {
	const formatted = frappe.datetime.str_to_user(date);
	return machine ? `${formatted} · ${machine}` : formatted;
}

function load_rows(state, ui) {
	ui.$body.html(`<div class="tb-dps-loading">${__("Loading")}...</div>`);
	frappe
		.xcall(DPS_API, {
			date: state.date,
			machine: state.machine || null,
		})
		.then((rows) => {
			state.rows = (rows || []).map((row) => ({
				...row,
				punched_in_display: row.punched_in_display || "",
				punched_out_display: row.punched_out_display || "",
			}));
			render_table(state, ui);
		})
		.catch(() => {
			ui.$body.html(`<div class="tb-dps-empty">${__("Could not load punch data.")}</div>`);
			ui.$count.text(__("0 users"));
		});
}

function render_table(state, ui) {
	const show_machine = !state.machine;
	const columns = DPS_COLUMNS(show_machine);
	const filtered = filter_rows(state.rows, columns, state.search);
	const sorted = sort_rows(filtered, state);

	if (!sorted.length) {
		ui.$body.html(`<div class="tb-dps-empty">${__("No punches recorded for this date.")}</div>`);
		ui.$count.text(__("0 users"));
		return;
	}

	const header = columns
		.map((col) => {
			const active = state.sort_field === (col.sort_key || col.key);
			const arrow = active ? (state.sort_order === "asc" ? " ↑" : " ↓") : "";
			const cls = [col.align === "right" ? "r" : "", "tb-dps-sortable"].filter(Boolean).join(" ");
			return `<th class="${cls}" data-sort="${frappe.utils.escape_html(col.sort_key || col.key)}">${col.label}${arrow}</th>`;
		})
		.join("");

	const body = sorted
		.map((row) => {
			const tds = columns
				.map((col) => {
					const val = row[col.key] ?? "";
					const cls = col.align === "right" ? "r" : col.key === "machine" ? "muted" : "";
					return `<td class="${cls}">${frappe.utils.escape_html(String(val))}</td>`;
				})
				.join("");
			return `<tr>${tds}</tr>`;
		})
		.join("");

	ui.$body.html(`
		<table class="tb-dps-table">
			<thead><tr>${header}</tr></thead>
			<tbody>${body}</tbody>
		</table>
	`);

	ui.$body.find(".tb-dps-sortable").on("click", (e) => {
		const field = $(e.currentTarget).data("sort");
		if (state.sort_field === field) {
			state.sort_order = state.sort_order === "asc" ? "desc" : "asc";
		} else {
			state.sort_field = field;
			state.sort_order = field === "user_name" || field === "machine" ? "asc" : "desc";
		}
		render_table(state, ui);
	});

	const label = sorted.length === 1 ? __("1 user") : __("{0} users", [sorted.length]);
	ui.$count.text(label);
}

function filter_rows(rows, columns, query) {
	if (!query) return rows;
	return rows.filter((row) =>
		columns.some((col) =>
			String(row[col.key] ?? "")
				.toLowerCase()
				.includes(query)
		)
	);
}

function sort_rows(rows, state) {
	const { sort_field, sort_order } = state;
	const dir = sort_order === "asc" ? 1 : -1;
	return [...rows].sort((a, b) => {
		let left = a[sort_field];
		let right = b[sort_field];
		if (sort_field === "punches") {
			return ((left || 0) - (right || 0)) * dir;
		}
		if (!left && !right) return 0;
		if (!left) return 1;
		if (!right) return -1;
		if (left instanceof Date || String(left).includes("T")) {
			left = new Date(left).getTime();
			right = new Date(right).getTime();
		}
		return (left > right ? 1 : left < right ? -1 : 0) * dir;
	});
}

function export_csv(state, ui) {
	const show_machine = !state.machine;
	const columns = DPS_COLUMNS(show_machine);
	const filtered = sort_rows(filter_rows(state.rows, columns, state.search), state);
	if (!filtered.length) {
		frappe.show_alert({ message: __("No rows to export"), indicator: "orange" });
		return;
	}
	const header = columns.map((col) => csv_cell(col.label)).join(",");
	const body = filtered
		.map((row) => columns.map((col) => csv_cell(row[col.key])).join(","))
		.join("\n");
	const blob = new Blob([header + "\n" + body], { type: "text/csv;charset=utf-8;" });
	const link = Object.assign(document.createElement("a"), {
		href: URL.createObjectURL(blob),
		download: `daily-punch-summary-${state.date}.csv`,
	});
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
	URL.revokeObjectURL(link.href);
}

function csv_cell(value) {
	return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

function inject_styles() {
	if (document.getElementById("tb-dps-styles-v2")) return;
	const style = document.createElement("style");
	style.id = "tb-dps-styles-v2";
	style.textContent = `
		.tb-dps-backdrop {
			position: fixed; inset: 0; background: rgba(0,0,0,.45);
			z-index: 9000; display: flex; align-items: center; justify-content: center;
		}
		.tb-dps-panel, .tb-dps-inline .tb-dps-panel-shell {
			background: var(--card-bg); border-radius: 10px;
			box-shadow: 0 8px 40px rgba(0,0,0,.22);
			width: 96vw; max-width: 960px; max-height: 82vh;
			display: flex; flex-direction: column;
		}
		.tb-dps-inline { max-width: 960px; margin: 0 auto; padding: 0 8px 24px; overflow: visible; }
		.tb-dps-inline > .tb-dps-header,
		.tb-dps-inline > .tb-dps-toolbar,
		.tb-dps-inline > .tb-dps-body,
		.tb-dps-inline > .tb-dps-footer {
			background: var(--card-bg);
			border-left: 1px solid var(--border-color);
			border-right: 1px solid var(--border-color);
		}
		.tb-dps-inline > .tb-dps-header {
			border-top: 1px solid var(--border-color);
			border-radius: 10px 10px 0 0;
		}
		.tb-dps-inline > .tb-dps-footer {
			border-bottom: 1px solid var(--border-color);
			border-radius: 0 0 10px 10px;
		}
		.tb-dps-header {
			display: flex; align-items: center; justify-content: space-between;
			padding: 16px 20px; border-bottom: 1px solid var(--border-color); flex-shrink: 0;
		}
		.tb-dps-title { font-size: 15px; font-weight: 700; color: var(--text-color); }
		.tb-dps-subtitle { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
		.tb-dps-close {
			width: 28px; height: 28px; border-radius: 50%;
			border: 1px solid var(--border-color); background: var(--subtle-fg);
			cursor: pointer; font-size: 16px; line-height: 1; color: var(--text-muted);
		}
		.tb-dps-close:hover { background: var(--border-color); color: var(--text-color); }
		.tb-dps-toolbar {
			padding: 12px 20px; border-bottom: 1px solid var(--border-color);
			display: flex; align-items: flex-end; gap: 12px; flex-shrink: 0; flex-wrap: wrap;
			overflow: visible; position: relative; z-index: 20;
		}
		.tb-dps-field { flex: 0 0 auto; }
		.tb-dps-field-machine { width: 220px; }
		.tb-dps-field-date { width: 160px; }
		.tb-dps-field-search { flex: 1 1 220px; min-width: 220px; }
		.tb-dps-field-label {
			display: block; font-size: 10px; font-weight: 700; text-transform: uppercase;
			letter-spacing: .3px; color: var(--text-muted); margin-bottom: 4px; line-height: 1;
			min-height: 10px;
		}
		.tb-dps-link-wrap, .tb-dps-control-wrap {
			overflow: visible; position: relative;
		}
		.tb-dps-link-wrap .awesomplete { z-index: 30; width: 100%; }
		.tb-dps-link-wrap .awesomplete > ul {
			z-index: 40; max-height: 240px; overflow-y: auto;
		}
		.tb-dps-search-inner {
			display: flex; align-items: center; gap: 8px;
			border: 1px solid var(--border-color); border-radius: 6px;
			padding: 0 12px; height: 32px; background: var(--card-bg);
			box-sizing: border-box;
		}
		.tb-dps-search-inner input {
			border: 0; outline: none; width: 100%; background: transparent; font-size: 13px;
			height: 30px; line-height: 30px; padding: 0;
		}
		.tb-dps-date .form-group, .tb-dps-machine .form-group { margin: 0; }
		.tb-dps-date input, .tb-dps-machine input {
			height: 32px !important; min-height: 32px !important;
			border-radius: 6px !important; box-sizing: border-box;
		}
		.tb-dps-body { flex: 1; overflow: auto; padding: 0; min-height: 200px; position: relative; z-index: 1; }
		.tb-dps-footer {
			padding: 12px 20px; border-top: 1px solid var(--border-color);
			display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
		}
		.tb-dps-count { font-size: 12px; color: var(--text-muted); }
		.tb-dps-btn-export {
			height: 30px; padding: 0 16px; font-size: 12px; font-weight: 600;
			border: 1px solid var(--border-color); border-radius: 6px;
			background: var(--card-bg); color: var(--text-color); cursor: pointer;
		}
		.tb-dps-btn-export:hover { background: var(--subtle-fg); }
		.tb-dps-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.tb-dps-table thead th {
			padding: 10px 14px; font-size: 11px; font-weight: 700; color: var(--text-muted);
			border-bottom: 1px solid var(--border-color); text-align: left;
			background: var(--subtle-fg); position: sticky; top: 0; z-index: 1;
			text-transform: uppercase; letter-spacing: .3px; white-space: nowrap;
		}
		.tb-dps-table thead th.r { text-align: right; }
		.tb-dps-table thead th.tb-dps-sortable { cursor: pointer; user-select: none; }
		.tb-dps-table td {
			padding: 10px 14px; border-bottom: 1px solid var(--border-color);
			text-align: left; vertical-align: middle;
		}
		.tb-dps-table td.r { text-align: right; font-weight: 600; }
		.tb-dps-table td.muted { color: var(--text-muted); font-size: 12px; }
		.tb-dps-table tbody tr:last-child td { border-bottom: none; }
		.tb-dps-table tbody tr:hover td { background: var(--highlight-color); }
		.tb-dps-empty, .tb-dps-loading {
			text-align: center; padding: 40px; color: var(--text-muted); font-size: 13px;
		}
	`;
	document.head.appendChild(style);
}
