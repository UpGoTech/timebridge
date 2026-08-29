// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.query_reports["Employee Working Hours"] = {

    filters: [
        {
            fieldname: "machine_user",
            label: __("TimeBridge Machine User"),
            fieldtype: "Link",
            options: "TimeBridge Machine User",
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            default: frappe.datetime.month_start(),
            reqd: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
            reqd: 1,
        },
    ],

    onload: function (report) {
        add_export_buttons(report);
        return settle_link_filter(report, "machine_user", "TimeBridge Machine User");
    },

    get_datatable_options: function (options) {
        return Object.assign(options, { layout: "fluid" });
    },

    formatter: function (value, row, column, data, default_formatter) {
        if (column.fieldname === "status_code") {
            const colours = {
                P: "var(--green-600)",
                A: "var(--red-500)",
                "P/A": "var(--orange-500)",
                S: "var(--blue-600)",
                L: "var(--blue-500)",
                H: "var(--purple-600)",
                R: "var(--gray-600)",
                I: "var(--purple-500)",
                "?": "var(--orange-400)",
            };

            const colour = colours[value] || "var(--text-muted)";
            const weight = value === "A" ? "700" : "500";

            return `<div style="text-align:center;color:${colour};font-weight:${weight}">${value || ""}</div>`;
        }

        value = default_formatter(value, row, column, data);

        if (data && data.status_code === "R") {
            value = `<span style="color:var(--text-muted)">${value}</span>`;
        }

        return value;
    },
};


function add_export_buttons(report) {
    const EXPORT = __("Export");

    report.page.add_inner_button(__("Excel"), function () {
        report.export_report();
    }, EXPORT);

    report.page.add_inner_button(__("PDF"), function () {
        open_print_settings(report, (settings) => report.pdf_report(settings));
    }, EXPORT);

    report.page.add_inner_button(__("Print"), function () {
        open_print_settings(report, (settings) => report.print_report(settings));
    }, EXPORT);
}


function open_print_settings(report, run) {
    frappe.ui.get_print_settings(
        false,
        run,
        report.report_doc.letter_head,
        report.get_visible_columns()
    );
}


function settle_link_filter(report, fieldname, doctype) {
    const filter = report && report.get_filter && report.get_filter(fieldname);

    if (!filter || !filter.value || !filter.get_input_value) {
        return;
    }

    if (filter.get_input_value()) {
        return;
    }

    const value = filter.value;

    return frappe.utils
        .fetch_link_title(doctype, value)
        .then(() => filter.set_formatted_input(value))
        .catch(() => filter.set_input_value(value));
}
