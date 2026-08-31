// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

// Mirrors STEP_NETWORK / STEP_CONNECT / STEP_READ / STEP_SAVE in
// services/device_info.py. The server sends step numbers, not labels, so
// these two lists must be changed together.
const STEPS = [
    { step: 1, label: __("Checking network") },
    { step: 2, label: __("Connecting to device") },
    { step: 3, label: __("Reading device information") },
    { step: 4, label: __("Saving to the record") }
];

// How long to wait for a worker to say it picked the job up. The job sits in
// the "short" queue, so anything beyond a few seconds means no worker is free
// — the single most common cause of this button appearing to do nothing.
const WORKER_PICKUP_SECONDS = 12;

// Added to the server's own job budget before the client gives up, so the UI
// never declares failure while the worker is still legitimately trying.
const WATCHDOG_GRACE_SECONDS = 15;

// How often to ask the server for progress. One second is far finer than the
// stages actually change, and the whole run is over in seconds.
const POLL_SECONDS = 1;

// Waiting on the device is a slower business — it polls us about every 30s,
// so checking every 2s is plenty and the wait has to be generous enough to
// cover a poll it has only just missed.
const FETCH_POLL_SECONDS = 2;

// Photos are slower and riskier than punches: the device has to collect the
// request, then upload images. Long enough to be fair, short enough that a
// firmware that dislikes the switches is caught quickly.
const PHOTO_POLL_SECONDS = 3;
const PHOTO_GIVE_UP_SECONDS = 300;
const FETCH_GIVE_UP_SECONDS = 120;

function endpoint_label(frm) {
    const host = `${frm.doc.ip_address || ""}:${frm.doc.port || ""}`;
    return cint(frm.doc.force_udp) ? `${host} UDP` : host;
}

// Only one progress dialog is meaningful at a time. Held here so a dialog
// closed mid-run can stop its own polling.
let active_progress = null;


frappe.ui.form.on("TimeBridge Machine", {

    onload(frm) {
        if (frm.is_new()) {
            frappe.set_route("add-machine");
        }
    },

    refresh(frm) {

        if (!frm.is_new()) {
            show_connection_health(frm);
        }

        // Five buttons in a row crowded the header and gave no clue which
        // belonged together. Two dropdowns instead: everything about the
        // device's data in one, everything about pictures in the other.
        const DEVICE = __("Device");
        const PHOTOS = __("Photos");

        // Every action needs a saved record — an unsaved machine has no id for
        // the server to work with — so the check lives here once instead of
        // being repeated in each handler.
        const needs_saved = (fn) => function () {

            if (frm.is_new()) {

                frappe.msgprint({
                    title: __("Not Saved"),
                    message: __("Save the machine first."),
                    indicator: "orange"
                });

                return;
            }

            fn(frm);
        };

        frm.add_custom_button(__("Test Connection"), needs_saved(start_connection_test), DEVICE);

        frm.add_custom_button(__("Fetch All Data"), needs_saved(start_fetch_all), DEVICE);

        frm.add_custom_button(__("Add User"), needs_saved(add_user_dialog), DEVICE);

        frm.add_custom_button(__("Fetch Photos"), needs_saved(start_photo_fetch), PHOTOS);

        frm.add_custom_button(__("Collect Photos"), needs_saved(start_photo_collection), PHOTOS);

    }

});


function add_user_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __("Add User"),
        fields: [
            { fieldname: "user_id", fieldtype: "Data", label: __("PIN"), reqd: 1 },
            { fieldname: "user_name", fieldtype: "Data", label: __("Name"), reqd: 1 },
            { fieldname: "privilege", fieldtype: "Select", label: __("Privilege"), options: "User\nAdmin", default: "User" },
            { fieldname: "card", fieldtype: "Data", label: __("Card Number") },
            { fieldname: "password", fieldtype: "Data", label: __("Device Password") },
            {
                fieldname: "also_machines",
                fieldtype: "Small Text",
                label: __("Also create on"),
                description: __("Optional extra TimeBridge Machine names, comma-separated. This machine is always included."),
            },
        ],
        primary_action_label: __("Create"),
        primary_action(values) {
            const machines = [frm.doc.name];
            (values.also_machines || "").split(/[\s,]+/).forEach((m) => {
                if (m && !machines.includes(m)) machines.push(m);
            });
            frappe.call({
                method: "timebridge.timebridge.api.create_device_users",
                args: {
                    user_id: values.user_id,
                    user_name: values.user_name,
                    machines: JSON.stringify(machines),
                    privilege: values.privilege,
                    card: values.card,
                    password: values.password,
                },
                freeze: true,
                callback(r) {
                    dialog.hide();
                    const failed = (r.message.results || []).filter((x) => !x.ok).length;
                    frappe.msgprint({
                        title: __("Add User"),
                        indicator: failed ? "orange" : "green",
                        message: (r.message.results || [])
                            .map((x) => `${x.machine}: ${x.ok ? __("ok") : (x.message || "")}`)
                            .join("<br>"),
                    });
                    frm.reload_doc();
                },
            });
        },
    });
    dialog.show();
}


/*
 * Attaching device users to TimeBridge Employees.
 *
 * The device gives a number and a name and nothing else, so this cannot be
 * automatic: a name matched to the wrong person moves their attendance onto
 * somebody else, silently. The whole plan is therefore shown first — who is
 * matched, who would be created, who is left out — and nothing is written until
 * it is confirmed.
 */
function employee_link_dialog(frm) {

    const dialog = new frappe.ui.Dialog({

        title: __("Create & Link TimeBridge Employees"),
        size: "large",

        fields: [
            {
                fieldname: "intro",
                fieldtype: "HTML",
                options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">` +
                    __("Attendance is built per TimeBridge Employee, so every device user needs one. Names are matched against existing TimeBridge Employees; the rest are created.") +
                    `</div>`
            },
            {
                fieldname: "date_of_joining",
                fieldtype: "Date",
                label: __("Date of Joining"),
                reqd: 1,
                default: frappe.datetime.get_today(),
                description: __("Required on TimeBridge Employee. The device does not know it, so the same date is used for everyone created here.")
            },
            {
                fieldname: "shift",
                fieldtype: "Link",
                label: __("TimeBridge Shift"),
                options: "TimeBridge Shift",
                description: __("Optional, but without it late and half-day cannot be worked out.")
            },
            { fieldname: "cb_org", fieldtype: "Column Break" },
            {
                fieldname: "organization",
                fieldtype: "Link",
                label: __("TimeBridge Organization"),
                options: "TimeBridge Organization",
                reqd: 1
            },
            {
                fieldname: "branch",
                fieldtype: "Link",
                label: __("TimeBridge Branch"),
                options: "TimeBridge Branch",
                reqd: 1
            },
            { fieldname: "sb_options", fieldtype: "Section Break" },
            {
                fieldname: "merge_same_name",
                fieldtype: "Check",
                label: __("Treat identical names as one person"),
                default: 1,
                description: __("One person often holds two enrolments on a device. Off, each device id becomes its own TimeBridge Employee and their day is split between them.")
            },
            {
                fieldname: "skip_non_person",
                fieldtype: "Check",
                label: __("Skip accounts that are not people"),
                default: 1,
                description: __("ADMIN and similar service accounts.")
            },
            { fieldname: "sb_plan", fieldtype: "Section Break" },
            { fieldname: "plan", fieldtype: "HTML" }
        ],

        primary_action_label: __("Create & Link"),

        primary_action(values) {

            dialog.get_primary_btn().prop("disabled", true).text(__("Working…"));

            frappe.call({

                method: "timebridge.timebridge.api.create_and_link_employees",

                args: {
                    machine_id: frm.doc.name,
                    date_of_joining: values.date_of_joining,
                    organization: values.organization,
                    branch: values.branch,
                    shift: values.shift || null,
                    merge_same_name: values.merge_same_name ? 1 : 0,
                    skip_non_person: values.skip_non_person ? 1 : 0
                },

                callback: function (r) {

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
                                  __("{0} could not be saved:", [failures.length]) + " " +
                                  frappe.utils.escape_html(failures.map(f => f.user_name).join(", ")) +
                                  `</div>`
                                : "") +
                            `<div style="margin-top:8px;">` +
                            __("Run <b>Rebuild Attendance</b> now to turn those punches into attendance.") +
                            `</div>`
                    });

                    frm.reload_doc();
                },

                error: function () {
                    dialog.get_primary_btn().prop("disabled", false).text(__("Create & Link"));
                }

            });

        }

    });

    // Both switches change what the plan would do, so the preview is re-read
    // rather than filtered in the browser — the server decides, in one place.
    const refresh_plan = () => load_employee_link_plan(frm, dialog);

    dialog.fields_dict.merge_same_name.$input.on("change", refresh_plan);
    dialog.fields_dict.skip_non_person.$input.on("change", refresh_plan);

    dialog.show();

    refresh_plan();
}


