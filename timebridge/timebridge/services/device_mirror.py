# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Device Mirror verify orchestration — compare device inventory vs server counts.
"""

import json

import frappe

from frappe.utils import add_days, cint, get_datetime, now_datetime, time_diff_in_seconds

from timebridge.timebridge.adms import commands
from timebridge.timebridge.services.biometric_templates import count_all_template_types
from timebridge.timebridge.services.connection import get_connector, is_push_device

MIRROR_PROGRESS_TTL = 3600
MIRROR_QUIET_SECONDS = 90

ASSET_KEYS = ("users", "punches", "photos", "fingerprints", "faces")


def progress_key(machine):
	return f"timebridge_mirror_verify::{machine}"


def set_progress(machine, payload):
	frappe.cache().set_value(progress_key(machine), payload, expires_in_sec=MIRROR_PROGRESS_TTL)


def get_progress(machine):
	return frappe.cache().get_value(progress_key(machine)) or {}


def default_window_days():
	return cint(
		frappe.db.get_single_value("TimeBridge Settings", "mirror_default_window_days")
	) or 45


def window_bounds(days, end=None):
	"""Return (start_date, end_date, start_dt, end_dt) for punch window."""

	end_dt = get_datetime(end) if end else now_datetime()
	days = cint(days)

	if days <= 0:
		start_dt = get_datetime("2000-01-01 00:00:00")
	else:
		start_dt = get_datetime(add_days(end_dt, -days).strftime("%Y-%m-%d 00:00:00"))

	end_dt = get_datetime(end_dt.strftime("%Y-%m-%d 23:59:59"))

	return start_dt.date(), end_dt.date(), start_dt, end_dt


def compute_server_counts(machine, window_start, window_end):
	"""Live server-side inventory counts."""

	template_counts = count_all_template_types(machine)

	photos = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabTimeBridge Machine User`
		WHERE machine = %s AND photo IS NOT NULL AND photo != ''
		""",
		machine,
	)[0][0]

	punches = frappe.db.sql(
		"""
		SELECT COUNT(*) FROM `tabTimeBridge Punch Log`
		WHERE machine = %s AND DATE(timestamp) BETWEEN %s AND %s
		""",
		(machine, window_start, window_end),
	)[0][0]

	return {
		"users": frappe.db.count("TimeBridge Machine User", {"machine": machine}),
		"punches": cint(punches),
		"photos": cint(photos),
		"fingerprints": template_counts["fingerprints"],
		"faces": template_counts["faces"],
	}


def compute_asset_status(device_count, server_count):
	"""
	Per-asset parity status.

	device_count None means we could not read the device.
	"""

	if device_count is None:
		return "Not mirrored", None

	device_count = cint(device_count)
	server_count = cint(server_count)
	delta = device_count - server_count

	if device_count == server_count:
		return "In sync", delta

	if device_count > server_count:
		return "Drift", delta

	return "Ahead", delta


def compute_overall_status(asset_statuses, verified_at=None, stale_hours=None):
	"""
	Worst actionable status: Drift > Stale > Unknown > In sync.
	Ahead alone does not downgrade overall.
	"""

	if stale_hours is None:
		stale_hours = cint(
			frappe.db.get_single_value("TimeBridge Settings", "mirror_stale_hours")
		) or 48

	statuses = [row.get("status") for row in (asset_statuses or {}).values()]

	if "Drift" in statuses:
		return "Drift"

	if verified_at:
		age_hours = time_diff_in_seconds(now_datetime(), get_datetime(verified_at)) / 3600
		if age_hours > stale_hours:
			return "Stale"

	if all(s in ("Unknown", "Not mirrored") for s in statuses):
		return "Unknown"

	if "Error" in statuses:
		return "Error"

	if all(s in ("In sync", "Ahead", "Unknown", "Not mirrored") for s in statuses):
		if any(s == "In sync" for s in statuses):
			return "In sync"

	return "Unknown"


