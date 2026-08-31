// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.query_reports["Daily Punch Summary"] = {
	filters: [
		{
			fieldname: "date",
			label: __("Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "machine",
			label: __("Machine"),
			fieldtype: "Link",
			options: "TimeBridge Machine",
		},
	],

	onload(report) {
		if (report._tb_daily_punch_summary_ready) {
			return;
		}
		report._tb_daily_punch_summary_ready = true;
		report._tb_search_query = "";

		inject_styles();
		setup_search(report);
		setup_footer(report);

		report.page.menu.hide_menu(__("Export"));
	},

	after_datatable_render() {
		const report = frappe.query_report;
		if (!report._tb_daily_punch_summary_ready || report._tb_in_search_apply) {
			return;
		}

		report._tb_source_data = (report.data || []).map((row) => ({ ...row }));
		if (report._tb_search_query) {
			apply_search(report);
			return;
		}
		update_count(report, report._tb_source_data.length);
	},
};

function inject_styles() {
	if (document.getElementById("tb-daily-punch-summary-style")) {
		return;
	}
	const style = document.createElement("style");
	style.id = "tb-daily-punch-summary-style";
	style.textContent = `
		.tb-dps-toolbar {
			margin: 0 0 12px;
		}
		.tb-dps-search-inner {
			display: flex;
			align-items: center;
			gap: 8px;
			border: 1px solid var(--border-color);
			border-radius: 8px;
			padding: 8px 12px;
			background: var(--card-bg);
		}
		.tb-dps-search-inner input {
			border: 0;
			outline: none;
			width: 100%;
			background: transparent;
			font-size: var(--text-base);
		}
		.tb-dps-footer {
			display: flex;
			align-items: center;
			justify-content: space-between;
			margin-top: 12px;
			padding-top: 12px;
			border-top: 1px solid var(--border-color);
		}
		.tb-dps-count {
			color: var(--text-muted);
			font-size: var(--text-sm);
		}
	`;
	document.head.appendChild(style);
}

function setup_search(report) {
	const $toolbar = $(`
		<div class="tb-dps-toolbar">
			<div class="tb-dps-search-inner">
				<svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
					<circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
				</svg>
				<input type="text" class="tb-dps-search-input" placeholder="${__("Search...")}">
			</div>
		</div>
	`);

	$toolbar.find(".tb-dps-search-input").on("input", (e) => {
		report._tb_search_query = (e.target.value || "").trim().toLowerCase();
		apply_search(report);
	});

	report.$report.before($toolbar);
	report._tb_search_wrapper = $toolbar;
}

function setup_footer(report) {
	const $footer = $(`
		<div class="tb-dps-footer">
			<span class="tb-dps-count"></span>
			<button type="button" class="btn btn-default btn-sm tb-dps-export">${__("Export CSV")}</button>
		</div>
	`);

	$footer.find(".tb-dps-export").on("click", () => export_csv(report));
	report.$report.after($footer);
	report._tb_footer = $footer;
}

function apply_search(report) {
	const source = report._tb_source_data || [];
	const query = report._tb_search_query || "";

	let filtered = source;
	if (query) {
		const fields = (report.columns || []).map((col) => col.fieldname);
		filtered = source.filter((row) =>
			fields.some((fieldname) =>
				String(row[fieldname] ?? "")
					.toLowerCase()
					.includes(query)
			)
		);
	}

	report.data = filtered;
	report._tb_in_search_apply = true;
	report.render_datatable();
	report._tb_in_search_apply = false;
	update_count(report, filtered.length);
}

function update_count(report, count) {
	if (!report._tb_footer) {
		return;
	}
	const label = count === 1 ? __("1 user") : __("{0} users", [count]);
	report._tb_footer.find(".tb-dps-count").text(label);
}

function export_csv(report) {
	const columns = report.columns || [];
	const rows = report.data || [];
	if (!rows.length) {
		frappe.show_alert({ message: __("No rows to export"), indicator: "orange" });
		return;
	}

	const header = columns.map((col) => csv_cell(col.label)).join(",");
	const body = rows
		.map((row) => columns.map((col) => csv_cell(row[col.fieldname])).join(","))
		.join("\n");

	const date = report.get_filter_value("date") || frappe.datetime.get_today();
	const blob = new Blob([header + "\n" + body], { type: "text/csv;charset=utf-8;" });
	const link = Object.assign(document.createElement("a"), {
		href: URL.createObjectURL(blob),
		download: `daily-punch-summary-${date}.csv`,
	});
	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);
	URL.revokeObjectURL(link.href);
}

function csv_cell(value) {
	return `"${String(value ?? "").replace(/"/g, '""')}"`;
}
