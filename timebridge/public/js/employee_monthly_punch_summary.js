// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.provide("timebridge.employee_monthly_punch_summary");

const EMPS_API =
	"timebridge.timebridge.services.dashboard.get_employee_monthly_punch_summary_list";

const EMPS_COLUMNS = () => [
	{ key: "date_display", label: __("Date"), sortable: true, sort_key: "date" },
	{ key: "punched_in_display", label: __("Punched In"), sortable: true, sort_key: "punched_in" },
	{ key: "punched_out_display", label: __("Punched Out"), sortable: true, sort_key: "punched_out" },
	{
		key: "working_hours_display",
		label: __("Working Hrs"),
		sortable: true,
		sort_key: "working_hours",
		align: "right",
	},
	{ key: "punches", label: __("Punches"), sortable: true, align: "right" },
];

const EMPS_MONTH_OPTIONS = () => [
	{ value: 1, label: __("January") },
	{ value: 2, label: __("February") },
	{ value: 3, label: __("March") },
	{ value: 4, label: __("April") },
	{ value: 5, label: __("May") },
	{ value: 6, label: __("June") },
	{ value: 7, label: __("July") },
	{ value: 8, label: __("August") },
	{ value: 9, label: __("September") },
	{ value: 10, label: __("October") },
	{ value: 11, label: __("November") },
	{ value: 12, label: __("December") },
];

timebridge.employee_monthly_punch_summary.render_inline = function ($parent, options = {}) {
	inject_styles();
	const initial = parse_month_value(options.month || current_month());
	const state = {
		machine_user: options.machine_user || "",
		year: initial.year,
		month_num: initial.month_num,
		month: month_from_parts(initial.year, initial.month_num),
		user_label: "",
		rows: [],
		sort_field: "date",
		sort_order: "asc",
		search: "",
	};
	const use_sidebar = Boolean(options.$sidebar);
	const shell_class = use_sidebar ? "tb-emps-inline tb-emps-with-sidebar" : "tb-emps-inline";
	const $shell = $(`<div class="${shell_class}"></div>`).appendTo($parent);
	const ui = build_panel($shell, state, { $sidebar: options.$sidebar });
	wire_panel(ui, state);
	if (state.machine_user) {
		load_rows(state, ui);
	} else {
		ui.$body.html(
			`<div class="tb-emps-empty">${__("Select a user and month to view punch summary.")}</div>`
		);
		ui.$count.text("");
	}
	return { state, ui, reload: () => load_rows(state, ui) };
};

function current_month() {
	return frappe.datetime.get_today().slice(0, 7) + "-01";
}

function parse_month_value(value) {
	if (!value) {
		const today = frappe.datetime.get_today();
		return { year: parseInt(today.slice(0, 4), 10), month_num: parseInt(today.slice(5, 7), 10) };
	}
	const parts = String(value).split("-");
	return {
		year: parseInt(parts[0], 10),
		month_num: parseInt(parts[1], 10),
	};
}

function month_from_parts(year, month_num) {
	return `${year}-${String(month_num).padStart(2, "0")}-01`;
}

function build_year_options() {
	const current = new Date().getFullYear();
	const years = [];
	for (let y = current - 5; y <= current + 1; y++) {
		years.push(String(y));
	}
	return years.join("\n");
}

function month_label_for_num(month_num) {
	const option = EMPS_MONTH_OPTIONS().find((row) => row.value === month_num);
	return option ? option.label : EMPS_MONTH_OPTIONS()[0].label;
}

function month_num_from_label(label) {
	const option = EMPS_MONTH_OPTIONS().find((row) => row.label === label);
	return option ? option.value : 1;
}

function format_period_label(year, month_num) {
	return `${month_label_for_num(month_num)} ${year}`;
}

