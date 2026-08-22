// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.ui.form.on("TimeBridge Leave", {

    setup(frm) {

        // Only types still in use. Without this, unticking Active on a leave
        // type retired it everywhere except the one place people pick from —
        // so a type nobody was meant to use again kept being offered.
        //
        // This narrows the picker, not the field: a leave already recorded
        // against a retired type still opens and still reads correctly.
        frm.set_query("leave_type", () => ({ filters: { is_active: 1 } }));
    },

    refresh: show_balance,
    employee: show_balance,
    leave_type: show_balance,
    from_date: show_balance,
    to_date: show_balance,
    half_day: show_balance

});


/**
 * Show what this leave will cost the employee's quota, before it is saved.
 *
 * Whether a day is paid used to be decided silently on save — the tick either
 * appeared or it did not, with no way to see why. That matters most on the
 * long leaves, where someone can ask for a month and discover afterwards that
 * only one day of it was paid.
 *
 * The figures come from the same server function that makes the decision on
 * save, so the panel cannot promise something the record will not honour.
 */
function show_balance(frm) {

    const $panel = frm.get_field("balance_panel").$wrapper;

    if (!frm.doc.employee || !frm.doc.leave_type || !frm.doc.from_date) {
        $panel.html(hint(__("Pick an employee, a leave type and a date to see the quota.")));
        return;
    }

    frappe.call({

        method: "timebridge.timebridge.doctype.timebridge_leave.timebridge_leave.leave_balance",
        args: {
            employee: frm.doc.employee,
            leave_type: frm.doc.leave_type,
            on_date: frm.doc.from_date,
            days: frm.doc.total_days || 1,
            // An existing record must not count itself, or reopening any saved
            // leave would always report the quota as spent.
            exclude: frm.is_new() ? null : frm.doc.name
        },

        callback: (r) => $panel.html(render_balance(r.message))

    });

}


function hint(text) {
    return `<div style="font-size:12px;color:var(--text-muted);padding:6px 0">${text}</div>`;
}


function render_balance(b) {

    if (!b) {
        return "";
    }

    if (b.reason === "type_never_paid") {
        return box("gray", __("This leave type is never paid."),
            __("Nothing is deducted from any quota."));
    }

    if (b.reason === "no_quota_set") {
        return box("orange", __("No paid quota is set for {0}.", [b.leave_type]),
            __("This leave will be UNPAID. Set a quota on the leave type if it should be paid."));
    }

    const rows = `
        <div style="display:grid;grid-template-columns:auto auto;gap:2px 16px;
                    font-size:12px;margin:6px 0;justify-content:start">
            <span style="color:var(--text-muted)">${__("Quota")} (${b.period_label})</span><b>${b.quota}</b>
            <span style="color:var(--text-muted)">${__("Already taken")}</span><b>${b.used}</b>
            <span style="color:var(--text-muted)">${__("Remaining")}</span><b>${b.remaining}</b>
            <span style="color:var(--text-muted)">${__("This request")}</span><b>${b.days_requested}</b>
        </div>`;

    if (b.will_be_paid) {
        return box("green", __("This leave will be PAID."), rows, true);
    }

    // Spelling out the split is the point: someone asking for a month needs to
    // see that all of it lands unpaid, not just that the tick did not appear.
    const detail = b.unpaid_days < b.days_requested
        ? __("Only {0} day(s) of quota remain, so all {1} day(s) are recorded UNPAID. Split it into two leaves if part should be paid.",
             [b.remaining, b.days_requested])
        : __("The quota for {0} is used up.", [b.period_label]);

    return box("orange", __("This leave will be UNPAID."), rows + `<div>${detail}</div>`, true);
}


function box(colour, headline, body, body_is_html) {

    const text = body_is_html ? body : `<div>${body}</div>`;

    return `
        <div style="border-left:3px solid var(--${colour}-500);
                    background:var(--${colour}-50, var(--bg-light-gray));
                    padding:8px 12px;border-radius:4px;font-size:12px;margin:4px 0">
            <div style="font-weight:600;margin-bottom:2px">${headline}</div>
            ${text}
        </div>`;
}