/*
 * Correcting TimeBridge Organization / TimeBridge Branch / TimeBridge Shift on people who already exist.
 *
 * The tempting shape for this was a "reset" on the linking dialog — unlink
 * everyone and run it again with different values. That does not work and is
 * not safe: re-linking matches the same TimeBridge Employees and never rewrites these
 * fields, and deleting them would take 2,000+ attendance rows and every punch's
 * employee with it. The field is what needs changing, so only the field changes.
 */
function employee_assignment_dialog(frm) {

    const dialog = new frappe.ui.Dialog({

        title: __("Update TimeBridge Organization / TimeBridge Shift"),

        fields: [
            {
                fieldname: "intro",
                fieldtype: "HTML",
                options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">` +
                    __("Changes these fields on the TimeBridge Employees already linked to this machine. Nothing is created, deleted or unlinked — punches and attendance are untouched.") +
                    `</div>`
            },
            { fieldname: "current", fieldtype: "HTML" },
            { fieldname: "sb_values", fieldtype: "Section Break" },
            {
                fieldname: "organization",
                fieldtype: "Link",
                label: __("TimeBridge Organization"),
                options: "TimeBridge Organization"
            },
            {
                fieldname: "branch",
                fieldtype: "Link",
                label: __("TimeBridge Branch"),
                options: "TimeBridge Branch"
            },
            { fieldname: "cb_values", fieldtype: "Column Break" },
            {
                fieldname: "shift",
                fieldtype: "Link",
                label: __("TimeBridge Shift"),
                options: "TimeBridge Shift",
                description: __("Changing this makes the stored late and half-day figures stale — rebuild afterwards.")
            },
            {
                fieldname: "note",
                fieldtype: "HTML",
                options: `<div style="font-size:12px;color:var(--text-muted);margin-top:8px;">` +
                    __("Leave a field empty to keep what is already there.") +
                    `</div>`
            }
        ],

        primary_action_label: __("Update"),

        primary_action(values) {

            if (!values.organization && !values.branch && !values.shift) {
                frappe.msgprint({
                    title: __("Nothing Chosen"),
                    indicator: "orange",
                    message: __("Pick at least one of TimeBridge Organization, TimeBridge Branch or TimeBridge Shift.")
                });
                return;
            }

            dialog.get_primary_btn().prop("disabled", true).text(__("Working…"));

            frappe.call({

                method: "timebridge.timebridge.api.update_employee_assignment",

                args: {
                    machine_id: frm.doc.name,
                    organization: values.organization || null,
                    branch: values.branch || null,
                    shift: values.shift || null
                },

                callback: function (r) {

                    const res = r.message || {};

                    dialog.hide();

                    frappe.msgprint({
                        title: __("TimeBridge Employees Updated"),
                        indicator: "green",
                        message:
                            `<div>${__("TimeBridge Employees on this machine")}: <b>${res.employees || 0}</b></div>` +
                            `<div>${__("Changed")}: <b>${res.changed || 0}</b></div>` +
                            (res.changed === 0
                                ? `<div style="margin-top:6px;color:var(--text-muted);">` +
                                  __("They already held those values.") + `</div>`
                                : "") +
                            (res.needs_rebuild
                                ? `<div class="alert alert-warning" style="margin-top:8px;padding:8px;">` +
                                  __("TimeBridge Shift changed. Run <b>Rebuild Attendance</b> — late and half-day were worked out from the old shift.") +
                                  `</div>`
                                : "")
                    });
                },

                error: function () {
                    dialog.get_primary_btn().prop("disabled", false).text(__("Update"));
                }

            });

        }

    });

    dialog.show();

    frappe.call({

        method: "timebridge.timebridge.api.employee_assignment_summary",
        args: { machine_id: frm.doc.name },

        callback: function (r) {

            const res = r.message || {};
            const $current = dialog.fields_dict.current.$wrapper;

            if (!res.employees) {

                $current.html(
                    `<div class="alert alert-info" style="font-size:12px;padding:8px;">` +
                    __("No TimeBridge Employees are linked to this machine yet. Use Create & Link TimeBridge Employees first.") +
                    `</div>`
                );

                dialog.get_primary_btn().prop("disabled", true);

                return;
            }

            const rows = (res.spread || []).map(function (row) {
                return `<tr>
                    <td>${frappe.utils.escape_html(row.organization_name || row.organization || "-")}</td>
                    <td>${frappe.utils.escape_html(row.branch_name || row.branch || "-")}</td>
                    <td>${frappe.utils.escape_html(row.shift_name || __("none"))}</td>
                    <td style="text-align:right"><b>${row.n}</b></td>
                </tr>`;
            }).join("");

            $current.html(`
                <div style="font-size:12px;margin-bottom:6px;">
                    ${__("{0} TimeBridge Employees are linked to this machine, and carry:", [res.employees])}
                </div>
                <table class="table table-sm" style="font-size:12px;margin:0;">
                    <thead><tr>
                        <th>${__("TimeBridge Organization")}</th>
                        <th>${__("TimeBridge Branch")}</th>
                        <th>${__("TimeBridge Shift")}</th>
                        <th style="text-align:right">${__("People")}</th>
                    </tr></thead>
                    <tbody>${rows}</tbody>
                </table>
                ${res.shared
                    ? `<div class="alert alert-warning" style="margin-top:8px;padding:8px;font-size:12px;">` +
                      __("{0} of them also punch on another machine and will be changed too.", [res.shared]) +
                      `</div>`
                    : ""}
            `);
        }

    });
}