function build_panel($root, state, { $sidebar = null } = {}) {
	const use_sidebar = Boolean($sidebar);
	const subtitle = format_subtitle(state);
	const filter_mount = use_sidebar
		? $('<div class="list-sidebar overlay-sidebar tb-emps-sidebar"></div>').appendTo($sidebar)
		: $root;

	if (use_sidebar) {
		filter_mount.html(`
			<div class="sidebar-section">
				<div class="sidebar-label">${__("Filters")}</div>
				<div class="tb-emps-field tb-emps-field-user">
					<label class="tb-emps-field-label">${__("User")}</label>
					<div class="tb-emps-link-wrap tb-emps-user"></div>
				</div>
				<div class="tb-emps-field tb-emps-field-year">
					<label class="tb-emps-field-label">${__("Year")}</label>
					<div class="tb-emps-control-wrap tb-emps-year"></div>
				</div>
				<div class="tb-emps-field tb-emps-field-month">
					<label class="tb-emps-field-label">${__("Month")}</label>
					<div class="tb-emps-control-wrap tb-emps-month"></div>
				</div>
			</div>
		`);
	}

	$root.append(`
		${use_sidebar ? "" : `<div class="tb-emps-header">
			<div>
				<div class="tb-emps-title">${__("Employee Monthly Punch Summary")}</div>
				<div class="tb-emps-subtitle">${subtitle}</div>
			</div>
		</div>`}
		<div class="tb-emps-toolbar${use_sidebar ? " tb-emps-toolbar-search-only" : ""}">
			${use_sidebar ? "" : `<div class="tb-emps-field tb-emps-field-user">
				<label class="tb-emps-field-label">${__("User")}</label>
				<div class="tb-emps-link-wrap tb-emps-user"></div>
			</div>
			<div class="tb-emps-field tb-emps-field-year">
				<label class="tb-emps-field-label">${__("Year")}</label>
				<div class="tb-emps-control-wrap tb-emps-year"></div>
			</div>
			<div class="tb-emps-field tb-emps-field-month">
				<label class="tb-emps-field-label">${__("Month")}</label>
				<div class="tb-emps-control-wrap tb-emps-month"></div>
			</div>`}
			<div class="tb-emps-field tb-emps-field-search">
				<label class="tb-emps-field-label">${__("Search")}</label>
				<div class="tb-emps-search-inner">
					<svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
						<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
					</svg>
					<input type="text" class="tb-emps-search-input" placeholder="${__("Search...")}">
				</div>
			</div>
		</div>
		<div class="tb-emps-body">
			<div class="tb-emps-loading">${__("Loading")}...</div>
		</div>
		<div class="tb-emps-footer">
			<span class="tb-emps-count"></span>
			<button type="button" class="tb-emps-btn-export">&#11015; ${__("Export CSV")}</button>
		</div>
	`);

	const filter_root = use_sidebar ? filter_mount : $root;

	const ui = {
		$root,
		$body: $root.find(".tb-emps-body"),
		$count: $root.find(".tb-emps-count"),
		$search: $root.find(".tb-emps-search-input"),
		$export: $root.find(".tb-emps-btn-export"),
	};

	function on_period_change() {
		state.year = parseInt(year_control.get_value(), 10);
		state.month_num = month_num_from_label(month_control.get_value());
		state.month = month_from_parts(state.year, state.month_num);
		update_subtitle($root, state);
		load_rows(state, ui);
	}

	const user_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Link",
			fieldname: "machine_user",
			label: __("User"),
			options: "TimeBridge Machine User",
			only_select: 1,
			change: () => {
				state.machine_user = user_control.get_value() || "";
				const label = user_control.get_label_value();
				state.user_label = label || state.machine_user;
				update_subtitle($root, state);
				load_rows(state, ui);
			},
		},
		parent: filter_root.find(".tb-emps-user"),
		render_input: true,
	});
	if (state.machine_user) {
		user_control.set_value(state.machine_user);
	}
	normalize_frappe_control(filter_root.find(".tb-emps-user"));

	const year_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Select",
			fieldname: "year",
			label: __("Year"),
			options: build_year_options(),
			change: on_period_change,
		},
		parent: filter_root.find(".tb-emps-year"),
		render_input: true,
	});
	year_control.set_value(String(state.year));
	normalize_frappe_control(filter_root.find(".tb-emps-year"));

	const month_control = frappe.ui.form.make_control({
		df: {
			fieldtype: "Select",
			fieldname: "month",
			label: __("Month"),
			options: EMPS_MONTH_OPTIONS()
				.map((row) => row.label)
				.join("\n"),
			change: on_period_change,
		},
		parent: filter_root.find(".tb-emps-month"),
		render_input: true,
	});
	month_control.set_value(month_label_for_num(state.month_num));
	normalize_frappe_control(filter_root.find(".tb-emps-month"));

	ui.user_control = user_control;
	ui.year_control = year_control;
	ui.month_control = month_control;
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
	$root.find(".tb-emps-subtitle").text(format_subtitle(state));
}

function format_subtitle(state) {
	const user = state.user_label || state.machine_user || __("No user selected");
	return `${user} · ${format_period_label(state.year, state.month_num)}`;
}

