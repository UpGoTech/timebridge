// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.query_reports["Attendance Report"] = {

    filters: [
        // Always one calendar month. A register is printed and signed per
        // month, so a free date range would produce a sheet nobody files.
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
            // A number box rather than a list: the arrows step through years
            // without opening anything, and a year outside a fixed list can
            // still be typed straight in.
            fieldtype: "Int",
            default: new Date().getFullYear()
        },

        {
            fieldname: "organization",
            label: __("Organization"),
            fieldtype: "Link",
            options: "Organization"
        },
        {
            fieldname: "branch",
            label: __("Branch"),
            fieldtype: "Link",
            options: "Branch",
            get_query: function () {
                const organization = frappe.query_report.get_filter_value("organization");
                return organization ? { filters: { organization: organization } } : {};
            }
        },
        {
            fieldname: "department",
            label: __("Department"),
            fieldtype: "Link",
            options: "Department",
            get_query: function () {
                const branch = frappe.query_report.get_filter_value("branch");
                return branch ? { filters: { branch: branch } } : {};
            }
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
        add_export_buttons(report, { landscape: true });
        add_year_steppers(report);
    },

    get_datatable_options: function (options) {
        // The row-number column ships without a heading, which leaves an
        // unlabelled column of digits beside the codes.
        return Object.assign(options, { serialNoColumn: true, checkboxColumn: false });
    },

    after_datatable_render: function (datatable) {

        // Filters can be rebuilt from under us, taking the arrows with them.
        // Re-attaching after every render is cheaper than tracking that;
        // add_year_steppers does nothing when they are already in place.
        add_year_steppers(frappe.query_report);

        // Shade the date itself on a weekly off, the way a paper register
        // does. The column definition carries the flag; the header cell is
        // not reachable from the formatter, which only ever sees body cells.
        shade_weekly_off_headers(datatable);
    },

    formatter: function (value, row, column, data, default_formatter) {

        // One letter per day, colour-coded.
        if (column.fieldname && column.fieldname.startsWith("day_")) {

            // Colours chosen to survive a black-and-white printer: absence is
            // the only one that stays visibly darker, because it is the one
            // people scan the page looking for.
            const colours = {
                P: "var(--green-600)",
                A: "var(--red-500)",
                "P/A": "var(--orange-500)",
                S: "var(--blue-600)",
                L: "var(--blue-500)",
                H: "var(--purple-600)",
                R: "var(--gray-600)",
                I: "var(--purple-500)",
                "?": "var(--orange-400)"
            };

            const colour = colours[value] || "var(--text-muted)";
            const weight = value === "A" ? "700" : "500";

            return `<div style="text-align:center;color:${colour};font-weight:${weight}">${value || ""}</div>`;
        }

        value = default_formatter(value, row, column, data);

        // Two destinations, because they answer different questions. The name
        // opens the day-by-day detail — the times behind these letters, for
        // the month already on screen. The code opens the Employee record
        // itself, for the shift, phone number and device mapping.
        //
        // The row carries the employee id; the name alone could not be used,
        // because employees are named EMP-##### and two people may share a
        // name.
        //
        // Neither is styled as a link. This sheet is printed, and a column of
        // blue underlined names would carry that ink onto paper for no reason.
        // They reveal themselves on hover instead.
        if (data && data.employee) {

            // Hand the name over before anyone clicks.
            //
            // Employee is shown by title rather than id, so the detail report's
            // Link filter would otherwise have to fetch that title from the
            // server — and it does so without waiting, leaving the filter box
            // empty for a moment. The report reads its filters out of the DOM,
            // finds nothing, and renders "pick an employee"; only a manual
            // refresh then worked.
            //
            // This row already holds both halves, and navigation is in-page, so
            // seeding the cache here means the filter fills in synchronously
            // and there is no moment to lose the race in.
            frappe.utils.add_link_title("Employee", data.employee, data.employee_name);

            if (column.fieldname === "employee_name") {

                value = `<a href="${detail_route(data.employee)}"
                            class="tb-employee-link"
                            title="${__("Open day-by-day detail")}">${value}</a>`;

            } else if (column.fieldname === "employee_code") {

                value = `<a href="/app/employee/${encodeURIComponent(data.employee)}"
                            class="tb-employee-link"
                            title="${__("Open employee record")}">${value}</a>`;
            }
        }

        // Absence is the one total worth spotting without reading across.
        if (column.fieldname === "total_absent" && data && data.total_absent > 0) {
            value = `<span style="color: var(--text-on-red, #b34d4d);">${value}</span>`;
        }

        return value;
    }

};


