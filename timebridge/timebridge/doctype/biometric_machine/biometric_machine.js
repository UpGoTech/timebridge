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
const PHOTO_GIVE_UP_SECONDS = 180;
const FETCH_GIVE_UP_SECONDS = 120;

// Only one progress dialog is meaningful at a time. Held here so a dialog
// closed mid-run can stop its own polling.
let active_progress = null;


frappe.ui.form.on("Biometric Machine", {

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

        // The device cannot be pulled from, so this is the action that
        // actually brings data in: it asks the device to upload again, and
        // waits for it to arrive.
        frm.add_custom_button(__("Fetch All Data"), needs_saved(start_fetch_all), DEVICE);

        // Punches are only timestamps until this runs. Normally the scheduler
        // handles it, but a manual rebuild is needed after a bulk fetch of
        // history, which arrives all at once and outside the recent window.
        frm.add_custom_button(__("Rebuild Attendance"), needs_saved(rebuild_attendance_dialog), DEVICE);

        frm.add_custom_button(__("Fetch Photos"), needs_saved(start_photo_fetch), PHOTOS);

        // The device cannot supply photographs, so this is the path that
        // actually works: upload them once, named after the person, and let
        // the server do the matching.
        frm.add_custom_button(__("Upload Photos"), needs_saved(start_photo_upload), PHOTOS);

    }

});


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
                        progress.fail(data.failed_step, data.message, data.machine_status);
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

        fail(step, message, machine_status) {

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
            &middot; ${frappe.utils.escape_html(frm.doc.ip_address || "")}:${frappe.utils.escape_html(String(frm.doc.port || ""))}
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

    // The device polls us every 30 seconds, so silence beyond a couple of
    // minutes is genuinely wrong rather than just quiet.
    let state, colour, headline, advice;

    if (!h.receiver_ok) {
        state = "down";
        colour = "red";
        headline = __("The app itself is not listening");
        advice = __("Frappe is not serving on port 8000. Run <code>bench start</code> in the WSL terminal.");

    } else if (mins === null || mins === undefined) {
        state = "silent";
        colour = "orange";
        headline = __("The device has never contacted us");
        advice = __("Enter the server address on the device: <b>Menu → Comm → Cloud Server Setting</b>, with Enable Domain Name and Enable Proxy Server both OFF. If it is already set, run <b>Fix TimeBridge Network.bat</b> on the Desktop — the WSL address changes on every restart.");

    } else if (mins > 5) {
        state = "stale";
        colour = "orange";
        headline = __("The device has gone quiet — last heard {0} minutes ago", [mins]);
        advice = __("It normally checks in every 30 seconds. Usually the PC restarted and the forwarding broke: run <b>Fix TimeBridge Network.bat</b> on the Desktop.");

    } else {
        state = "ok";
        colour = "green";
        headline = __("Connected — the device is sending on its own");
        advice = __("Nothing to do. New punches arrive by themselves; no button needs pressing.");
    }

    const icon = { ok: "&#10003;", stale: "!", silent: "?", down: "&#10007;" }[state];

    const rows = [
        [__("Device last spoke"),
         h.last_contact ? `${h.last_contact} (${h.last_contact_kind || ""})` : __("never")],
        [__("Serial number"), h.serial_number || `<span style="color:var(--red-500)">${__("not set — pushes cannot be matched")}</span>`],
        [__("Punches today"), h.punches_today],
        [__("Punches total"), h.punches_total],
        [__("Employees on device"), h.users],
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
                            `<div>${__("Employees with a photo")}: <b>${st.with_photo || 0}</b> / ${st.users || 0}</div>` +
                            `<div style="color:var(--text-muted);margin-top:6px;">` +
                            `${__("Device last spoke")}: ${st.last_contact || __("never")}</div>` +
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
                                    __("The device kept talking to us but sent no pictures — it most likely stores only the face template, not a photograph. Look for an option like Save Photo or Attendance Photo in the device menu. Until then, photos can be attached by hand on each Machine User or Employee.")
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

        doctype: "Biometric Machine",
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
