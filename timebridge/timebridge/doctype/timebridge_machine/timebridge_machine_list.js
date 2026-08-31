// Copyright (c) 2026, UPGO and contributors
// For license information, please see license.txt

frappe.listview_settings["TimeBridge Machine"] = {

    onload(listview) {

        const actions = [
            ["Test Connection", "test_connection"],
            ["Fetch All Data", "fetch_all_data"],
            ["Fetch Photos", "fetch_photos"],
        ];

        actions.forEach(([label, action]) => {
            listview.page.add_actions_menu_item(
                __(label),
                () => run_on_selected(listview, action, label),
                false
            );
        });

        listview.page.set_primary_action(__("Add Machine"), () => {
            frappe.set_route("add-machine");
        });

    },

};


function run_on_selected(listview, action, label) {

    const machines = listview.get_checked_items(true);

    if (!machines.length) {
        frappe.msgprint({
            title: __("Nothing Selected"),
            message: __("Tick the machines you want this to run on."),
            indicator: "orange"
        });
        return;
    }

    frappe.call({

        method: "timebridge.timebridge.api.bulk_device_action",
        args: { action: action, machines: JSON.stringify(machines) },
        freeze: true,
        freeze_message: __("Working on {0} machine(s)…", [machines.length]),

        callback(r) {

            const results = (r.message || {}).results || [];

            const rows = results.map(row => {

                const ok = row.ok;
                const icon = ok ? "&#10003;" : "&#10007;";
                const colour = ok ? "var(--green-500)" : "var(--red-500)";
                const people = row.people_today
                    ? __("{0} people punched today", [row.people_today])
                    : __("no punches today");

                return `
                    <div style="display:flex;gap:10px;align-items:baseline;padding:4px 0;
                                border-bottom:1px solid var(--border-color);font-size:12px;">
                        <span style="color:${colour};width:14px;">${icon}</span>
                        <b style="min-width:150px;">${frappe.utils.escape_html(row.machine_name || row.machine)}</b>
                        <span style="min-width:150px;color:var(--text-muted);">${people}</span>
                        <span>${frappe.utils.escape_html(row.message || "")}</span>
                    </div>`;
            }).join("");

            const failed = results.filter(row => !row.ok).length;

            frappe.msgprint({
                title: `${__(label)} — ${__("{0} machine(s)", [results.length])}`,
                indicator: failed ? "orange" : "green",
                message: `<div>${rows}</div>`,
                wide: true
            });

        }

    });

}
