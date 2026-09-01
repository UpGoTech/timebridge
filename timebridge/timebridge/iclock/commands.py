# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Queue commands for the device's next /iclock/getrequest poll."""

import frappe
from frappe.utils import cint, now_datetime
from frappe import _

CONTACT_TTL = 86400
PHOTO_FETCH_TTL = 600
DOCTYPE = "TimeBridge Device Command"


def contact_key(machine):
	return f"timebridge_adms_last_contact::{machine}"


def photo_fetch_key(machine):
	return f"timebridge_photo_fetch::{machine}"


def _next_command_id(machine):
	last = frappe.db.sql(
		"""
		SELECT MAX(command_id) FROM `tabTimeBridge Device Command`
		WHERE machine = %s
		""",
		machine,
	)[0][0]
	return cint(last) + 1


def queue_command(machine, command, kind="Other", user_id=None):
	command_id = _next_command_id(machine)
	frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"machine": machine,
			"command_id": command_id,
			"command": command,
			"kind": kind,
			"user_id": user_id,
			"status": "Queued",
			"queued_at": now_datetime(),
		}
	).insert(ignore_permissions=True)
	return command_id


def pop_commands(machine):
	rows = frappe.get_all(
		DOCTYPE,
		filters={"machine": machine, "status": "Queued"},
		fields=["name", "command_id", "command"],
		order_by="command_id asc",
	)
	pending = []
	now = now_datetime()
	for row in rows:
		frappe.db.set_value(
			DOCTYPE,
			row.name,
			{"status": "Sent", "sent_at": now},
			update_modified=False,
		)
		pending.append({"id": row.command_id, "command": row.command})
	return pending


def pending_count(machine):
	return frappe.db.count(DOCTYPE, {"machine": machine, "status": "Queued"})


def has_active_fetch(machine, needles=(), kinds=("Fetch", "Photo")):
	"""True when a desk download command was collected and a response is expected."""

	rows = frappe.get_all(
		DOCTYPE,
		filters={"machine": machine, "status": "Sent", "kind": ["in", list(kinds)]},
		fields=["command"],
	)
	if not rows:
		return False
	if not needles:
		return True
	for row in rows:
		command = row.command or ""
		if any(needle in command for needle in needles):
			return True
	return False


def finish_fetch_commands(machine, needles=(), kinds=("Fetch", "Photo")):
	"""Mark matching Sent download commands Done after a successful ingest."""

	rows = frappe.get_all(
		DOCTYPE,
		filters={"machine": machine, "status": "Sent", "kind": ["in", list(kinds)]},
		fields=["name", "command"],
	)
	for row in rows:
		command = row.command or ""
		if needles and not any(needle in command for needle in needles):
			continue
		frappe.db.set_value(
			DOCTYPE,
			row.name,
			{"status": "Done"},
			update_modified=False,
		)


def format_commands(commands):
	if not commands:
		return "OK"
	return "\n".join(f"C:{c['id']}:{c['command']}" for c in commands)


def request_users():
	return "DATA QUERY USERINFO"


def resend_attendance_between(start, end):
	return f"DATA QUERY ATTLOG StartTime={start}\tEndTime={end}"


def request_info():
	return "INFO"


def reboot():
	return "REBOOT"


def format_userinfo_update(user_id, user_name, privilege="User", password="", card=""):
	pri = "14" if privilege == "Admin" else "0"
	return (
		f"DATA UPDATE USERINFO PIN={user_id}\tName={user_name or ''}"
		f"\tPri={pri}\tPasswd={password or ''}\tCard={card or ''}\tGrp=1"
	)


def format_userinfo_delete(user_id):
	return f"DATA DELETE USERINFO PIN={user_id}"


def photo_queries(machine):
	return [
		"DATA QUERY tablename=biophoto\tfielddesc=*\tfilter=*",
		"DATA QUERY tablename=userpic\tfielddesc=*\tfilter=*",
		"DATA QUERY USERPIC",
		"DATA QUERY BIOPHOTO",
	]


def start_enroll_photo_fetch(machine, baseline=0):
	frappe.cache().set_value(
		photo_fetch_key(machine),
		{"round": 1, "baseline": cint(baseline)},
		expires_in_sec=PHOTO_FETCH_TTL,
	)
	for command in photo_queries(machine):
		queue_command(machine, command, kind="Photo")


def advance_enroll_photo_fetch(machine, photos_now=0):
	return None


def record_contact(machine, kind):
	stamp = now_datetime()
	frappe.cache().set_value(
		contact_key(machine),
		{"at": stamp.strftime("%Y-%m-%d %H:%M:%S"), "kind": kind},
		expires_in_sec=CONTACT_TTL,
	)
	frappe.db.set_value(
		"TimeBridge Machine",
		machine,
		"last_contact_at",
		stamp,
		update_modified=False,
	)