def build_asset_status(device_counts, server_counts):
	"""Build per-asset status dict with counts and delta."""

	result = {}

	for key in ASSET_KEYS:
		device_val = (device_counts or {}).get(key)
		server_val = (server_counts or {}).get(key, 0)
		status, delta = compute_asset_status(device_val, server_val)

		result[key] = {
			"device": device_val,
			"server": server_val,
			"delta": delta,
			"status": status,
		}

	return result


def latest_snapshot(machine):
	"""Most recent Device Snapshot for a machine."""

	rows = frappe.get_all(
		"TimeBridge Device Snapshot",
		filters={"machine": machine},
		fields=[
			"name",
			"verified_at",
			"status",
			"window_start",
			"window_end",
			"window_days",
			"transport",
			"device_counts",
			"server_counts",
			"asset_status",
			"error_message",
			"duration_seconds",
		],
		order_by="verified_at desc",
		limit=1,
	)

	if not rows:
		return None

	row = rows[0]

	for field in ("device_counts", "server_counts", "asset_status"):
		if isinstance(row.get(field), str):
			try:
				row[field] = json.loads(row[field])
			except Exception:
				pass

	return row


def snapshot_history(machine, limit=20):
	"""Recent verify runs for history panel."""

	rows = frappe.get_all(
		"TimeBridge Device Snapshot",
		filters={"machine": machine},
		fields=["name", "verified_at", "status", "window_days", "duration_seconds"],
		order_by="verified_at desc",
		limit=limit,
	)

	return rows


def write_snapshot(
	machine,
	*,
	transport,
	window_days,
	window_start,
	window_end,
	device_counts,
	server_counts,
	error_message=None,
	duration_seconds=None,
	started_at=None,
):
	"""Persist verify results and update machine mirror_status cache."""

	asset_status = build_asset_status(device_counts, server_counts)
	overall = compute_overall_status(asset_status, now_datetime())

	if error_message:
		overall = "Error"

	doc = frappe.get_doc(
		{
			"doctype": "TimeBridge Device Snapshot",
			"machine": machine,
			"verified_at": now_datetime(),
			"status": overall,
			"transport": transport,
			"window_days": cint(window_days),
			"window_start": window_start,
			"window_end": window_end,
			"device_counts": device_counts,
			"server_counts": server_counts,
			"asset_status": asset_status,
			"error_message": error_message,
			"duration_seconds": duration_seconds,
		}
	)
	doc.insert(ignore_permissions=True)

	frappe.db.set_value("TimeBridge Machine", machine, "mirror_status", overall, update_modified=False)
	frappe.db.commit()

	return doc.name


def get_device_mirror(machine_id, window_days=None):
	"""Latest snapshot plus live server counts for the Desk page."""

	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	window_days = cint(window_days) if window_days is not None else default_window_days()
	start_date, end_date, _, _ = window_bounds(window_days)

	snapshot = latest_snapshot(machine_id)
	server_counts = compute_server_counts(machine_id, start_date, end_date)

	contact = commands.last_contact(machine_id) or {}

	return {
		"machine": {
			"name": machine.name,
			"machine_name": machine.machine_name,
			"machine_id": machine.machine_id,
			"sdk_type": machine.sdk_type,
			"serial_number": machine.serial_number,
			"status": machine.status,
			"mirror_status": machine.mirror_status,
			"last_contact_at": machine.last_contact_at,
		},
		"window_days": window_days,
		"window_start": str(start_date),
		"window_end": str(end_date),
		"snapshot": snapshot,
		"server_counts": server_counts,
		"contact": contact,
		"history": snapshot_history(machine_id),
	}