/**
 * Where a name click lands: the same month, for one person, with the times.
 *
 * The period travels in the URL because Frappe turns query parameters into
 * filters (router.js, set_route_options_from_url). Without it the detail would
 * open on the current month while the register behind it showed another one,
 * and the two would quietly disagree.
 */
function detail_route(employee) {

    const filters = frappe.query_report.get_filter_values() || {};

    const params = new URLSearchParams({
        employee: employee,
        month: filters.month || (new Date().getMonth() + 1).toString(),
        year: filters.year || new Date().getFullYear()
    });

    return `/app/query-report/Employee Attendance Detail?${params.toString()}`;
}


/**
 * Put Excel, PDF and Print on the toolbar instead of inside the "..." menu.
 *
 * Frappe's own methods are called rather than reimplemented, so exports keep
 * working the way the menu does — same filters, same access log, same naming.
 */
function add_export_buttons(report, opts) {

    opts = opts || {};

    // Third argument is the group name, which becomes the dropdown's label.
    // Deliberately not "Actions": that is Frappe's own menu for chart and card
    // tools, and mixing exports into it buries three things people use daily
    // among three they rarely touch. Their own dropdown sits beside it.
    const EXPORT = __("Export");

    report.page.add_inner_button(__("Excel"), function () {
        // Frappe's export dialog already defaults to Excel: one click, then
        // Download.
        report.export_report();
    }, EXPORT);

    report.page.add_inner_button(__("PDF"), function () {
        open_print_settings(report, opts, function (print_settings) {
            report.pdf_report(print_settings);
        });
    }, EXPORT);

    report.page.add_inner_button(__("Print"), function () {
        open_print_settings(report, opts, function (print_settings) {
            report.print_report(print_settings);
        });
    }, EXPORT);
}


function open_print_settings(report, opts, run) {

    const dialog = frappe.ui.get_print_settings(
        false,
        run,
        report.report_doc.letter_head,
        report.get_visible_columns()
    );

    // Thirty-eight columns never fit portrait A4. Preselecting landscape saves
    // discovering that by wasting a sheet.
    if (opts.landscape && dialog.fields_dict.orientation) {
        dialog.set_value("orientation", "Landscape");
    }

    report.add_portrait_warning(dialog);
}


/**
 * Colour the date headers that fall on a weekly off.
 *
 * The report's formatter is only given body cells, so the header has to be
 * reached through the rendered table. Which columns to shade comes from the
 * `weekly_off` flag the server puts on each day column — the same flag the
 * attendance calculation uses, so the register cannot disagree with the
 * records it is printing.
 */
function shade_weekly_off_headers(datatable) {

    if (!datatable || !datatable.datamanager) {
        return;
    }

    const columns = datatable.datamanager.columns || [];

    columns.forEach((col) => {

        if (!col.weekly_off) {
            return;
        }

        // Header cells carry their own class. `dt-cell--col-N` also matches
        // the inline filter row below the headings, which is why the shading
        // was landing on a row of empty search boxes instead of the date.
        const $cell = $(datatable.header).find(`.dt-cell--header-${col.colIndex}`);

        $cell.css({
            "background-color": "#ffd7d7",
            "font-weight": "700"
        });
    });
}


/**
 * Replace the year box's spinner with two arrows that step the year.
 *
 * A dropdown meant opening a list to move one year — three actions for a
 * one-step change. The browser's own spinner runs the wrong way round for a
 * calendar: here the up arrow goes back in time, not forward.
 *
 * The arrows are hung off the input's own parent. Filters in the page header
 * are built in "only_input" mode, which has no .control-input div at all — an
 * earlier attempt targeted that and silently attached nothing.
 */
function add_year_steppers(report) {

    const filter = report.get_filter && report.get_filter("year");

    if (!filter || !filter.$input || filter.$wrapper.find(".tb-year-steps").length) {
        return;
    }

    const $input = filter.$input;
    const $holder = $input.parent();

    // Frappe's Int control is an <input type="text">, so there is no native
    // spinner to hide — every arrow in this box is one of ours.
    //
    // The left side keeps Frappe's own 8px so the year still lines up with the
    // month beside it. Only the right is widened, far enough that the digits
    // never reach the arrows.
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


frappe.dom.set_style(`
    /* Reads as ordinary text until pointed at, so the printed register keeps
       looking like a register. */
    a.tb-employee-link,
    a.tb-employee-link:visited {
        color: inherit;
        text-decoration: none;
    }
    a.tb-employee-link:hover {
        color: var(--primary);
        text-decoration: underline;
    }
    @media print {
        a.tb-employee-link { color: inherit !important; text-decoration: none !important; }
    }
`);