def last_contact(machine):
	cached = frappe.cache().get_value(contact_key(machine))
	if cached:
		return cached
	stored = frappe.db.get_value("TimeBridge Machine", machine, "last_contact_at")
	if not stored:
		return {}
	return {"at": str(stored)[:19], "kind": "recorded"}


INFO_WAIT_TTL = 300
INFO_RESULT_TTL = 300
INFO_TIMEOUT_SECONDS = 120
COMMAND = "TimeBridge Device Command"


def _info_wait_key(machine):
	return f"timebridge_info_wait::{machine}"


def _info_result_key(machine):
	return f"timebridge_info_result::{machine}"


def start_info_request(machine):
	"""Queue INFO and register a desk poll session."""

	command_id = queue_command(machine, request_info(), kind="Fetch")
	frappe.cache().set_value(
		_info_wait_key(machine),
		{
			"command_id": command_id,
			"started_at": now_datetime().strftime("%Y-%m-%d %H:%M:%S"),
		},
		expires_in_sec=INFO_WAIT_TTL,
	)
	frappe.cache().delete_value(_info_result_key(machine))
	return {
		"status": "queued",
		"command_id": command_id,
		"pending_commands": pending_count(machine),
	}


def info_progress(machine, command_id):
	"""Poll state for a queued INFO command."""

	command_id = cint(command_id)
	wait = frappe.cache().get_value(_info_wait_key(machine)) or {}
	result = frappe.cache().get_value(_info_result_key(machine))
	if result and cint(result.get("command_id")) == command_id:
		return {
			"phase": "done",
			"message": _("Info received from device."),
			"info": result.get("info") or {},
		}

	cmd = frappe.db.get_value(
		COMMAND,
		{"machine": machine, "command_id": command_id},
		["status", "command", "sent_at", "queued_at"],
		as_dict=True,
	)
	if not cmd:
		return {"phase": "error", "message": _("INFO command not found.")}

	started_at = wait.get("started_at") or cmd.queued_at
	elapsed = _elapsed_seconds(started_at)
	if elapsed >= INFO_TIMEOUT_SECONDS:
		return {
			"phase": "timeout",
			"message": _(
				"The device did not return INFO within {0} seconds."
			).format(INFO_TIMEOUT_SECONDS),
			"wait_seconds": elapsed,
		}

	if cmd.status == "Queued":
		return {
			"phase": "queued",
			"message": _("INFO command queued — waiting for device to poll…"),
			"wait_seconds": elapsed,
		}

	if cmd.status == "Sent":
		return {
			"phase": "waiting",
			"message": _("Command collected — waiting for device response…"),
			"wait_seconds": elapsed,
		}

	if cmd.status == "Done":
		info = format_info_display(machine)
		return {
			"phase": "done",
			"message": _("Info received from device."),
			"info": info,
		}

	return {
		"phase": "waiting",
		"message": _("Waiting for device…"),
		"wait_seconds": elapsed,
	}


def maybe_finish_info_wait(machine):
	wait = frappe.cache().get_value(_info_wait_key(machine))
	if not wait:
		return False

	command_id = cint(wait.get("command_id"))
	cmd_status = frappe.db.get_value(
		COMMAND,
		{"machine": machine, "command_id": command_id},
		"status",
	)
	if cmd_status != "Sent":
		return False

	info = format_info_display(machine)
	frappe.cache().set_value(
		_info_result_key(machine),
		{"command_id": command_id, "info": info},
		expires_in_sec=INFO_RESULT_TTL,
	)
	frappe.cache().delete_value(_info_wait_key(machine))
	_mark_command_done(machine, command_id)
	return True


def format_info_display(machine):
	row = frappe.db.get_value(
		"TimeBridge Machine",
		machine,
		[
			"serial_number",
			"machine_name",
			"machine_id",
			"adms_firmware",
			"adms_user_count",
			"adms_attlog_count",
			"adms_face_count",
			"adms_fp_count",
			"adms_photo_count",
			"adms_device_ip",
			"adms_pushver",
			"last_contact_at",
		],
		as_dict=True,
	) or {}

	lines = {}
	if row.get("serial_number"):
		lines["Serial"] = row.serial_number
	if row.get("machine_name"):
		lines["Name"] = row.machine_name
	if row.get("machine_id"):
		lines["Machine ID"] = row.machine_id
	if row.get("adms_firmware"):
		lines["Firmware"] = row.adms_firmware
	if row.get("adms_pushver"):
		lines["Push version"] = row.adms_pushver
	if row.get("adms_device_ip"):
		lines["Device IP"] = row.adms_device_ip
	if row.get("adms_user_count") is not None:
		lines["Users"] = row.adms_user_count
	if row.get("adms_attlog_count") is not None:
		lines["Attendance records"] = row.adms_attlog_count
	if row.get("adms_face_count") is not None:
		lines["Faces"] = row.adms_face_count
	if row.get("adms_fp_count") is not None:
		lines["Fingerprints"] = row.adms_fp_count
	if row.get("adms_photo_count") is not None:
		lines["Photos"] = row.adms_photo_count
	if row.get("last_contact_at"):
		lines["Last contact"] = str(row.last_contact_at)[:19]
	return lines