def start_mirror_verify(machine_id, window_days=None):
	"""Kick off async verify — PyZK job or ADMS command sequence."""

	window_days = cint(window_days) if window_days is not None else default_window_days()
	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	start_date, end_date, start_dt, end_dt = window_bounds(window_days)

	run_id = frappe.generate_hash(length=10)
	server_counts = compute_server_counts(machine_id, start_date, end_date)
	started_at = now_datetime()

	set_progress(
		machine_id,
		{
			"run_id": run_id,
			"status": "running",
			"stage": "Starting",
			"window_days": window_days,
			"window_start": str(start_date),
			"window_end": str(end_date),
			"server_counts": server_counts,
			"device_counts": {},
			"started_at": str(started_at)[:19],
		},
	)

	if is_push_device(machine):
		commands.start_mirror_verify(
			machine_id,
			window_days=window_days,
			start_dt=start_dt.strftime("%Y-%m-%d %H:%M:%S"),
			end_dt=end_dt.strftime("%Y-%m-%d %H:%M:%S"),
			run_id=run_id,
			server_counts=server_counts,
		)
	else:
		frappe.enqueue(
			"timebridge.timebridge.services.device_mirror.run_pyzk_verify_job",
			queue="short",
			timeout=600,
			machine_id=machine_id,
			window_days=window_days,
			run_id=run_id,
			server_counts=server_counts,
			started_at=str(started_at)[:19],
		)

	return {"run_id": run_id, "status": "running"}


def run_pyzk_verify_job(machine_id, window_days, run_id, server_counts, started_at):
	"""Background job: connect via PyZK and read device inventory counts."""

	from frappe.utils import get_datetime

	started = get_datetime(started_at)
	start_date, end_date, start_dt, end_dt = window_bounds(window_days, end=started)

	set_progress(
		machine_id,
		{
			**get_progress(machine_id),
			"stage": "Connecting",
		},
	)

	machine = frappe.get_doc("TimeBridge Machine", machine_id)
	device_counts = {}
	error_message = None

	try:
		connector = get_connector(machine)
		info = connector.get_device_info(machine)

		device_counts["users"] = cint(info.get("user_count"))
		device_counts["fingerprints"] = cint(info.get("finger_count"))
		device_counts["faces"] = cint(info.get("face_count"))

		set_progress(machine_id, {**get_progress(machine_id), "stage": "Reading punches"})

		with connector.connect(machine) as conn:
			records = connector.get_attendance(conn)

		punch_count = 0

		for row in records:
			ts = get_datetime(row.get("timestamp"))
			if ts and start_dt <= ts <= end_dt:
				punch_count += 1

		device_counts["punches"] = punch_count

		# PyZK does not expose photo count directly; use server as reference only.
		device_counts["photos"] = None

	except Exception as exc:
		error_message = str(exc)[:1000]
		frappe.log_error(title="TimeBridge Mirror: PyZK verify failed", message=frappe.get_traceback())

	duration = time_diff_in_seconds(now_datetime(), started)

	if not error_message:
		write_snapshot(
			machine_id,
			transport="PyZK",
			window_days=window_days,
			window_start=start_date,
			window_end=end_date,
			device_counts=device_counts,
			server_counts=server_counts,
			duration_seconds=duration,
			started_at=started,
		)

	asset_status = build_asset_status(device_counts, server_counts)

	set_progress(
		machine_id,
		{
			"run_id": run_id,
			"status": "failed" if error_message else "complete",
			"stage": "Done",
			"window_days": window_days,
			"window_start": str(start_date),
			"window_end": str(end_date),
			"server_counts": server_counts,
			"device_counts": device_counts,
			"asset_status": asset_status,
			"overall_status": "Error" if error_message else compute_overall_status(asset_status),
			"error_message": error_message,
			"duration_seconds": duration,
			"started_at": str(started)[:19],
		},
	)


def mirror_verify_progress(machine_id):
	"""Poll verify state — merges cache progress with latest snapshot."""

	state = get_progress(machine_id)
	adms = commands.mirror_verify_progress(machine_id)

	if adms.get("active"):
		state = {**state, **adms}

	if state.get("status") in ("complete", "failed"):
		snapshot = latest_snapshot(machine_id)
		if snapshot:
			state["snapshot"] = snapshot

	return state


