# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Upsert the TimeBridge Machine Status Custom HTML Block.

Custom HTML Block is a Desk DocType with no app module / is_standard export,
so workspace JSON alone cannot create it. Call sync_machine_status_block() from
after_install and post_model_sync patches before syncing the workspace.
"""

import frappe

BLOCK_NAME = "TimeBridge Machine Status"

BLOCK_HTML = """
<div class="tb-ms">
	<div class="tb-ms-head">
		<span class="tb-ms-title">Machine Status</span>
		<span class="tb-ms-meta" data-role="meta"></span>
	</div>
	<div class="tb-ms-empty" data-role="empty" hidden>No machines yet.</div>
	<div class="tb-ms-loading" data-role="loading">Loading…</div>
	<div class="tb-ms-table-wrap" data-role="table-wrap" hidden>
		<table class="tb-ms-table">
			<thead>
				<tr>
					<th>Machine</th>
					<th>Status</th>
					<th>Last sync</th>
					<th>Sync type</th>
				</tr>
			</thead>
			<tbody data-role="tbody"></tbody>
		</table>
	</div>
</div>
"""

BLOCK_STYLE = """
.tb-ms { font-size: var(--text-sm, 13px); color: var(--text-color); }
.tb-ms-head {
	display: flex;
	align-items: baseline;
	justify-content: space-between;
	gap: 12px;
	margin-bottom: 10px;
}
.tb-ms-title { font-weight: 600; font-size: var(--text-base, 14px); }
.tb-ms-meta { color: var(--text-muted); font-size: var(--text-xs, 12px); }
.tb-ms-empty, .tb-ms-loading { color: var(--text-muted); padding: 8px 0; }
.tb-ms-table-wrap { overflow-x: auto; }
.tb-ms-table {
	width: 100%;
	border-collapse: collapse;
}
.tb-ms-table th,
.tb-ms-table td {
	text-align: left;
	padding: 8px 10px;
	border-bottom: 1px solid var(--border-color);
	white-space: nowrap;
}
.tb-ms-table th {
	color: var(--text-muted);
	font-weight: 500;
	font-size: var(--text-xs, 12px);
	text-transform: uppercase;
	letter-spacing: 0.02em;
}
.tb-ms-table a {
	color: var(--text-color);
	text-decoration: none;
	font-weight: 500;
}
.tb-ms-table a:hover { color: var(--primary); text-decoration: underline; }
.tb-ms-pill {
	display: inline-block;
	padding: 2px 8px;
	border-radius: 999px;
	font-size: var(--text-xs, 12px);
	font-weight: 500;
	line-height: 1.4;
}
.tb-ms-pill.connected {
	background: var(--green-100, #e4f5e9);
	color: var(--green-700, #2e7d32);
}
.tb-ms-pill.disconnected {
	background: var(--red-100, #fde8e8);
	color: var(--red-700, #c62828);
}
.tb-ms-muted { color: var(--text-muted); }
"""

BLOCK_SCRIPT = """
(function () {
	const loading = root_element.querySelector('[data-role="loading"]');
	const empty = root_element.querySelector('[data-role="empty"]');
	const wrap = root_element.querySelector('[data-role="table-wrap"]');
	const tbody = root_element.querySelector('[data-role="tbody"]');
	const meta = root_element.querySelector('[data-role="meta"]');
	const REFRESH_MS = 30000;
	let timer = null;

	function esc(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	function pill(status) {
		const cls = status === "Connected" ? "connected" : "disconnected";
		return `<span class="tb-ms-pill ${cls}">${esc(status || "Disconnected")}</span>`;
	}

	function render(machines) {
		loading.hidden = true;
		if (!machines || !machines.length) {
			empty.hidden = false;
			wrap.hidden = true;
			meta.textContent = "";
			return;
		}
		empty.hidden = true;
		wrap.hidden = false;
		const connected = machines.filter((m) => m.status === "Connected").length;
		meta.textContent = `${connected} connected · ${machines.length} total`;
		tbody.innerHTML = machines
			.map((m) => {
				const href = `/app/timebridge-machine/${encodeURIComponent(m.name)}`;
				const when = m.last_contact_at || "—";
				const kind = m.last_contact_kind || "—";
				return (
					`<tr>` +
					`<td><a href="${href}">${esc(m.machine_name)}</a></td>` +
					`<td>${pill(m.status)}</td>` +
					`<td class="tb-ms-muted">${esc(when)}</td>` +
					`<td>${esc(kind)}</td>` +
					`</tr>`
				);
			})
			.join("");
	}

	function load() {
		frappe.call({
			method: "timebridge.timebridge.services.device_status.get_machine_status_board",
			callback: function (r) {
				render((r.message && r.message.machines) || []);
			},
			error: function () {
				loading.hidden = true;
				empty.hidden = false;
				empty.textContent = "Could not load machine status.";
				wrap.hidden = true;
			},
		});
	}

	load();
	timer = setInterval(load, REFRESH_MS);
	document.addEventListener("visibilitychange", function () {
		if (document.hidden) {
			if (timer) {
				clearInterval(timer);
				timer = null;
			}
		} else if (!timer) {
			load();
			timer = setInterval(load, REFRESH_MS);
		}
	});
})();
"""


def sync_machine_status_block():
	"""Create or update the public Custom HTML Block used on the workspace."""

	values = {
		"doctype": "Custom HTML Block",
		"name": BLOCK_NAME,
		"private": 0,
		"html": BLOCK_HTML.strip(),
		"style": BLOCK_STYLE.strip(),
		"script": BLOCK_SCRIPT.strip(),
	}

	if frappe.db.exists("Custom HTML Block", BLOCK_NAME):
		doc = frappe.get_doc("Custom HTML Block", BLOCK_NAME)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		frappe.get_doc(values).insert(ignore_permissions=True)

	frappe.db.commit()
	return BLOCK_NAME


def delete_machine_status_block():
	if frappe.db.exists("Custom HTML Block", BLOCK_NAME):
		frappe.delete_doc("Custom HTML Block", BLOCK_NAME, force=True, ignore_permissions=True)