function load_employee_link_plan(frm, dialog) {

    const $plan = dialog.fields_dict.plan.$wrapper;

    $plan.html(`<div style="font-size:12px;color:var(--text-muted)">${__("Working out the plan…")}</div>`);

    frappe.call({

        method: "timebridge.timebridge.api.preview_employee_link",

        args: {
            machine_id: frm.doc.name,
            merge_same_name: dialog.get_value("merge_same_name") ? 1 : 0,
            skip_non_person: dialog.get_value("skip_non_person") ? 1 : 0
        },

        callback: function (r) {

            const res = r.message || {};
            const counts = res.counts || {};
            const rows = res.rows || [];

            // Only fill these if untouched, so a re-read after flicking a
            // switch cannot overwrite what the operator has already chosen.
            const defaults = res.defaults || {};

            if (!dialog.get_value("organization") && defaults.organization) {
                dialog.set_value("organization", defaults.organization);
            }

            if (!dialog.get_value("branch") && defaults.branch) {
                dialog.set_value("branch", defaults.branch);
            }

            if (!dialog.get_value("shift") && defaults.shift) {
                dialog.set_value("shift", defaults.shift);
            }

            if (!rows.length) {

                // Saying only "nothing to do" invites the reader to change the
                // fields above and press again, which does nothing — those
                // fields only ever apply to people being created.
                $plan.html(
                    `<div class="alert alert-info" style="font-size:12px;padding:8px;">` +
                    (counts.already_linked
                        ? __("Every device user on this machine already has a TimeBridge Employee. To change their TimeBridge Organization, TimeBridge Branch or TimeBridge Shift, close this and use <b>Update TimeBridge Organization / TimeBridge Shift</b> — the fields above apply only to newly created TimeBridge Employees.")
                        : __("This machine has no device users yet. Fetch from the device first.")) +
                    `</div>`
                );

                dialog.get_primary_btn().prop("disabled", true);

                return;
            }

            dialog.get_primary_btn().prop("disabled", false);

            const summary = [
                `<b>${counts.create || 0}</b> ${__("to create")}`,
                `<b>${counts.link || 0}</b> ${__("matched to existing TimeBridge Employees")}`,
                `<b>${counts.already_linked || 0}</b> ${__("already linked")}`,
                `<b>${counts.skipped || 0}</b> ${__("skipped")}`
            ].join(" &middot; ");

            const body = rows.map(function (row) {

                const ids = frappe.utils.escape_html(row.user_ids.join(", "));
                const merged = row.user_ids.length > 1;

                return `<tr>
                    <td>${frappe.utils.escape_html(row.user_name || "")}</td>
                    <td>${ids}${merged ? ` <span style="color:var(--orange-600)">(${__("one person, {0} enrolments", [row.user_ids.length])})</span>` : ""}</td>
                    <td>${row.action === "link"
                        ? `<span style="color:var(--blue-600)">${__("link to")} ${frappe.utils.escape_html(row.employee)}</span>`
                        : `<span style="color:var(--green-600)">${__("create")}</span> <code>${frappe.utils.escape_html(row.employee_code)}</code>`}</td>
                </tr>`;

            }).join("");

            const skipped = (res.skipped || []).length
                ? `<div style="font-size:12px;color:var(--text-muted);margin-top:8px;">` +
                  __("Skipped") + ": " +
                  frappe.utils.escape_html(res.skipped.map(s => `${s.user_name} (${s.user_id})`).join(", ")) +
                  `</div>`
                : "";

            $plan.html(`
                <div style="font-size:12px;margin-bottom:8px;">${summary}</div>
                <div style="max-height:260px;overflow:auto;border:1px solid var(--border-color);border-radius:4px;">
                    <table class="table table-sm" style="font-size:12px;margin:0;">
                        <thead><tr>
                            <th>${__("Name on device")}</th>
                            <th>${__("Device ID")}</th>
                            <th>${__("Action")}</th>
                        </tr></thead>
                        <tbody>${body}</tbody>
                    </table>
                </div>
                ${skipped}
            `);
        },

        error: function () {
            $plan.html(`<div style="color:var(--red-500);font-size:12px;">${__("Could not read the plan.")}</div>`);
        }

    });
}


function rebuild_attendance_dialog(frm) {

    const dialog = new frappe.ui.Dialog({

        title: __("Rebuild Attendance"),

        fields: [
            {
                fieldname: "info",
                fieldtype: "HTML",
                options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">` +
                    __("Recalculates in/out times and hours from stored punches. Existing rows are updated, never duplicated — safe to run again.") +
                    `</div>`
            },
            {
                fieldname: "from_date",
                fieldtype: "Date",
                label: __("From Date"),
                description: __("Leave both dates empty to rebuild everything.")
            },
            {
                fieldname: "to_date",
                fieldtype: "Date",
                label: __("To Date")
            }
        ],

        primary_action_label: __("Rebuild"),

        primary_action(values) {

            dialog.get_primary_btn().prop("disabled", true).text(__("Working…"));

            frappe.call({

                method: "timebridge.timebridge.api.rebuild_attendance",
                args: {
                    from_date: values.from_date || null,
                    to_date: values.to_date || null
                },

                callback: function (r) {

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
                            __("Repeat punches within {0}s were counted once.", [res.duplicate_window || 0]) +
                            `</div>`
                    });

                },

                error: function () {
                    dialog.get_primary_btn().prop("disabled", false).text(__("Rebuild"));
                }

            });

        }

    });

    dialog.show();
}


function start_fetch_all(frm) {

    // The two transports make this button mean different things. A dialable
    // device is read here and now, so how far back to read is a real question
    // with a real cost — a full history can be tens of thousands of rows. A
    // push device is only asked to re-send and answers on its own timer, so
    // there is nothing to choose and asking would be noise.
    if ((frm.doc.sdk_type || "") === "ADMS") {
        start_push_fetch(frm);
        return;
    }

    const dialog = new frappe.ui.Dialog({

        title: __("Fetch From Device"),

        fields: [
            {
                fieldname: "info",
                fieldtype: "HTML",
                options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">` +
                    __("The device is read directly. It goes offline for a few seconds while its records are copied, so avoid doing this at a shift change.") +
                    `</div>`
            },
            {
                fieldname: "window",
                fieldtype: "Select",
                label: __("How far back"),
                default: "30",
                options: [
                    { value: "7", label: __("Last 7 days") },
                    { value: "30", label: __("Last 30 days") },
                    { value: "90", label: __("Last 90 days") },
                    { value: "0", label: __("Everything on the device") }
                ],
                description: __("Punches already stored are skipped, so a wider window costs time but never duplicates.")
            }
        ],

        primary_action_label: __("Fetch"),

        primary_action(values) {
            dialog.hide();
            start_pull_fetch(frm, cint(values.window));
        }

    });

    dialog.show();
}


function start_pull_fetch(frm, days) {

    const dialog = new frappe.ui.Dialog({
        title: __("Fetching From Device"),
        primary_action_label: __("Close"),
        primary_action: () => dialog.hide(),
        onhide: () => { if (timer) { clearInterval(timer); timer = null; } }
    });

    let timer = null;

    dialog.$body.html(`
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
            ${frappe.utils.escape_html(frm.doc.machine_name || frm.doc.name)}
            &middot; ${frappe.utils.escape_html(endpoint_label(frm))}
        </div>
        <div class="pf-note" style="font-size:13px;margin-bottom:6px;"></div>
        <div class="pf-detail" style="font-size:12px;color:var(--text-muted);"></div>
        <div class="pf-counts" style="font-size:12px;margin-top:10px;"></div>
        <div class="pf-hint alert alert-info hidden"
             style="margin-top:10px;font-size:12px;padding:8px;"></div>
    `);

    dialog.show();

    const $note = dialog.$body.find(".pf-note");
    const $detail = dialog.$body.find(".pf-detail");
    const $counts = dialog.$body.find(".pf-counts");
    const $hint = dialog.$body.find(".pf-hint");

    $note.html(__("Queuing…"));

    frappe.call({

        method: "timebridge.timebridge.api.request_all_data",
        args: { machine_id: frm.doc.name, days: days },

        callback: function (r) {

            const res = r.message || {};

            if (res.status !== "queued") {
                $note.html(`<b style="color:var(--red-500)">${frappe.utils.escape_html(res.message || __("Could not queue the fetch."))}</b>`);
                return;
            }

            // A machine whose SDK Type was changed while this form sat open
            // would otherwise be polled on the wrong channel and appear stuck.
            if (res.mode === "push") {
                dialog.hide();
                start_push_fetch(frm);
                return;
            }

            let waited = 0;

            $note.html(__("Waiting for a background worker…"));

            timer = setInterval(function () {

                waited += POLL_SECONDS;

                frappe.call({

                    method: "timebridge.timebridge.api.pull_sync_progress",
                    args: { machine_id: frm.doc.name },

                    callback: function (p) {

                        const st = p.message || {};

                        if (st.stage) {
                            $note.html(frappe.utils.escape_html(st.stage));
                        }

                        $detail.html(st.detail ? frappe.utils.escape_html(st.detail) : "");

                        if (st.status === "queued" && waited >= WORKER_PICKUP_SECONDS) {
                            $hint.removeClass("hidden").html(
                                __("No worker has picked this up yet. If it stays here, the background workers are not running — start the bench with <code>bench start</code>.")
                            );
                        } else if (st.status !== "queued") {
                            $hint.addClass("hidden");
                        }

                        if (st.status === "success") {

                            clearInterval(timer);
                            timer = null;

                            const punches = st.punches || {};
                            const users = st.users || {};

                            $note.html(`<b style="color:var(--green-500)">${__("Done.")}</b>`);
                            $detail.html("");

                            $counts.html(
                                `<div>${__("New punches")}: <b>${punches.created || 0}</b></div>` +
                                `<div>${__("Already stored")}: <b>${punches.duplicates || 0}</b></div>` +
                                `<div>${__("New users")}: <b>${users.created || 0}</b>` +
                                (users.updated ? ` (${users.updated} ${__("updated")})` : "") + `</div>` +
                                (punches.outside_window
                                    ? `<div style="color:var(--text-muted);margin-top:6px;">` +
                                      __("{0} punches on the device are older than the window you chose.", [punches.outside_window]) +
                                      `</div>`
                                    : "") +
                                (punches.unmatched
                                    ? `<div class="alert alert-warning" style="margin-top:8px;padding:8px;">` +
                                      __("{0} punches belong to device users with no TimeBridge Employee linked yet. Link them on the TimeBridge Machine User record and they will attach themselves.", [punches.unmatched]) +
                                      `</div>`
                                    : "") +
                                `<div style="margin-top:8px;">` +
                                __("Run <b>Rebuild Attendance</b> next to turn these punches into attendance.") +
                                `</div>`
                            );

                            frm.reload_doc();

                            return;
                        }

                        if (st.status === "failed") {

                            clearInterval(timer);
                            timer = null;

                            $note.html(`<b style="color:var(--red-500)">${__("Fetch failed")}</b>`);
                            $detail.html(frappe.utils.escape_html(st.message || ""));

                            frm.reload_doc();
                        }

                    }

                });

            }, POLL_SECONDS * 1000);

        },

        error: function () {
            $note.html(`<b style="color:var(--red-500)">${__("Could not reach the server.")}</b>`);
        }

    });
}