def on_adms_mirror_complete(machine_id, state):
	"""Called from ADMS handlers when mirror verify finishes."""

	started = get_datetime(state.get("started_at")) if state.get("started_at") else now_datetime()
	duration = time_diff_in_seconds(now_datetime(), started)

	write_snapshot(
		machine_id,
		transport="ADMS",
		window_days=state.get("window_days"),
		window_start=state.get("window_start"),
		window_end=state.get("window_end"),
		device_counts=state.get("device_counts") or {},
		server_counts=state.get("server_counts") or {},
		error_message=state.get("error_message"),
		duration_seconds=duration,
		started_at=started,
	)

	asset_status = build_asset_status(
		state.get("device_counts") or {},
		state.get("server_counts") or {},
	)

	set_progress(
		machine_id,
		{
			**state,
			"status": "failed" if state.get("error_message") else "complete",
			"stage": "Done",
			"asset_status": asset_status,
			"overall_status": "Error" if state.get("error_message") else compute_overall_status(asset_status),
			"duration_seconds": duration,
		},
	)

	commands.clear_mirror_verify(machine_id)


def request_template_fetch(machine_id):
	"""Queue ADMS template pull commands for manual Fetch templates action."""

	from timebridge.timebridge.services.connection import is_push_device

	machine = frappe.get_doc("TimeBridge Machine", machine_id)

	if not is_push_device(machine):
		frappe.throw("Template fetch via query is only available for ADMS push devices.")

	commands.queue_template_fetch(machine_id)
	return {"queued": True}


def purge_old_snapshots():
	"""Remove snapshots older than log_retention_days."""

	retention = cint(frappe.db.get_single_value("TimeBridge Settings", "log_retention_days")) or 90
	cutoff = add_days(now_datetime(), -retention)

	names = frappe.get_all(
		"TimeBridge Device Snapshot",
		filters=[["verified_at", "<", cutoff]],
		pluck="name",
	)

	for name in names:
		frappe.delete_doc("TimeBridge Device Snapshot", name, ignore_permissions=True)

	if names:
		frappe.db.commit()


def run_scheduled_verify():
	"""Cron entry: verify configured machines when mirror schedule is enabled."""

	if not cint(frappe.db.get_single_value("TimeBridge Settings", "enable_scheduler")):
		return

	if not cint(frappe.db.get_single_value("TimeBridge Settings", "enable_mirror_schedule")):
		return

	settings = frappe.get_single("TimeBridge Settings")
	frequency = settings.mirror_schedule_frequency or "Every Night"
	schedule_time = settings.mirror_schedule_time

	if not _schedule_due_now(frequency, schedule_time):
		return

	machines = _scheduled_machines(settings)

	for machine in machines:
		try:
			start_mirror_verify(machine, window_days=default_window_days())
		except Exception:
			frappe.log_error(
				title=f"TimeBridge Mirror: scheduled verify failed for {machine}",
				message=frappe.get_traceback(),
			)


def notify_drift_if_configured(machine, snapshot_name, overall_status):
	"""Log drift when scheduled verify finds gaps and notify is enabled."""

	if overall_status != "Drift":
		return

	if not cint(frappe.db.get_single_value("TimeBridge Settings", "mirror_notify_on_drift")):
		return

	frappe.log_error(
		title=f"TimeBridge Mirror: drift on {machine}",
		message=f"Scheduled verify found drift. Snapshot: {snapshot_name}",
	)


def _scheduled_machines(settings):
	"""Machines to verify — allowlist or all sync_enabled."""

	if settings.mirror_machines:
		return [row.machine for row in settings.mirror_machines if row.machine]

	return frappe.get_all(
		"TimeBridge Machine",
		filters={"sync_enabled": 1},
		pluck="name",
	)


def _schedule_due_now(frequency, schedule_time):
	"""True when this cron tick should run scheduled verify."""

	now = now_datetime()
	target_hour = cint(str(schedule_time or "02:00:00").split(":")[0])
	target_minute = cint(str(schedule_time or "02:00:00").split(":")[1])

	if now.hour != target_hour or now.minute > 14:
		return False

	if frequency == "Every Night":
		return True

	if frequency == "Every Monday" and now.weekday() == 0:
		return True

	if frequency == "Every Sunday" and now.weekday() == 6:
		return True

	return frequency == "Custom"