function load_rows(state, ui) {
	if (!state.machine_user) {
		ui.$body.html(
			`<div class="tb-emps-empty">${__("Select a user and month to view punch summary.")}</div>`
		);
		ui.$count.text("");
		return;
	}

	ui.$body.html(`<div class="tb-emps-loading">${__("Loading")}...</div>`);
	frappe
		.xcall(EMPS_API, {
			machine_user: state.machine_user,
			month: state.month,
		})
		.then((rows) => {
			state.rows = (rows || []).map((row) => ({
				...row,
				date_display: row.date_display || "",
				punched_in_display: row.punched_in_display || "",
				punched_out_display: row.punched_out_display || "",
			}));
			render_table(state, ui);
		})
		.catch(() => {
			ui.$body.html(`<div class="tb-emps-empty">${__("Could not load punch data.")}</div>`);
			ui.$count.text("");
		});
}

function render_table(state, ui) {
	const columns = EMPS_COLUMNS();
	const filtered = filter_rows(state.rows, columns, state.search);
	const sorted = sort_rows(filtered, state);

	if (!sorted.length) {
		ui.$body.html(`<div class="tb-emps-empty">${__("No data for this month.")}</div>`);
		ui.$count.text("");
		return;
	}

	const header = columns
		.map((col) => {
			const active = state.sort_field === (col.sort_key || col.key);
			const arrow = active ? (state.sort_order === "asc" ? " ↑" : " ↓") : "";
			const cls = [col.align === "right" ? "r" : "", "tb-emps-sortable"].filter(Boolean).join(" ");
			return `<th class="${cls}" data-sort="${frappe.utils.escape_html(col.sort_key || col.key)}">${col.label}${arrow}</th>`;
		})
		.join("");

	const body = sorted
		.map((row) => {
			const tds = columns
				.map((col) => {
					const val = row[col.key] ?? "";
					const cls = col.align === "right" ? "r" : "";
					return `<td class="${cls}">${frappe.utils.escape_html(String(val))}</td>`;
				})
				.join("");
			return `<tr>${tds}</tr>`;
		})
		.join("");

	ui.$body.html(`
		<table class="tb-emps-table">
			<thead><tr>${header}</tr></thead>
			<tbody>${body}</tbody>
		</table>
	`);

	ui.$body.find(".tb-emps-sortable").on("click", (e) => {
		const field = $(e.currentTarget).data("sort");
		if (state.sort_field === field) {
			state.sort_order = state.sort_order === "asc" ? "desc" : "asc";
		} else {
			state.sort_field = field;
			state.sort_order =
				field === "date" || field === "date_display" ? "asc" : field === "punches" ? "desc" : "asc";
		}
		render_table(state, ui);
	});

	const with_punches = sorted.filter((row) => (row.punches || 0) > 0).length;
	ui.$count.text(
		__("{0} days with punches · {1} days", [with_punches, sorted.length])
	);
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
		if (sort_field === "punches" || sort_field === "working_hours") {
			return ((left || 0) - (right || 0)) * dir;
		}
		if (!left && !right) return 0;
		if (!left) return 1;
		if (!right) return -1;
		if (sort_field === "date" || String(left).includes("-")) {
			left = new Date(left).getTime();
			right = new Date(right).getTime();
		} else if (left instanceof Date || String(left).includes("T")) {
			left = new Date(left).getTime();
			right = new Date(right).getTime();
		}
		return (left > right ? 1 : left < right ? -1 : 0) * dir;
	});
}