function start_push_fetch(frm) {

    const dialog = new frappe.ui.Dialog({
        title: __("Fetching From Device"),
        primary_action_label: __("Close"),
        primary_action: () => dialog.hide(),
        onhide: () => { if (timer) { clearInterval(timer); timer = null; } }
    });

    let timer = null;

    dialog.$body.html(`
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
            ${frappe.utils.escape_html(frm.doc.machine_name || frm.doc.name)}
            &middot; ${__("serial")} ${frappe.utils.escape_html(frm.doc.serial_number || "-")}
        </div>
        <div class="fa-note" style="font-size:13px;margin-bottom:10px;"></div>
        <div class="fa-counts" style="font-size:12px;"></div>
        <div class="fa-hint alert alert-info hidden"
             style="margin-top:10px;font-size:12px;padding:8px;"></div>
    `);

    dialog.show();

    const $note = dialog.$body.find(".fa-note");
    const $counts = dialog.$body.find(".fa-counts");
    const $hint = dialog.$body.find(".fa-hint");

    frappe.call({

        method: "timebridge.timebridge.api.request_all_data",
        args: { machine_id: frm.doc.name },

        callback: function (r) {

            const res = r.message || {};

            if (res.status !== "queued") {
                $note.html(`<b style="color:var(--red-500)">${frappe.utils.escape_html(res.message || __("Could not queue the request."))}</b>`);
                return;
            }

            const baseline = res.baseline || 0;
            const baseline_syncs = res.baseline_syncs || 0;
            let waited = 0;
            let answered = false;

            $note.html(__("Request sent. Waiting for the device to collect it…"));

            $hint.removeClass("hidden").html(
                __("The device checks in roughly every 30 seconds. It has to ask us before it can be told anything — we cannot call it.")
            );

            timer = setInterval(function () {

                waited += FETCH_POLL_SECONDS;

                frappe.call({

                    method: "timebridge.timebridge.api.fetch_status",
                    args: { machine_id: frm.doc.name },

                    callback: function (s) {

                        const st = s.message || {};
                        const gained = (st.punches || 0) - baseline;
                        const contact = st.last_contact || {};

                        // The device *replying* is the success condition, not
                        // the row count changing. Re-sending records we already
                        // hold is a correct answer that adds nothing.
                        const new_syncs = (st.sync_logs || 0) - baseline_syncs;

                        if (new_syncs > 0) {
                            answered = true;
                        }

                        let received = 0;
                        (st.recent_syncs || []).slice(0, new_syncs).forEach(function (row) {
                            received += (row.records_fetched || 0);
                        });

                        $counts.html(
                            `<div>${__("Punches stored")}: <b>${st.punches || 0}</b>` +
                            (gained > 0 ? ` <span style="color:var(--green-500)">(+${gained} ${__("new")})</span>` : "") + `</div>` +
                            `<div>${__("Users")}: <b>${st.users || 0}</b></div>` +
                            (answered
                                ? `<div style="margin-top:6px;">${__("Device sent")}: <b>${received}</b> ${__("records in this fetch")}</div>`
                                : "") +
                            `<div style="color:var(--text-muted);margin-top:6px;">` +
                            `${__("Device last spoke")}: ${contact.at ? frappe.utils.escape_html(contact.at) + " (" + frappe.utils.escape_html(contact.kind || "") + ")" : __("not since this page opened")}</div>` +
                            `<div style="color:var(--text-muted);">${__("Waiting")}: ${waited}s</div>`
                        );

                        if (st.pending_commands === 0 && !answered && waited >= FETCH_POLL_SECONDS) {
                            $note.html(__("Device collected the request. Waiting for its data…"));
                        }

                        if (answered) {

                            if (gained > 0) {
                                $note.html(`<b style="color:var(--green-500)">${__("Data arrived — {0} new punches.", [gained])}</b>`);
                                frm.reload_doc();
                            } else {
                                $note.html(`<b style="color:var(--green-500)">${__("Device answered. Everything it sent was already stored — nothing new to add.")}</b>`);
                            }

                            $hint.addClass("hidden");
                        }

                        if (waited >= FETCH_GIVE_UP_SECONDS) {

                            clearInterval(timer);
                            timer = null;

                            if (!answered) {
                                $note.html(`<b style="color:var(--orange-500)">${__("The device sent nothing in {0} seconds.", [FETCH_GIVE_UP_SECONDS])}</b>`);
                                $hint.removeClass("hidden").html(
                                    contact.at
                                        ? __("The device is talking to us, so the connection is fine — it simply had nothing to send for that period.")
                                        : __("The device never contacted us. Check that its Cloud Server address points at this PC, and that the network fixer has been run since the last restart.")
                                );
                            }
                        }

                    }

                });

            }, FETCH_POLL_SECONDS * 1000);

        },

        error: function () {
            $note.html(`<b style="color:var(--red-500)">${__("Could not reach the server.")}</b>`);
        }

    });

}


function start_connection_test(frm) {

    const progress = open_progress_dialog(frm);

    active_progress = progress;

    frappe.call({

        method: "timebridge.timebridge.api.get_device_info",

        args: {
            machine_id: frm.doc.name
        },

        // The endpoint only queues the read, so this callback fires long
        // before the device answers. Everything after this is polled.
        callback: function (r) {

            if (!r.message) {
                progress.fail(null, __("The server did not answer the request."));
                return;
            }

            progress.set_note(r.message.message);

            poll_progress(
                frm,
                progress,
                r.message.run_id,
                (r.message.timeout || 120) + WATCHDOG_GRACE_SECONDS
            );

        },

        error: function () {
            progress.fail(null, __("Could not reach the server."));
        }

    });

}


function poll_progress(frm, progress, run_id, budget_seconds) {
    /*
     * Ask the server where the job has got to, once a second.
     *
     * This deliberately does NOT use frappe.realtime. Frappe's socketio binds
     * IPv6 and WSL2 only forwards IPv4 listeners to Windows, so realtime
     * events never reach the browser on this setup — the job would run to
     * completion and the form would still show nothing. Polling rides on the
     * ordinary web port, which works.
     */

    let elapsed = 0;

    const timer = setInterval(function () {

        elapsed += POLL_SECONDS;

        if (elapsed > budget_seconds) {
            progress.fail(null, __("No answer after {0} seconds. The job may have been killed, or the worker is stuck.", [budget_seconds]));
            return;
        }

        frappe.call({

            method: "timebridge.timebridge.api.get_device_info_progress",
            args: { machine_id: frm.doc.name },

            callback: function (r) {

                const data = r.message || {};

                // A leftover result from an earlier click must never be shown
                // as the answer to this one.
                if (run_id && data.run_id && data.run_id !== run_id) {
                    return;
                }

                // Anything other than "queued" means the job ran. Recording
                // that here matters because a fast job — a push device answers
                // in milliseconds, without opening any connection — finishes
                // between two polls, so the client never sees a "progress"
                // update and would otherwise report "Did Not Start" about work
                // that had already completed.
                if (data.status && data.status !== "queued") {
                    progress.mark_ran();
                }

                if (data.status === "queued") {

                    if (elapsed >= WORKER_PICKUP_SECONDS) {
                        progress.warn_not_picked_up(WORKER_PICKUP_SECONDS);
                    }

                    return;
                }

                if (data.status === "progress") {
                    progress.advance(data);
                    return;
                }

                if (data.status === "success") {

                    if (data.is_push) {
                        progress.explain_push(data.message, data.machine_status, true);
                    } else {
                        progress.succeed(data);
                    }

                    frm.reload_doc();
                    return;
                }

                if (data.status === "failed") {

                    // A push device has no connection sequence, so the four
                    // pull steps would be four rows of dashes explaining
                    // nothing. Show the reason on its own instead.
                    if (data.is_push) {
                        progress.explain_push(data.message, data.machine_status, false);
                    } else {
                        progress.fail(data.failed_step, data.message, data.machine_status, data.reason);
                    }

                    frm.reload_doc();
                }

            }

        });

    }, POLL_SECONDS * 1000);

    progress.own_timer(timer);
}


