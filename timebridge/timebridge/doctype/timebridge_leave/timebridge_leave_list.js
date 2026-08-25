// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.listview_settings["TimeBridge Leave"] = {

    onload: function (listview) {
        listview.page.add_inner_button(__("Add Leave for Many"), () => open_bulk_dialog());
    }

};


/**
 * Record several people's leave in one pass.
 *
 * The grid lives only in this dialog — its columns are declared inline, so no
 * child DocType exists and nothing is stored anywhere until Save. What Save
 * produces is ordinary TimeBridge Leave documents, which keeps one record of
 * a leave rather than two that could drift apart.
 */
function open_bulk_dialog() {

    const dialog = new frappe.ui.Dialog({

        title: __("Add Leave for Many"),
        size: "large",

        fields: [
            {
                fieldname: "leave_type",
                label: __("Leave Type"),
                fieldtype: "Link",
                options: "TimeBridge Leave Type",
                reqd: 1,
                // Only types still in use. A retired type would quietly record
                // leave nobody expects to see again.
                get_query: () => ({ filters: { is_active: 1 } }),
                onchange: function () {
                    show_quota_note(dialog, this.get_value());
                }
            },
            { fieldname: "quota_note", fieldtype: "HTML" },
            {
                fieldname: "rows",
                label: __("Leave Days"),
                fieldtype: "Table",
                cannot_add_rows: false,
                in_place_edit: false,
                reqd: 1,
                data: [],
                // One person, one date, one row. Two days for the same person
                // is two rows — which keeps every row a complete instruction
                // and needs no rule about what a range means.
                fields: [
                    {
                        fieldname: "employee",
                        label: __("TimeBridge Employee"),
                        fieldtype: "Link",
                        options: "TimeBridge Employee",
                        in_list_view: 1,
                        reqd: 1,
                        columns: 5,
                        get_query: () => ({ filters: { is_active: 1 } })
                    },
                    {
                        fieldname: "leave_date",
                        label: __("Date"),
                        fieldtype: "Date",
                        in_list_view: 1,
                        reqd: 1,
                        columns: 4
                    }
                ]
            }
        ],

        primary_action_label: __("Create"),

        primary_action(values) {

            const rows = (values.rows || []).filter((r) => r.employee && r.leave_date);

            if (!rows.length) {
                frappe.msgprint(__("Add at least one row with an employee and a date."));
                return;
            }

            dialog.get_primary_btn().prop("disabled", true);

            frappe.call({

                method: "timebridge.timebridge.doctype.timebridge_leave.timebridge_leave.create_bulk_leaves",
                args: { leave_type: values.leave_type, rows: rows },
                freeze: true,
                freeze_message: __("Recording leave…"),

                callback: (r) => {
                    dialog.hide();
                    show_result(r.message || {});
                    // The list is stale the moment anything was created.
                    cur_list && cur_list.refresh();
                },

                error: () => dialog.get_primary_btn().prop("disabled", false)
            });
        }
    });

    dialog.show();
}


/**
 * Say up front what this type's quota will do.
 *
 * A type with no quota records every day unpaid. That is correct behaviour and
 * completely invisible until payroll, so it is worth one line before the work
 * rather than a surprise after it.
 */
function show_quota_note(dialog, leave_type) {

    const $note = dialog.get_field("quota_note").$wrapper;

    if (!leave_type) {
        $note.empty();
        return;
    }

    frappe.db.get_value(
        "TimeBridge Leave Type",
        leave_type,
        ["quota", "quota_period", "is_paid"],
        (row) => {

            if (!row) {
                $note.empty();
                return;
            }

            const paid = cint(row.is_paid);
            const quota = flt(row.quota);

            let text;
            let colour;

            if (!paid) {
                text = __("{0} is never paid. Every day recorded here will be unpaid.", [leave_type]);
                colour = "var(--text-muted)";
            } else if (!quota) {
                text = __("{0} has no quota set, so every day recorded here will be UNPAID. Set a quota on the leave type if it should be paid.", [leave_type]);
                colour = "var(--orange-600)";
            } else {
                text = __("Quota: {0} paid day(s) per {1}. Anything beyond that is recorded unpaid.",
                    [quota, row.quota_period === "Yearly" ? __("year") : __("month")]);
                colour = "var(--text-muted)";
            }

            $note.html(`<div style="font-size:12px;color:${colour};padding:2px 0 6px">${text}</div>`);
        }
    );
}


/**
 * What actually happened, row by row.
 *
 * Skipped rows carry their reason. A bulk tool that reports only a count
 * leaves the user to work out which four of twenty did not go in.
 */
function show_result(result) {

    const created = result.created || [];
    const skipped = result.skipped || [];

    let html = `<div style="font-size:13px">
        <div style="margin-bottom:10px">
            <b style="font-size:15px;color:var(--green-600)">${created.length}</b>
            ${__("leave record(s) created")}
        </div>`;

    if (created.length) {

        html += `<table class="table table-bordered" style="font-size:12px;margin-bottom:14px">
            <thead><tr>
                <th>${__("TimeBridge Employee")}</th><th>${__("Date")}</th><th>${__("Paid")}</th>
            </tr></thead><tbody>`;

        created.forEach((c) => {
            const paid = c.is_paid
                ? `<span style="color:var(--green-600)">${__("Paid")}</span>`
                : `<span style="color:var(--orange-600)">${__("Unpaid")}</span>`;
            html += `<tr><td>${frappe.utils.escape_html(c.employee_name)}</td>
                         <td>${frappe.datetime.str_to_user(c.date)}</td>
                         <td>${paid}</td></tr>`;
        });

        html += `</tbody></table>`;
    }

    if (skipped.length) {

        html += `<div style="margin-bottom:8px">
            <b style="font-size:15px;color:var(--orange-600)">${skipped.length}</b>
            ${__("skipped")}
        </div>
        <table class="table table-bordered" style="font-size:12px">
            <thead><tr>
                <th>${__("TimeBridge Employee")}</th><th>${__("Date")}</th><th>${__("Why")}</th>
            </tr></thead><tbody>`;

        skipped.forEach((s) => {
            html += `<tr><td>${frappe.utils.escape_html(s.employee_name)}</td>
                         <td>${frappe.datetime.str_to_user(s.date)}</td>
                         <td>${frappe.utils.escape_html(s.reason)}</td></tr>`;
        });

        html += `</tbody></table>`;
    }

    html += `</div>`;

    frappe.msgprint({ title: __("Leave recorded"), message: html, wide: true });
}
