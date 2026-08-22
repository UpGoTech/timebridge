// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.query_reports["Punch Register"] = {

    filters: [
        // The same month/year pair as the other two reports, so moving between
        // them does not mean learning a third way to pick a period.
        {
            fieldname: "month",
            label: __("Month"),
            fieldtype: "Select",
            default: (new Date().getMonth() + 1).toString(),
            options: [
                { value: "1", label: __("January") },
                { value: "2", label: __("February") },
                { value: "3", label: __("March") },
                { value: "4", label: __("April") },
                { value: "5", label: __("May") },
                { value: "6", label: __("June") },
                { value: "7", label: __("July") },
                { value: "8", label: __("August") },
                { value: "9", label: __("September") },
                { value: "10", label: __("October") },
                { value: "11", label: __("November") },
                { value: "12", label: __("December") }
            ]
        },
        {
            fieldname: "year",
            label: __("Year"),
            fieldtype: "Int",
            default: new Date().getFullYear()
        },
        // Also the sheet's heading, so an exported file says which terminal
        // it came from. Organization / Branch / Department are left off:
        // they do not split anyone here, and Machine already does.
        {
            fieldname: "biometric_machine",
            label: __("Machine"),
            fieldtype: "Link",
            options: "Biometric Machine"
        },
        {
            fieldname: "shift",
            label: __("Shift"),
            fieldtype: "Link",
            options: "Shift"
        },
        {
            fieldname: "employee",
            label: __("Employee"),
            fieldtype: "Link",
            options: "Employee"
        },
        {
            fieldname: "include_inactive",
            label: __("Include Inactive"),
            fieldtype: "Check",
            default: 0
        }
    ],

    onload: function (report) {
        add_year_steppers(report);
        add_export_buttons(report);
    },

    get_datatable_options: function (options) {
        return Object.assign(options, { serialNoColumn: true, checkboxColumn: false });
    },

    after_datatable_render: function (datatable) {
        add_year_steppers(frappe.query_report);
        shade_weekly_off_headers(datatable);
    },

    formatter: function (value, row, column, data, default_formatter) {

        if (column.fieldname && column.fieldname.startsWith("day_")) {

            // A time is the ordinary case and stays plain. The letters are the
            // exceptions — a day nobody was expected, or nobody came — and are
            // coloured the same way the register colours them, so the two
            // reports read alike.
            const letters = {
                R: "var(--gray-500)",
                H: "var(--purple-600)",
                S: "var(--blue-600)",
                L: "var(--blue-500)",
                A: "var(--red-500)",
                "?": "var(--orange-400)"
            };

            if (letters[value]) {
                return `<div style="text-align:center;color:${letters[value]};
                        font-weight:${value === "A" ? "700" : "500"}">${value}</div>`;
            }

            // A trailing dash means the Out never arrived. Dimming just that
            // half keeps the real time readable while showing what is missing.
            if (typeof value === "string" && value.endsWith("-")) {
                return `<div style="text-align:center">${value.slice(0, -1)}<span
                        style="color:var(--orange-500)">–</span></div>`;
            }

            return `<div style="text-align:center">${value || ""}</div>`;
        }

        return default_formatter(value, row, column, data);
    }

};


/**
 * Excel, PDF and Print on the toolbar — the same three the other reports carry.
 *
 * Landscape is preselected because thirty-one time columns are wider than any
 * portrait page; this report is built for Excel, and printing it at all is the
 * unusual case.
 */
function add_export_buttons(report) {

    // Third argument is the group name, which becomes the dropdown's label.
    // Deliberately not "Actions": that is Frappe's own menu for chart and card
    // tools, and mixing exports into it buries three things people use daily
    // among three they rarely touch. Their own dropdown sits beside it.
    const EXPORT = __("Export");

    report.page.add_inner_button(__("Excel"), function () {
        download_excel(report);
    }, EXPORT);

    report.page.add_inner_button(__("PDF"), function () {
        open_print_settings(report, (settings) => report.pdf_report(settings));
    }, EXPORT);

    report.page.add_inner_button(__("Print"), function () {
        open_print_settings(report, (settings) => report.print_report(settings));
    }, EXPORT);
}


/**
 * The report's own workbook rather than Frappe's.
 *
 * Frappe's export writes the grid and nothing else: no title, no machine, no
 * month, no frozen header, and every declared column width divided by ten —
 * which is what left thirty-one time columns spilling into each other. The
 * server builds the file instead.
 *
 * Posted as a form rather than called, because the response is the file. A
 * frappe.call would hand back bytes with nowhere to put them; open_url_post is
 * how Frappe's own exports do the same thing, and it carries the CSRF token.
 */
function download_excel(report) {

    open_url_post(frappe.request.url, {
        cmd: "timebridge.timebridge.report.punch_register.punch_register.export_excel",
        filters: JSON.stringify(report.get_filter_values(true))
    });
}


function open_print_settings(report, run) {

    const dialog = frappe.ui.get_print_settings(
        false,
        run,
        report.report_doc.letter_head,
        report.get_visible_columns()
    );

    if (dialog.fields_dict.orientation) {
        dialog.set_value("orientation", "Landscape");
    }

    report.add_portrait_warning(dialog);
}


/**
 * Tint the date of a weekly off in the header row.
 *
 * The column definition carries the flag; the header cell cannot be reached
 * from the formatter, which only ever sees body cells. dt-cell--header-N is
 * deliberate — dt-cell--col-N also matches the inline filter row underneath,
 * which put the tint on an empty search box.
 */
function shade_weekly_off_headers(datatable) {

    if (!datatable || !datatable.datamanager) {
        return;
    }

    (datatable.datamanager.columns || []).forEach(function (col) {

        if (!col.weekly_off) {
            return;
        }

        const $cell = datatable.header.querySelector(`.dt-cell--header-${col.colIndex}`);

        if ($cell) {
            $cell.style.backgroundColor = "var(--red-500)";
            $cell.style.color = "#fff";
        }
    });
}


/**
 * Step the year with the arrows on the number box.
 *
 * Frappe's Int control is an <input type="text">, so there is no native spinner
 * to hide — every arrow here is one of ours.
 */
function add_year_steppers(report) {

    const filter = report && report.get_filter && report.get_filter("year");

    if (!filter || !filter.$input || filter.$wrapper.find(".tb-year-steps").length) {
        return;
    }

    const $input = filter.$input;
    const $holder = $input.parent();

    $input.css("padding-right", "34px");
    $holder.css("position", "relative");

    $holder.append(`
        <div class="tb-year-steps" style="position:absolute;right:18px;top:50%;
             transform:translateY(-50%);display:flex;flex-direction:column;
             line-height:7px;cursor:pointer;user-select:none;
             color:var(--text-muted);z-index:2">
            <span class="tb-year-prev" title="${__("Previous year")}"
                  style="font-size:8px;padding:1px 2px">&#9650;</span>
            <span class="tb-year-next" title="${__("Next year")}"
                  style="font-size:8px;padding:1px 2px">&#9660;</span>
        </div>
    `);

    const step = (by) => {
        const now = cint(filter.get_value()) || new Date().getFullYear();
        filter.set_value(now + by);
        report.refresh();
    };

    // Up goes to the earlier year, down to the later one — as asked for.
    $holder.find(".tb-year-prev").on("click", () => step(-1));
    $holder.find(".tb-year-next").on("click", () => step(1));
}