function open_progress_dialog(frm) {

    const dialog = new frappe.ui.Dialog({
        title: __("Testing Connection"),
        primary_action_label: __("Close"),
        primary_action: () => dialog.hide(),

        // A job outlives a closed dialog. Without this, a late result would
        // be drawn into a hidden one and the user would see nothing at all.
        onhide: () => {
            // Stop polling the moment the dialog goes away, or it keeps
            // hitting the server once a second forever.
            clear_timers();

            if (active_progress === handle) {
                active_progress = null;
            }
        }
    });

    dialog.$body.html(progress_html(frm));
    dialog.show();

    // Held so the port search can close this one before opening the retry —
    // otherwise the failed dialog stays sitting behind the new one.
    frm.__tb_progress_dialog = dialog;

    // Nothing useful can be done mid-run, and a half-read device should not
    // be left behind by a stray click. Re-enabled when the job settles.
    dialog.get_primary_btn().prop("disabled", true);

    let poll_timer = null;
    let settled = false;

    // Did the worker ever report a single stage? If not, the run never
    // started at all, which is a completely different story from "it ran and
    // failed" — and showing four blank rows for it only confuses.
    let any_progress = false;

    const $body = dialog.$body;

    function clear_timers() {
        if (poll_timer) { clearInterval(poll_timer); poll_timer = null; }
    }

    function set_icon(step, state) {

        const $row = $body.find(`[data-step="${step}"]`);

        $row.attr("data-state", state);
        $row.find(".tb-icon").html(icon_for(state));
    }

    function show_machine_status(machine_status) {

        if (!machine_status) {
            return;
        }

        const colour = machine_status === "Connected" ? "green" : "red";

        $body.find(".tb-status")
            .removeClass("hidden")
            .html(
                __("Machine status set to") +
                ` <span class="indicator-pill ${colour}">${frappe.utils.escape_html(machine_status)}</span>`
            );
    }

    function settle(state) {

        settled = true;
        clear_timers();

        dialog.get_primary_btn().prop("disabled", false);

        // Nothing ever ran. A list of empty rows invites the reader to hunt
        // for a fault in steps that were never attempted, so replace it with
        // the one fact that matters and the one action that fixes it.
        if (state === "failed" && !any_progress) {

            dialog.set_title(__("Did Not Start"));

            $body.find(".tb-steps, .tb-note, .tb-warning, .tb-error").addClass("hidden");

            $body.find(".tb-blocked").removeClass("hidden").html(
                `<div style="font-weight:600;margin-bottom:6px;">` +
                __("The device was never contacted.") +
                `</div>` +
                `<div style="margin-bottom:8px;">` +
                __("This test never began, so nothing is known about the device yet — this is not a fault of the device or its settings.") +
                `</div>` +
                `<div>` +
                __("The background worker is busy with other work and never picked this up. Wait a minute and try again, or free up a worker.") +
                `</div>`
            );

            return;
        }

        dialog.set_title(
            state === "success" ? __("Connected") : __("Connection Failed")
        );

        // Mark anything still waiting as never reached, so the list does not
        // leave three grey rows looking like work that is still pending.
        $body.find('[data-state="pending"], [data-state="active"]').each(function () {

            const step = $(this).attr("data-step");

            if ($(this).attr("data-state") === "active" && state === "failed") {
                return;
            }

            set_icon(step, state === "success" ? "done" : "skipped");
        });
    }

    const handle = {

        set_note(text) {
            $body.find(".tb-note").text(text || "");
        },

        mark_ran() {
            // "Did Not Start" is only ever true when the job never ran at all.
            any_progress = true;
        },

        explain_push(message, machine_status, ok) {
            /*
             * A push device is never dialled, so there is no four-step
             * sequence to report. Showing one would invite the reader to hunt
             * for a fault in steps that do not exist for this kind of device.
             */

            any_progress = true;

            dialog.set_title(ok ? __("Device Is Sending") : __("Device Is Not Sending"));

            $body.find(".tb-steps, .tb-note, .tb-warning, .tb-error").addClass("hidden");

            $body.find(".tb-blocked")
                .removeClass("hidden")
                .removeClass("alert-warning")
                .addClass(ok ? "alert-success" : "alert-warning")
                .html(
                    `<div style="font-weight:600;margin-bottom:6px;">` +
                    (ok ? __("This device pushes its data to us, and it is doing so.")
                        : __("This device pushes its data to us — it cannot be dialled.")) +
                    `</div><div>${frappe.utils.escape_html(message || "")}</div>`
                );

            show_machine_status(machine_status);

            settled = true;
            clear_timers();
            dialog.get_primary_btn().prop("disabled", false);
        },

        own_timer(timer) {

            // Handed the polling interval so it can be stopped from one place:
            // whether the run settles, or the user closes the dialog first.
            poll_timer = timer;

            if (settled) {
                clear_timers();
            }
        },

        warn_not_picked_up(seconds) {

            if (settled || any_progress) {
                return;
            }

            $body.find(".tb-warning")
                .removeClass("hidden")
                .html(
                    __("No background worker has picked this up after {0} seconds.", [seconds]) +
                    "<br>" +
                    __("The job is queued but nothing is running it. Check that <code>bench start</code> is running — a bare <code>bench serve</code> has no workers.")
                );
        },

        advance(data) {

            // Any word from the worker means it exists, so the "nobody picked
            // this up" warning is no longer true.
            any_progress = true;

            $body.find(".tb-warning").addClass("hidden");

            this.set_note(
                data.detail ? `${data.stage} — ${data.detail}` : data.stage
            );

            if (!data.step) {
                return;
            }

            // Everything before the current step must have finished for it to
            // be running at all.
            STEPS.forEach(s => {
                if (s.step < data.step) {
                    set_icon(s.step, "done");
                }
            });

            set_icon(data.step, "active");

            if (data.detail) {
                $body.find(`[data-step="${data.step}"] .tb-detail`).text(data.detail);
            }
        },

        succeed(data) {

            STEPS.forEach(s => set_icon(s.step, "done"));

            this.set_note(data.message || __("Done"));

            show_machine_status(data.machine_status);

            const info = data.info || {};

            const rows = [
                [__("Serial number"), info.serial_number],
                [__("Device name"), info.device_name],
                [__("Firmware"), info.firmware_version],
                [__("Device time"), info.device_time],
                [__("Users"), info.user_count],
                [__("Records"), info.record_count]
            ].filter(row => row[1] !== undefined && row[1] !== null && row[1] !== "");

            if (rows.length) {

                $body.find(".tb-result").removeClass("hidden").html(
                    rows.map(
                        row => `<div class="tb-kv"><span>${frappe.utils.escape_html(String(row[0]))}</span>` +
                               `<b>${frappe.utils.escape_html(String(row[1]))}</b></div>`
                    ).join("")
                );
            }

            settle("success");
        },

        fail(step, message, machine_status, reason) {

            show_machine_status(machine_status);

            if (step) {
                set_icon(step, "failed");
            } else {
                // No step given: mark whatever was running as the casualty.
                const $active = $body.find('[data-state="active"]');
                if ($active.length) {
                    set_icon($active.attr("data-step"), "failed");
                }
            }

            this.set_note("");

            $body.find(".tb-error")
                .removeClass("hidden")
                .text(message || __("Unknown error"));

            settle("failed");

            // A rejected comm key is not a network fault: the port was open and
            // the device answered, it just refused us. Searching for a port
            // here would report "no port is open", which is untrue and sends
            // the reader off to restart a device that is behaving correctly.
            if (reason === "unauthenticated") {

                $body.find(".tb-blocked").removeClass("hidden").html(
                    `<div style="font-weight:600;margin-bottom:6px;">` +
                    __("The device refused the Communication Password.") +
                    `</div>` +
                    `<div>` +
                    __("Read the key off the device — <b>Menu → Comm → PC Connection</b> (called Comm Key or Security on some firmware) — and enter it in <b>Communication Password</b> here. Setting it to 0 on the device works too, as long as this field is 0 as well.") +
                    `</div>`
                );

                return;
            }

            // Only after the failure is already on screen. Finding the port is
            // an extra kindness, not part of the test — if it errors or finds
            // nothing, the dialog stays exactly as it was.
            offer_port_search(frm, $body);
        }

    };

    return handle;

}