def _mark_command_done(machine, command_id):
	name = frappe.db.get_value(
		COMMAND,
		{"machine": machine, "command_id": command_id},
		"name",
	)
	if name:
		frappe.db.set_value(
			COMMAND,
			name,
			{"status": "Done"},
			update_modified=False,
		)


DOWNLOAD_SESSION_TTL = 600
DOWNLOAD_TIMEOUT_SECONDS = 180
DOWNLOAD_IDLE_SECONDS = 25

DOWNLOAD_KIND_CONFIG = {
	"users": {
		"needles": ("USERINFO",),
		"kinds": ("Fetch",),
		"title": "Users",
	},
	"transactions": {
		"needles": ("ATTLOG",),
		"kinds": ("Fetch",),
		"title": "Transactions",
	},
	"faces": {
		"needles": ("biophoto", "userpic", "BIOPHOTO", "USERPIC", "FACE"),
		"kinds": ("Photo", "Fetch"),
		"title": "Faces",
	},
}


def _download_session_key(machine, session_id):
	return f"timebridge_download::{machine}::{session_id}"


def _download_active_key(machine, kind):
	return f"timebridge_download_active::{machine}::{kind}"


def start_download_session(machine, kind, command_ids, meta=None):
	command_ids = [cint(command_id) for command_id in (command_ids or []) if command_id]
	session_id = f"{kind}-{command_ids[0] if command_ids else frappe.generate_hash(length=8)}"
	now = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	session = {
		"session_id": session_id,
		"kind": kind,
		"command_ids": command_ids,
		"started_at": now,
		"last_activity_at": None,
		"finished": False,
		"status": "queued",
		"stats": {
			"fetched": 0,
			"created": 0,
			"updated": 0,
			"photos_saved": 0,
			"duplicates": 0,
			"skipped": 0,
		},
		"meta": meta or {},
	}
	frappe.cache().set_value(
		_download_session_key(machine, session_id),
		session,
		expires_in_sec=DOWNLOAD_SESSION_TTL,
	)
	frappe.cache().set_value(
		_download_active_key(machine, kind),
		session_id,
		expires_in_sec=DOWNLOAD_SESSION_TTL,
	)
	return {
		"status": "queued",
		"session_id": session_id,
		"kind": kind,
		"command_ids": command_ids,
	}


def _get_download_session(machine, session_id):
	if not session_id:
		return None
	return frappe.cache().get_value(_download_session_key(machine, session_id))


def download_ingest_allowed(machine, kind):
	session_id = frappe.cache().get_value(_download_active_key(machine, kind))
	if not session_id:
		return False
	session = _get_download_session(machine, session_id)
	return bool(session and not session.get("finished"))


def explicit_download_allowed(machine, kind):
	if download_ingest_allowed(machine, kind):
		return True
	config = DOWNLOAD_KIND_CONFIG.get(kind)
	if not config:
		return False
	return has_active_fetch(machine, config["needles"], config["kinds"])


def record_download_activity(machine, kind, **increments):
	session_id = frappe.cache().get_value(_download_active_key(machine, kind))
	session = _get_download_session(machine, session_id)
	if not session or session.get("finished"):
		return
	session["last_activity_at"] = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	stats = session.setdefault("stats", {})
	for key, value in increments.items():
		stats[key] = cint(stats.get(key)) + cint(value)
	frappe.cache().set_value(
		_download_session_key(machine, session["session_id"]),
		session,
		expires_in_sec=DOWNLOAD_SESSION_TTL,
	)


def finish_download_session(machine, session, status="done"):
	if not session or session.get("finished"):
		return session
	config = DOWNLOAD_KIND_CONFIG.get(session.get("kind") or "")
	if config:
		finish_fetch_commands(machine, config["needles"], config["kinds"])
	session["finished"] = True
	session["status"] = status
	session["finished_at"] = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
	frappe.cache().set_value(
		_download_session_key(machine, session["session_id"]),
		session,
		expires_in_sec=DOWNLOAD_SESSION_TTL,
	)
	frappe.cache().delete_value(_download_active_key(machine, session["kind"]))
	return session


