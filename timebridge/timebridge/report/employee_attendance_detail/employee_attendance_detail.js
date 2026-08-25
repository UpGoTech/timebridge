// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.query_reports["TimeBridge Employee Attendance Detail"] = {

    filters: [
        {
            fieldname: "employee",
            label: __("TimeBridge Employee"),
            fieldtype: "Link",
            options: "TimeBridge Employee"
            // Deliberately not reqd. Frappe answers a missing mandatory filter
            // with "Please set filters", which is both blunt and — on the way
            // in from the register — wrong, since an employee was in fact
            // chosen. The report says so itself in plainer words instead.
        },
        // Same month/year pair as the register, so moving between the two does
        // not mean learning a second way to pick a period.
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
        }
    ],

    onload: function (report) {

        add_year_steppers(report);
        add_back_button(report);
        add_export_buttons(report);

        // Returned so Frappe waits: onload sits between set_route_filters and
        // refresh in query_report.js, and run_serially honours a promise.
        return settle_link_filter(report, "employee", "TimeBridge Employee");
    },

    get_datatable_options: function (options) {

        // Ten columns do not fill a wide screen, and the leftover was showing
        // as a dead grey band down the right of the table. Fluid hands that
        // width back to the columns, so Date stops being clipped to
        // "01-07-20…" and Remarks gets room for a whole sentence.
        //
        // The register does the opposite on purpose: thirty-eight day columns
        // must stay narrow and scroll.
        return Object.assign(options, { layout: "fluid" });
    },

    after_datatable_render: function () {
        add_year_steppers(frappe.query_report);
    },

    formatter: function (value, row, column, data, default_formatter) {

        if (column.fieldname === "status_code") {

            // The same letters and the same colours as the register. Someone
            // arriving here from a click should not have to re-read a legend.
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

        // A weekly off is dimmed rather than hidden: the row has to stay, or
        // the dates stop running 1 to 31 and the month looks incomplete.
        if (data && data.status_code === "R") {
            value = `<span style="color:var(--text-muted)">${value}</span>`;
        }

        return value;
    }

};


/**
 * The way back to the register, on the same month.
 *
 * You arrive here by clicking a name, and the browser's Back button is the only
 * way out otherwise — which loses the month if the filters were changed in the
 * meantime. This carries the period across, so the register reopens showing the
 * month that was being read.
 *
 * An inner button rather than the page's secondary action: Frappe clears inner
 * buttons before every report loads, but leaves the secondary button alone. As
 * a secondary action it followed the user back to the register and sat there
 * offering to go somewhere they already were.
 */
function add_back_button(report) {

    report.page.add_inner_button(__("← Attendance Register"), function () {

        const filters = report.get_filter_values() || {};

        frappe.route_options = {
            month: filters.month || (new Date().getMonth() + 1).toString(),
            year: filters.year || new Date().getFullYear(),
        };

        frappe.set_route("query-report", "Attendance Report");
    });
}


/**
 * Excel, PDF and Print on the toolbar rather than buried in the "…" menu —
 * the same three the register carries, so the two reports behave alike.
 */
function add_export_buttons(report) {

    // Third argument is the group name, which becomes the dropdown's label.
    // Deliberately not "Actions": that is Frappe's own menu for chart and card
    // tools, and mixing exports into it buries three things people use daily
    // among three they rarely touch. Their own dropdown sits beside it.
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

    // Seven columns fit portrait A4 comfortably, so unlike the register this
    // one is left on Frappe's own default rather than forced to landscape.
    frappe.ui.get_print_settings(
        false,
        run,
        report.report_doc.letter_head,
        report.get_visible_columns()
    );
}


/**
 * Wait for a Link filter's box to catch up with the value it was given.
 *
 * TimeBridge Employee is shown by name rather than id, so its control fetches the title
 * from the server before it can fill the box (link.js, set_link_title). That
 * fetch is not awaited: set_value stores the real value on the control and
 * returns immediately, leaving the box briefly empty.
 *
 * The report meanwhile reads its filters straight out of the DOM
 * (base_control.js, get_value), finds nothing, and gives up — which is how an
 * employee arriving in the URL produced "Please set filters" while their name
 * sat in plain sight in the filter bar a moment later.
 *
 * So: if the control knows a value the box has not shown yet, warm the title
 * cache and paint it. With the title cached, set_link_title no longer awaits
 * anything and the box is filled before this returns.
 */
function settle_link_filter(report, fieldname, doctype) {

    const filter = report && report.get_filter && report.get_filter(fieldname);

    // The control stores the real value the moment it is set; only the visible
    // box lags. So the two are compared directly rather than through
    // get_value(), which reads one or the other depending on the control's
    // status and would let the pending case slip past.
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
        // A title that cannot be fetched must not leave the report stuck on a
        // spinner; the id alone still selects the right person.
        .catch(() => filter.set_input_value(value));
}


/**
 * Step the year with the arrows on the number box.
 *
 * Lifted from the register deliberately rather than shared: two reports each
 * owning their filter bar is easier to reason about than a helper file loaded
 * by both, and this is a dozen lines.
 */
function add_year_steppers(report) {

    const filter = report && report.get_filter && report.get_filter("year");

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

    $holder.find(".tb-year-prev").on("click", () => step(-1));
    $holder.find(".tb-year-next").on("click", () => step(1));
}