function icon_for(state) {

    if (state === "done") {
        return '<span style="color:var(--green-500)">&#10003;</span>';
    }

    if (state === "failed") {
        return '<span style="color:var(--red-500)">&#10007;</span>';
    }

    if (state === "active") {
        return '<span class="tb-spin">&#9676;</span>';
    }

    if (state === "skipped") {
        return '<span style="color:var(--gray-400)">&ndash;</span>';
    }

    return '<span style="color:var(--gray-400)">&#9675;</span>';
}


function progress_html(frm) {

    const steps = STEPS.map(s => `
        <li data-step="${s.step}" data-state="pending"
            style="display:flex;align-items:baseline;gap:8px;padding:6px 0;">
            <span class="tb-icon" style="width:16px;text-align:center;">${icon_for("pending")}</span>
            <span class="tb-label">${s.label}</span>
            <span class="tb-detail" style="color:var(--text-muted);font-size:11px;"></span>
        </li>
    `).join("");

    return `
        <style>
            @keyframes tb-spin { to { transform: rotate(360deg); } }
            .tb-spin { display:inline-block; animation: tb-spin 1s linear infinite;
                       color: var(--blue-500); }
            .tb-kv { display:flex; justify-content:space-between; padding:3px 0;
                     border-bottom:1px solid var(--border-color); font-size:12px; }
        </style>

        <div style="font-size:12px;color:var(--text-muted);margin-bottom:4px;">
            ${frappe.utils.escape_html(frm.doc.machine_name || frm.doc.name)}
            &middot; ${frappe.utils.escape_html(endpoint_label(frm))}
        </div>

        <div class="tb-note" style="min-height:18px;font-size:12px;color:var(--text-color);"></div>

        <ul class="tb-steps" style="list-style:none;padding:0;margin:8px 0 0 0;">${steps}</ul>

        <div class="tb-blocked hidden alert alert-warning"
             style="margin-top:4px;font-size:12px;padding:10px;"></div>

        <div class="tb-warning hidden alert alert-warning"
             style="margin-top:10px;font-size:12px;padding:8px;"></div>

        <div class="tb-error hidden alert alert-danger"
             style="margin-top:10px;font-size:12px;padding:8px;white-space:pre-wrap;"></div>

        <div class="tb-status hidden" style="margin-top:10px;font-size:12px;"></div>

        <div class="tb-result hidden" style="margin-top:10px;"></div>
    `;
}


/**
 * A plain-language health panel at the top of the machine form.
 *
 * Exists so the question "is this working, and if not what do I do?" is
 * answered on the page. Everything here was previously only visible by
 * running commands in a terminal, which is not a reasonable thing to ask of
 * the person who just wants to know whether punches are arriving.
 */
function show_connection_health(frm) {

    frappe.call({

        method: "timebridge.timebridge.api.connection_health",
        args: { machine_id: frm.doc.name },

        callback: function (r) {

            const h = r.message;

            if (!h) {
                return;
            }

            frm.dashboard.clear_headline();
            frm.dashboard.set_headline(build_health_html(h), "blue");
        }

    });

}


function build_health_html(h) {

    const mins = h.minutes_since_contact;
    const port_label = h.web_port ? String(h.web_port) : __("your Frappe web port");

    // The device polls us every 30 seconds, so silence beyond a couple of
    // minutes is genuinely wrong rather than just quiet.
    let state, colour, headline, advice;

    if (mins === null || mins === undefined) {
        state = "silent";
        colour = "orange";
        headline = __("The device has never contacted us");
        advice = __(
            "On the device open <b>Menu → Comm → Cloud Server Setting</b> (or ADMS). " +
            "Set <b>Server Port</b> to <b>{0}</b>, turn <b>Enable Domain Name</b> and " +
            "<b>Enable Proxy Server</b> OFF, and point <b>Server Address</b> at the " +
            "host where this Frappe site is reachable from the device network.",
            [port_label]
        );

    } else if (mins > 5) {
        state = "stale";
        colour = "orange";
        headline = __("The device has gone quiet — last heard {0} minutes ago", [mins]);
        advice = __(
            "It normally checks in every 30 seconds on port <b>{0}</b>. " +
            "Check that the device can still reach this server — network, firewall, " +
            "or port forwarding may have changed since it last worked.",
            [port_label]
        );

    } else {
        state = "ok";
        colour = "green";
        headline = __("Connected — the device is sending on its own");
        advice = __("Nothing to do. New punches arrive by themselves; no button needs pressing.");
    }

    const icon = { ok: "&#10003;", stale: "!", silent: "?", down: "&#10007;" }[state];

    const rows = [
        [__("ADMS server port"), h.web_port || __("unknown")],
        [__("Device last spoke"),
         h.last_contact ? `${h.last_contact} (${h.last_contact_kind || ""})` : __("never")],
        [__("Serial number"), h.serial_number || `<span style="color:var(--red-500)">${__("not set — pushes cannot be matched")}</span>`],
        [__("Punches today"), h.punches_today],
        [__("Punches total"), h.punches_total],
        [__("TimeBridge Employees on device"), h.users],
    ];

    if (h.pending_commands) {
        rows.push([__("Waiting to be collected"), __("{0} request(s)", [h.pending_commands])]);
    }

    const table = rows.map(
        ([k, v]) => `<div style="display:flex;gap:8px;font-size:12px;padding:1px 0;">
            <span style="color:var(--text-muted);min-width:150px;">${k}</span>
            <b>${v}</b></div>`
    ).join("");

    return `
        <div style="padding:2px 0;">
            <div style="font-weight:600;margin-bottom:6px;">
                <span style="color:var(--${colour}-500);">${icon}</span> ${headline}
            </div>
            ${table}
            <div style="margin-top:8px;font-size:12px;color:var(--text-muted);line-height:1.5;">
                ${advice}
            </div>
        </div>
    `;
}


/**
 * Ask the device for enrolled photographs, and keep an eye on it while asking.
 *
 * Requesting photos means opening the FACE and UserPic switches in the
 * handshake, which some firmwares reject outright — and a rejected handshake
 * means no punches. So this watches whether the device is still checking in,
 * and closes those switches itself the moment it looks like it has stopped.
 * The punch feed is worth more than the pictures.
 */