def _command_statuses(machine, command_ids):
	statuses = {}
	for command_id in command_ids or []:
		status = frappe.db.get_value(
			COMMAND,
			{"machine": machine, "command_id": cint(command_id)},
			"status",
		)
		if status:
			statuses[cint(command_id)] = status
	return statuses


def _download_stats_summary(session):
	stats = session.get("stats") or {}
	kind = session.get("kind")
	if kind == "users":
		return {
			"Records fetched": stats.get("fetched", 0),
			"Machine users created": stats.get("created", 0),
			"Machine users updated": stats.get("updated", 0),
			"Photos saved": stats.get("photos_saved", 0),
			"Lines skipped": stats.get("skipped", 0),
		}
	if kind == "transactions":
		return {
			"Records fetched": stats.get("fetched", 0),
			"Punches created": stats.get("created", 0),
			"Duplicates skipped": stats.get("duplicates", 0),
			"Invalid skipped": stats.get("skipped", 0),
		}
	if kind == "faces":
		return {"Photos saved": stats.get("photos_saved", 0)}
	meta = session.get("meta") or {}
	if meta.get("start") and meta.get("end"):
		return {"From": meta["start"], "To": meta["end"], **stats}
	return dict(stats)


def _download_done_response(session, message=None):
	stats = _download_stats_summary(session)
	if session.get("status") == "timeout" and not any(cint(v) for v in stats.values()):
		indicator = "orange"
		message = message or _(
			"The device did not return data within {0} seconds."
		).format(DOWNLOAD_TIMEOUT_SECONDS)
	elif session.get("status") == "timeout":
		indicator = "orange"
		message = message or _("Finished with partial data — device stopped sending.")
	else:
		indicator = "green"
		message = message or _("Download complete.")
	return {
		"phase": "done" if session.get("status") != "timeout" else "timeout",
		"message": message,
		"stats": stats,
		"indicator": indicator,
	}


def download_progress(machine, session_id):
	session = _get_download_session(machine, session_id)
	if not session:
		return {"phase": "error", "message": _("Download session not found.")}

	if session.get("finished"):
		return _download_done_response(session)

	elapsed = _elapsed_seconds(session.get("started_at"))
	if elapsed >= DOWNLOAD_TIMEOUT_SECONDS:
		finish_download_session(machine, session, status="timeout")
		return _download_done_response(session)

	command_ids = session.get("command_ids") or []
	statuses = _command_statuses(machine, command_ids)
	stats = session.get("stats") or {}
	has_activity = any(
		cint(stats.get(key))
		for key in ("fetched", "created", "updated", "photos_saved", "duplicates")
	)
	last_activity = session.get("last_activity_at")
	idle = _elapsed_seconds(last_activity) if last_activity else None

	if last_activity and idle is not None and idle >= DOWNLOAD_IDLE_SECONDS:
		finish_download_session(machine, session, status="done")
		return _download_done_response(session)

	if statuses and all(status == "Done" for status in statuses.values()):
		finish_download_session(machine, session, status="done")
		return _download_done_response(session)

	if last_activity:
		kind = session.get("kind")
		if kind == "users":
			message = _(
				"Receiving users… {0} fetched, {1} created, {2} photos so far."
			).format(
				stats.get("fetched", 0),
				stats.get("created", 0),
				stats.get("photos_saved", 0),
			)
		elif kind == "transactions":
			message = _(
				"Receiving transactions… {0} fetched, {1} stored so far."
			).format(stats.get("fetched", 0), stats.get("created", 0))
		elif kind == "faces":
			message = _("Receiving photos… {0} saved so far.").format(
				stats.get("photos_saved", 0)
			)
		else:
			message = _("Receiving data from device…")
		return {
			"phase": "receiving",
			"message": message,
			"wait_seconds": elapsed,
			"stats": _download_stats_summary(session),
		}

	if statuses and any(status == "Sent" for status in statuses.values()):
		return {
			"phase": "waiting",
			"message": _("Command collected — waiting for device upload…"),
			"wait_seconds": elapsed,
		}

	if statuses and any(status == "Queued" for status in statuses.values()):
		return {
			"phase": "queued",
			"message": _("Download queued — waiting for device to poll…"),
			"wait_seconds": elapsed,
		}

	if has_activity:
		return {
			"phase": "receiving",
			"message": _("Waiting for remaining batches…"),
			"wait_seconds": elapsed,
			"stats": _download_stats_summary(session),
		}

	return {
		"phase": "waiting",
		"message": _("Waiting for device…"),
		"wait_seconds": elapsed,
	}


def _elapsed_seconds(since):
	if not since:
		return 0
	from frappe.utils import get_datetime, now_datetime

	try:
		start = get_datetime(since)
	except Exception:
		return 0
	return max(0, int((now_datetime() - start).total_seconds()))