function export_csv(state, ui) {
	const columns = EMPS_COLUMNS();
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
		download: `employee-monthly-punch-summary-${state.month.slice(0, 7)}.csv`,
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
	if (document.getElementById("tb-emps-styles-v1")) return;
	const style = document.createElement("style");
	style.id = "tb-emps-styles-v1";
	style.textContent = `
		.tb-emps-inline { max-width: 960px; margin: 0 auto; padding: 0 8px 24px; overflow: visible; }
		.tb-emps-inline.tb-emps-with-sidebar { max-width: none; margin: 0; padding: 0 0 24px; }
		.tb-emps-sidebar { padding: 8px 0; }
		.tb-emps-sidebar .tb-emps-field { width: 100%; margin-bottom: 12px; }
		.tb-emps-toolbar-search-only .tb-emps-field-search { flex: 1 1 240px; min-width: 240px; }
		.tb-emps-inline > .tb-emps-header,
		.tb-emps-inline > .tb-emps-toolbar,
		.tb-emps-inline > .tb-emps-body,
		.tb-emps-inline > .tb-emps-footer {
			background: var(--card-bg);
			border-left: 1px solid var(--border-color);
			border-right: 1px solid var(--border-color);
		}
		.tb-emps-inline > .tb-emps-header {
			border-top: 1px solid var(--border-color);
			border-radius: 10px 10px 0 0;
		}
		.tb-emps-inline > .tb-emps-footer {
			border-bottom: 1px solid var(--border-color);
			border-radius: 0 0 10px 10px;
		}
		.tb-emps-header {
			display: flex; align-items: center; justify-content: space-between;
			padding: 16px 20px; border-bottom: 1px solid var(--border-color); flex-shrink: 0;
		}
		.tb-emps-title { font-size: 15px; font-weight: 700; color: var(--text-color); }
		.tb-emps-subtitle { font-size: 11px; color: var(--text-muted); margin-top: 2px; }
		.tb-emps-toolbar {
			padding: 12px 20px; border-bottom: 1px solid var(--border-color);
			display: flex; align-items: flex-end; gap: 12px; flex-shrink: 0; flex-wrap: wrap;
			overflow: visible; position: relative; z-index: 20;
		}
		.tb-emps-field { flex: 0 0 auto; }
		.tb-emps-field-user { width: 240px; }
		.tb-emps-field-year { width: 100px; }
		.tb-emps-field-month { width: 150px; }
		.tb-emps-field-search { flex: 1 1 220px; min-width: 220px; }
		.tb-emps-field-label {
			display: block; font-size: 10px; font-weight: 700; text-transform: uppercase;
			letter-spacing: .3px; color: var(--text-muted); margin-bottom: 4px; line-height: 1;
			min-height: 10px;
		}
		.tb-emps-link-wrap, .tb-emps-control-wrap { overflow: visible; position: relative; }
		.tb-emps-link-wrap .awesomplete { z-index: 30; width: 100%; }
		.tb-emps-link-wrap .awesomplete > ul {
			z-index: 40; max-height: 240px; overflow-y: auto;
		}
		.tb-emps-search-inner {
			display: flex; align-items: center; gap: 8px;
			border: 1px solid var(--border-color); border-radius: 6px;
			padding: 0 12px; height: 32px; background: var(--card-bg);
			box-sizing: border-box;
		}
		.tb-emps-search-inner input {
			border: 0; outline: none; width: 100%; background: transparent; font-size: 13px;
			height: 30px; line-height: 30px; padding: 0;
		}
		.tb-emps-month .form-group, .tb-emps-year .form-group, .tb-emps-user .form-group { margin: 0; }
		.tb-emps-month select, .tb-emps-year select, .tb-emps-month input, .tb-emps-year input, .tb-emps-user input {
			height: 32px !important; min-height: 32px !important;
			border-radius: 6px !important; box-sizing: border-box;
		}
		.tb-emps-body { flex: 1; overflow: auto; padding: 0; min-height: 200px; position: relative; z-index: 1; }
		.tb-emps-footer {
			padding: 12px 20px; border-top: 1px solid var(--border-color);
			display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
		}
		.tb-emps-count { font-size: 12px; color: var(--text-muted); }
		.tb-emps-btn-export {
			height: 30px; padding: 0 16px; font-size: 12px; font-weight: 600;
			border: 1px solid var(--border-color); border-radius: 6px;
			background: var(--card-bg); color: var(--text-color); cursor: pointer;
		}
		.tb-emps-btn-export:hover { background: var(--subtle-fg); }
		.tb-emps-table { width: 100%; border-collapse: collapse; font-size: 13px; }
		.tb-emps-table thead th {
			padding: 10px 14px; font-size: 11px; font-weight: 700; color: var(--text-muted);
			border-bottom: 1px solid var(--border-color); text-align: left;
			background: var(--subtle-fg); position: sticky; top: 0; z-index: 1;
			text-transform: uppercase; letter-spacing: .3px; white-space: nowrap;
		}
		.tb-emps-table thead th.r { text-align: right; }
		.tb-emps-table thead th.tb-emps-sortable { cursor: pointer; user-select: none; }
		.tb-emps-table td {
			padding: 10px 14px; border-bottom: 1px solid var(--border-color);
			text-align: left; vertical-align: middle;
		}
		.tb-emps-table td.r { text-align: right; font-weight: 600; }
		.tb-emps-table tbody tr:last-child td { border-bottom: none; }
		.tb-emps-table tbody tr:hover td { background: var(--highlight-color); }
		.tb-emps-empty, .tb-emps-loading {
			text-align: center; padding: 40px; color: var(--text-muted); font-size: 13px;
		}
	`;
	document.head.appendChild(style);
}