function start_photo_fetch(frm) {

    const dialog = new frappe.ui.Dialog({
        title: __("Fetching Photos"),
        primary_action_label: __("Close"),
        primary_action: () => dialog.hide(),
        onhide: () => {
            if (timer) { clearInterval(timer); timer = null; }
            // Never leave the switches open once nobody is watching them.
            frappe.call({ method: "timebridge.timebridge.api.stop_photo_transfer" });
        }
    });

    let timer = null;

    dialog.$body.html(`
        <div style="font-size:12px;color:var(--text-muted);margin-bottom:8px;">
            ${frappe.utils.escape_html(frm.doc.machine_name || frm.doc.name)}
            &middot; ${__("serial")} ${frappe.utils.escape_html(frm.doc.serial_number || "-")}
        </div>
        <div class="pf-note" style="font-size:13px;margin-bottom:10px;"></div>
        <div class="pf-counts" style="font-size:12px;"></div>
        <div class="pf-hint alert alert-info hidden"
             style="margin-top:10px;font-size:12px;padding:8px;"></div>
    `);

    dialog.show();

    const $note = dialog.$body.find(".pf-note");
    const $counts = dialog.$body.find(".pf-counts");
    const $hint = dialog.$body.find(".pf-hint");

    frappe.call({

        method: "timebridge.timebridge.api.request_photos",
        args: { machine_id: frm.doc.name },

        callback: function (r) {

            const res = r.message || {};

            if (res.status !== "queued") {
                $note.html(`<b style="color:var(--red-500)">${frappe.utils.escape_html(res.message || __("Could not start."))}</b>`);
                return;
            }

            const baseline = res.baseline_photos || 0;
            let waited = 0;

            $note.html(__("Asked the device for photos. Waiting…"));
            $hint.removeClass("hidden").html(
                __("The device checks in about every 30 seconds. If it stops answering, the photo switches are closed again automatically so punches keep working.")
            );

            timer = setInterval(function () {

                waited += PHOTO_POLL_SECONDS;

                frappe.call({

                    method: "timebridge.timebridge.api.photo_fetch_status",
                    args: { machine_id: frm.doc.name },

                    callback: function (s) {

                        const st = s.message || {};
                        const gained = (st.photos || 0) - baseline;

                        $counts.html(
                            `<div>${__("Photos stored")}: <b>${st.photos || 0}</b>` +
                            (gained > 0 ? ` <span style="color:var(--green-500)">(+${gained})</span>` : "") + `</div>` +
                            `<div>${__("TimeBridge Employees with a photo")}: <b>${st.with_photo || 0}</b> / ${st.users || 0}</div>` +
                            `<div style="color:var(--text-muted);margin-top:6px;">` +
                            `${__("Device last spoke")}: ${st.last_contact || __("never")}</div>` +
                            (st.fetch_round
                                ? `<div style="color:var(--text-muted);">${__("Query form")}: ${st.fetch_round} / 3</div>`
                                : "") +
                            `<div style="color:var(--text-muted);">${__("Waiting")}: ${waited}s</div>`
                        );

                        // The device stopped answering — the switches have
                        // already been closed server-side; say so and stop.
                        if (st.reverted || (st.device_quiet && !st.photo_transfer_on)) {

                            clearInterval(timer);
                            timer = null;

                            $note.html(`<b style="color:var(--orange-500)">${__("The device went quiet — photo request cancelled.")}</b>`);
                            $hint.removeClass("hidden").html(
                                __("This firmware does not accept the photo switches. They have been closed again, so punches will resume on the next check-in. Nothing was lost.")
                            );
                            return;
                        }

                        if (gained > 0) {
                            $note.html(`<b style="color:var(--green-500)">${__("{0} photo(s) arrived.", [gained])}</b>`);
                            $hint.addClass("hidden");
                            frm.reload_doc();
                        }

                        if (waited >= PHOTO_GIVE_UP_SECONDS) {

                            clearInterval(timer);
                            timer = null;

                            frappe.call({ method: "timebridge.timebridge.api.stop_photo_transfer" });

                            if (gained === 0) {
                                $note.html(`<b style="color:var(--orange-500)">${__("No photos in {0} seconds.", [PHOTO_GIVE_UP_SECONDS])}</b>`);
                                $hint.removeClass("hidden").html(
                                    __("Three query forms were tried (bulk with tabs, bulk with commas, then one request per person). Daily punch snapshots are ignored on purpose. If this stays at zero, the firmware is not re-sending Bio-Photo over ADMS — use Upload Photos with files named like 3.jpg.")
                                );
                            }
                        }

                    }

                });

            }, PHOTO_POLL_SECONDS * 1000);

        },

        error: function () {
            $note.html(`<b style="color:var(--red-500)">${__("Could not reach the server.")}</b>`);
        }

    });

}


/**
 * Upload many photographs at once and attach each to the right person.
 *
 * Matching is done by filename on the server. The wait before matching exists
 * because FileUploader reports each file separately with no "all done" signal
 * — so the last upload resets a short timer, and matching runs once the
 * uploads have actually stopped rather than once per file.
 */
function start_photo_upload(frm) {

    frappe.msgprint({
        title: __("Naming The Files"),
        indicator: "blue",
        message:
            `<div style="font-size:13px;line-height:1.6">` +
            __("Name each photo after the person, then pick them all at once. Any of these work:") +
            `<ul style="margin:8px 0 8px 18px;padding:0;">
                <li><b>4.jpg</b> — ${__("the id on the device")}</li>
                <li><b>SHUBHANGI KAMBLE.jpg</b> — ${__("the name")}</li>
                <li><b>shubhangi_kamble.jpg</b> — ${__("spaces, dashes and underscores are ignored")}</li>
             </ul>` +
            __("Anything that cannot be matched is listed afterwards, and nothing is guessed at.") +
            `</div>`,
        primary_action: {
            label: __("Choose Photos"),
            action() {
                frappe.hide_msgprint();
                open_photo_uploader(frm);
            }
        }
    });

}


function open_photo_uploader(frm) {

    const uploaded = [];
    let settle_timer = null;

    new frappe.ui.FileUploader({

        doctype: "TimeBridge Machine",
        docname: frm.doc.name,
        folder: "Home/Attachments",
        restrictions: {
            allowed_file_types: ["image/*"]
        },

        on_success(file_doc) {

            // The record name, not the url: identical pictures share a url, and the
            // server would then attach the wrong one.
            uploaded.push(file_doc.name);

            // FileUploader gives no "everything finished" callback, so wait
            // for a gap in the uploads instead of matching after each one.
            if (settle_timer) {
                clearTimeout(settle_timer);
            }

            settle_timer = setTimeout(() => match_uploaded_photos(frm, uploaded), 1200);
        }

    });

}


function match_uploaded_photos(frm, file_urls) {

    if (!file_urls.length) {
        return;
    }

    frappe.call({

        method: "timebridge.timebridge.api.match_photos",
        args: {
            machine_id: frm.doc.name,
            file_urls: JSON.stringify(file_urls)
        },
        freeze: true,
        freeze_message: __("Matching photos to people…"),

        callback: function (r) {

            const res = r.message || {};
            const matched = res.matched || [];
            const unmatched = res.unmatched || [];

            let html = `<div style="font-size:13px">`;

            html += `<div style="margin-bottom:8px;">` +
                __("Matched {0} of {1}. {2} of {3} people now have a photo.",
                   [matched.length, res.total || 0, res.with_photo || 0, res.users || 0]) +
                `</div>`;

            if (matched.length) {
                html += `<div style="margin-top:10px;font-weight:600;color:var(--green-600)">${__("Attached")}</div>`;
                html += matched.map(m =>
                    `<div style="font-size:12px;padding:1px 0;">${frappe.utils.escape_html(m.file)}
                     &rarr; <b>${frappe.utils.escape_html(m.user_name)}</b></div>`
                ).join("");
            }

            if (unmatched.length) {
                html += `<div style="margin-top:12px;font-weight:600;color:var(--orange-500)">${__("Could not match")}</div>`;
                html += unmatched.map(f =>
                    `<div style="font-size:12px;padding:1px 0;">${frappe.utils.escape_html(f)}</div>`
                ).join("");
                html += `<div style="margin-top:8px;font-size:12px;color:var(--text-muted)">` +
                    __("Rename these to the person's device id or name and upload again. They are still attached to this machine, so nothing is lost.") +
                    `</div>`;
            }

            html += `</div>`;

            frappe.msgprint({
                title: unmatched.length ? __("Photos Uploaded — Some Unmatched") : __("Photos Uploaded"),
                indicator: unmatched.length ? "orange" : "green",
                message: html
            });

            frm.reload_doc();
        }

    });

}


/**
 * When the test fails, go and look for the port ourselves.
 *
 * "Connection refused" tells the user the configured port did not answer and
 * stops there, which is where the guessing used to start — was the address
 * wrong, was the device off, or was it sitting right there on another port?
 * Finding out meant someone running probes at a terminal.
 *
 * So the dialog now does that itself, and says which of the three it is. It
 * runs only after a failure has already been drawn, so a successful test is
 * untouched, and any error here leaves the dialog exactly as it was.
 */
function offer_port_search(frm, $body) {

    if (!frm.doc.ip_address || $body.find(".tb-portscan").length) {
        return;
    }

    const $panel = $(`
        <div class="tb-portscan" style="margin-top:10px;padding-top:10px;
             border-top:1px solid var(--border-color);font-size:12px;">
            <div class="tb-portscan-msg" style="color:var(--text-muted)">
                ${__("Looking for the right port…")}
            </div>
        </div>
    `).appendTo($body);

    frappe.call({

        method: "timebridge.timebridge.api.find_device_port",
        args: { machine_id: frm.doc.name },

        callback: function (r) {

            const res = r.message || {};

            if (!res.checked) {
                $panel.remove();
                return;
            }

            // The device is there and talking on another port. This is the
            // only case worth a button, because it is the only one where we
            // know what to change.
            if (res.suggestion) {

                $panel.find(".tb-portscan-msg").html(`
                    <div style="color:var(--green-600);font-weight:600;margin-bottom:2px">
                        ${__("Found it — the device answers on port {0}.", [res.suggestion])}
                    </div>
                    <div>${__("It is listening, just not on {0}.", [res.configured_port])}</div>
                `);

                $(`<button class="btn btn-xs btn-primary" style="margin-top:8px">
                       ${__("Use {0} and test again", [res.suggestion])}
                   </button>`)
                    .appendTo($panel)
                    .on("click", function () {

                        $(this).prop("disabled", true).text(__("Saving…"));

                        // Saved rather than set quietly: the port is part of
                        // the record, and a change nobody can see later is a
                        // change nobody can undo.
                        frm.set_value("port", res.suggestion);

                        frm.save().then(() => {
                            frm.__tb_progress_dialog && frm.__tb_progress_dialog.hide();
                            start_connection_test(frm);
                        });
                    });

                return;
            }

            // Something answered — a refusal counts — so the address is right
            // and the device has power. Nothing is serving, which on these
            // terminals is almost always a restart away.
            if (res.reachable) {

                $panel.find(".tb-portscan-msg").html(`
                    <div style="color:var(--orange-600);font-weight:600;margin-bottom:2px">
                        ${__("The device is awake, but no port is open.")}
                    </div>
                    <div>${__("Switch it off and on — network settings only take effect after a restart.")}</div>
                `);

                return;
            }

            $panel.find(".tb-portscan-msg").html(`
                <div style="color:var(--red-500);font-weight:600;margin-bottom:2px">
                    ${__("Nothing answered at {0}.", [res.ip_address])}
                </div>
                <div>${__("Either the address is wrong, or the device is on a different network from this server.")}</div>
            `);
        },

        error: function () {
            $panel.remove();
        }

    });
}


// A punch is answered within a second or two, so there is no point asking
// more often than this — and a session can be left open for a long while.
const COLLECT_POLL_SECONDS = 3;


/**
 * Watch photographs arrive, one person at a time.
 *
 * This collects nothing itself. Pictures come because people punch and the
 * device is set to photograph them; all that was missing was somewhere to see
 * how far along it is. Without that the job has no end — you cannot tell who
 * is still outstanding, or when to switch the camera back off.
 */
function start_photo_collection(frm) {

    let timer = null;

    const dialog = new frappe.ui.Dialog({
        title: __("Collect Photos"),
        size: "large",
        primary_action_label: __("Close"),
        primary_action: () => dialog.hide(),
        // Collection is passive, so closing costs nothing — photographs keep
        // arriving, they simply stop being watched.
        onhide: () => { if (timer) { clearInterval(timer); timer = null; } }
    });

    dialog.$body.html(`
        <div style="font-size:13px;margin-bottom:10px;">
            ${__("Have everyone punch once. Each photograph appears here as it arrives.")}
        </div>
        <div class="pc-bar-wrap" style="background:var(--gray-200);border-radius:6px;
             height:8px;overflow:hidden;margin-bottom:6px;">
            <div class="pc-bar" style="height:100%;width:0;background:var(--green-500);
                 transition:width .3s;"></div>
        </div>
        <div class="pc-count" style="font-size:12px;color:var(--text-muted);
             margin-bottom:12px;">&nbsp;</div>
        <div class="pc-lists" style="display:flex;gap:18px;"></div>
        <div class="pc-hint" style="margin-top:12px;padding-top:10px;
             border-top:1px solid var(--border-color);font-size:11.5px;
             color:var(--text-muted);">
            ${__("No photographs arriving? Check Camera Mode on the device — it must be set to save a photo.")}
        </div>
    `);

    dialog.show();

    function render(status) {

        const done = status.done || [];
        const pending = status.pending || [];
        const total = status.total || 0;

        const pct = total ? Math.round((done.length / total) * 100) : 0;

        dialog.$body.find(".pc-bar").css("width", pct + "%");
        dialog.$body.find(".pc-count").text(
            __("{0} of {1} collected", [done.length, total])
        );

        // The retake mark sits beside a finished name rather than in a menu:
        // the moment you notice a bad photograph is the moment you are looking
        // at this list.
        const done_rows = done.map(p => `
            <li style="display:flex;align-items:center;gap:6px;padding:3px 0;">
                <span style="color:var(--green-600)">&#10003;</span>
                <span style="flex:1">${frappe.utils.escape_html(p.name)}</span>
                <span class="pc-retake" data-mu="${p.machine_user}"
                      title="${__("Take a new photo on the next punch")}"
                      style="cursor:pointer;color:var(--text-muted);">&#8635;</span>
            </li>`).join("");

        const pending_rows = pending.map(p => `
            <li style="display:flex;align-items:center;gap:6px;padding:3px 0;
                       color:var(--text-muted)">
                <span>&#9675;</span>
                <span>${frappe.utils.escape_html(p.name)}</span>
                ${p.retaking ? `<span style="font-size:10px;color:var(--orange-600)">
                    ${__("retaking")}</span>` : ""}
            </li>`).join("");

        dialog.$body.find(".pc-lists").html(`
            <div style="flex:1">
                <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;
                     color:var(--text-muted);margin-bottom:4px;">
                    ${__("Collected")} (${done.length})
                </div>
                <ul style="list-style:none;padding:0;margin:0;font-size:12.5px;">
                    ${done_rows || `<li style="color:var(--text-muted)">—</li>`}
                </ul>
            </div>
            <div style="flex:1">
                <div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;
                     color:var(--text-muted);margin-bottom:4px;">
                    ${__("Still to come")} (${pending.length})
                </div>
                <ul style="list-style:none;padding:0;margin:0;font-size:12.5px;">
                    ${pending_rows || `<li style="color:var(--text-muted)">—</li>`}
                </ul>
            </div>
        `);

        if (status.finished) {

            if (timer) { clearInterval(timer); timer = null; }

            dialog.$body.find(".pc-hint").html(`
                <div style="color:var(--green-600);font-weight:600;">
                    ${__("Everyone has a photograph.")}
                </div>
                <div>${__("Set Camera Mode back to “No photo” on the device, so it stops filling its own memory.")}</div>
            `);
        }
    }

    function poll(method) {

        frappe.call({
            method: "timebridge.timebridge.api." + method,
            args: { machine_id: frm.doc.name },
            callback: (r) => r.message && render(r.message),
            // A single failed poll is not worth interrupting a session that
            // may be left open for an hour; the next one will report.
            error: () => {}
        });
    }

    dialog.$body.on("click", ".pc-retake", function () {

        const machine_user = $(this).attr("data-mu");

        frappe.call({
            method: "timebridge.timebridge.api.request_photo_retake",
            args: { machine_user: machine_user },
            callback: () => {
                // Restart the watch: a finished session stopped polling, and
                // a retake gives it something to wait for again.
                if (!timer) {
                    timer = setInterval(() => poll("photo_collection_status"),
                                        COLLECT_POLL_SECONDS * 1000);
                }
                poll("photo_collection_status");
            }
        });
    });

    // The first call also opens the transfer switch, without which the device
    // is not permitted to send pictures at all.
    poll("start_photo_collection");

    timer = setInterval(() => poll("photo_collection_status"),
                        COLLECT_POLL_SECONDS * 1000);
}
