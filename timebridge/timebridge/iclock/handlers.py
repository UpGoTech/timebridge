# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Route inbound /iclock requests after the renderer has claimed the path."""

import frappe
from frappe.utils import cint, now_datetime

from timebridge.timebridge.iclock import (
	audit,
	commands,
	discovery,
	handshake,
	parser,
	peers,
	photos,
	stamps,
	stats,
)
from timebridge.timebridge.iclock.protocol import receives
from timebridge.timebridge.iclock.server import adms_server_enabled
from timebridge.timebridge.services.device_records import (
	close_sync_log,
	link_unmatched_punches,
	open_sync_log,
	save_punches,
	save_users,
)
from timebridge.timebridge.services.machine_log import write_machine_log


def _photo_ingest_allowed(row, users_session=False, faces_session=False):
	if users_session or faces_session:
		return True
	if commands.explicit_download_allowed(row.name, "faces"):
		return True
	return any(
		receives(row, field)
		for field in (
			"receive_attphoto",
			"receive_userpic",
			"receive_face",
			"receive_biophoto",
		)
	)


def _record_user_download_photos(row, users_session, saved, flushed=0):
	total = cint(saved) + cint(flushed)
	if users_session and total:
		commands.record_download_activity(row.name, "users", photos_saved=total)


def handle_cdata(serial, args, body, method, raw=None):
	if not adms_server_enabled():
		return None

	row = discovery.machine_row(serial)

	if method in ("GET", "HEAD"):
		return _handshake(serial, args, row)

	if not row or row.adms_status != "Registered":
		return "OK"

	commands.record_contact(row.name, "upload")
	table = parser.parse_table_name(args.get("table"))

	if table == "ATTLOG":
		return _receive_attlog(row, args, body)
	if table in ("OPERLOG", "USERINFO"):
		return _receive_userinfo(row, args, body)
	if table in photos.PHOTO_TABLES:
		return _receive_photos(row, args, body, raw, table)
	if table == "OPTIONS":
		stats.apply_options_body(row.name, body)
		return "OK"
	return handshake.ack(parser.body_line_count(body) or 1)


def handle_getrequest(serial, args, body, method, raw=None):
	if not adms_server_enabled():
		return None
	row = discovery.machine_row(serial)
	if not row or row.adms_status != "Registered":
		return peers.pop_serial_command(serial) or "OK"

	commands.record_contact(row.name, "poll")
	info = args.get("INFO") or args.get("info")
	if info:
		stats.apply_info_tuple(row.name, info)

	pending = commands.pop_commands(row.name)
	return commands.format_commands(pending)


def handle_ping(serial, args, body, method, raw=None):
	if not adms_server_enabled():
		return None
	row = discovery.machine_row(serial)
	if row and row.adms_status == "Registered":
		commands.record_contact(row.name, "ping")
	return "OK"


def handle_devicecmd(serial, args, body, method, raw=None):
	if not adms_server_enabled():
		return None
	row = discovery.machine_row(serial)
	if row and row.adms_status == "Registered":
		commands.record_contact(row.name, "command result")
		stats.apply_info_command_body(row.name, body)
	return "OK"


def handle_fdata(serial, args, body, method, raw=None):
	if not adms_server_enabled():
		return None
	row = discovery.machine_row(serial)
	if not row or row.adms_status != "Registered":
		return "OK"
	commands.record_contact(row.name, "upload")
	users_session = commands.download_ingest_allowed(row.name, "users")
	faces_session = commands.download_ingest_allowed(row.name, "faces")
	if _photo_ingest_allowed(row, users_session, faces_session):
		saved = photos.handle_photo(
			row.name,
			args,
			raw or b"",
			body,
			"fdata",
			stash_if_missing=users_session,
		)
		if faces_session and saved:
			commands.record_download_activity(row.name, "faces", photos_saved=saved)
		elif users_session:
			flushed = photos.flush_pending_photos(row.name, "fdata")
			_record_user_download_photos(row, users_session, saved, flushed)
		elif commands.explicit_download_allowed(row.name, "faces"):
			commands.finish_fetch_commands(
				row.name,
				("biophoto", "userpic", "BIOPHOTO", "USERPIC", "FACE"),
				kinds=("Photo", "Fetch"),
			)
	return handshake.ack(1)


def handle_querydata(serial, args, body, method, raw=None):
	return "OK"


def _handshake(serial, args, row):
	discovery.record_init(serial, args)
	row = discovery.machine_row(serial)

	if not row or row.adms_status != "Registered":
		return "OK"

	commands.record_contact(row.name, "handshake")
	if not row.adms_handshake_at:
		frappe.db.set_value(
			"TimeBridge Machine",
			row.name,
			"adms_handshake_at",
			now_datetime(),
			update_modified=False,
		)
		commands.queue_command(row.name, commands.request_info(), kind="Fetch")

	return handshake.build_handshake(serial, row)


def _receive_attlog(row, args, body):
	records, skipped = parser.parse_attlog(body)
	fetched = len(records) + len(skipped)
	explicit_fetch = commands.explicit_download_allowed(row.name, "transactions")
	session_active = commands.download_ingest_allowed(row.name, "transactions")

	if not receives(row, "receive_attlog") and not explicit_fetch:
		stamps.record_attlog_stamp(row.name, args, records)
		frappe.db.commit()
		return handshake.ack(fetched or 1)

	try:
		result = save_punches(row.name, records)
		sync_batch = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
		log_name = open_sync_log(row.name, "Attendance", sync_batch)
		close_sync_log(
			log_name,
			"Success",
			fetched=fetched,
			created=result["created"],
			skipped=result["duplicates"] + result["invalid"] + len(skipped),
		)
		stamps.record_attlog_stamp(row.name, args, records)
		if session_active:
			commands.record_download_activity(
				row.name,
				"transactions",
				fetched=fetched,
				created=result["created"],
				duplicates=result["duplicates"],
				skipped=result["invalid"] + len(skipped),
			)
		elif explicit_fetch:
			commands.finish_fetch_commands(row.name, ("ATTLOG",))
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		tb = frappe.get_traceback()
		write_machine_log(
			machine=row.name,
			level="Error",
			event="Upload",
			message="ATTLOG ingest failed",
			details=tb,
		)
		frappe.db.commit()
		return "Error: ATTLOG ingest failed"

	return handshake.ack(fetched or 1)


def _receive_userinfo(row, args, body):
	records, skipped = parser.parse_userinfo(body)
	photo_rows = parser.parse_photo_fields(body)
	op_rows = parser.parse_oplog(body)
	explicit_users = commands.explicit_download_allowed(row.name, "users")
	users_session = commands.download_ingest_allowed(row.name, "users")
	store_users = (
		receives(row, "receive_enrolluser")
		or receives(row, "receive_chguser")
		or explicit_users
	)
	explicit_photos = commands.explicit_download_allowed(row.name, "faces")
	faces_session = commands.download_ingest_allowed(row.name, "faces")
	stash_photos = bool(users_session)

	if records and store_users:
		sync_batch = now_datetime().strftime("%Y-%m-%d %H:%M:%S")
		log_name = open_sync_log(row.name, "Users", sync_batch)
		try:
			result = save_users(row.name, records)
			link_unmatched_punches(row.name)
			close_sync_log(
				log_name,
				"Success",
				fetched=len(records) + len(skipped),
				created=result["created"],
				skipped=len(skipped),
			)
			frappe.db.set_value(
				"TimeBridge Machine",
				row.name,
				"last_user_sync",
				now_datetime(),
			)
			if users_session:
				commands.record_download_activity(
					row.name,
					"users",
					fetched=len(records) + len(skipped),
					created=result["created"],
					updated=result["updated"],
					skipped=len(skipped),
				)
				flushed = photos.flush_pending_photos(row.name, "BIOPHOTO")
				if flushed:
					commands.record_download_activity(
						row.name, "users", photos_saved=flushed
					)
			elif explicit_users:
				commands.finish_fetch_commands(row.name, ("USERINFO",))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			tb = frappe.get_traceback()
			close_sync_log(log_name, "Failed", fetched=len(records), error=tb[:1000])
			frappe.db.commit()
			return "Error: USERINFO ingest failed"

	if photo_rows and _photo_ingest_allowed(row, users_session, faces_session):
		try:
			saved = photos.save_photos_from_fields(
				row.name, photo_rows, "BIOPHOTO", stash_if_missing=stash_photos
			)
			flushed = photos.flush_pending_photos(row.name, "BIOPHOTO") if users_session else 0
			if faces_session:
				if saved or flushed:
					commands.record_download_activity(
						row.name, "faces", photos_saved=cint(saved) + cint(flushed)
					)
			elif users_session:
				_record_user_download_photos(row, users_session, saved, flushed)
			elif explicit_photos:
				commands.finish_fetch_commands(
					row.name,
					("biophoto", "userpic", "BIOPHOTO", "USERPIC", "FACE"),
					kinds=("Photo", "Fetch"),
				)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title="TimeBridge iclock: OPERLOG photo failed",
				message=frappe.get_traceback(),
			)
	elif users_session:
		flushed = photos.flush_pending_photos(row.name, "BIOPHOTO")
		if flushed:
			commands.record_download_activity(row.name, "users", photos_saved=flushed)
			frappe.db.commit()

	stamps.record_operlog_stamp(row.name, args, op_rows=op_rows)
	frappe.db.commit()
	count = parser.body_line_count(body)
	return handshake.ack(count or 1)


def _receive_photos(row, args, body, raw, table):
	users_session = commands.download_ingest_allowed(row.name, "users")
	faces_session = commands.download_ingest_allowed(row.name, "faces")
	explicit_fetch = commands.explicit_download_allowed(row.name, "faces")
	if _photo_ingest_allowed(row, users_session, faces_session):
		saved = photos.handle_photo(
			row.name,
			args,
			raw or b"",
			body,
			table,
			stash_if_missing=users_session,
		)
		flushed = photos.flush_pending_photos(row.name, table) if users_session else 0
		if faces_session and (saved or flushed):
			commands.record_download_activity(
				row.name, "faces", photos_saved=cint(saved) + cint(flushed)
			)
		elif users_session:
			_record_user_download_photos(row, users_session, saved, flushed)
		elif explicit_fetch and not faces_session and not users_session:
			commands.finish_fetch_commands(
				row.name,
				("biophoto", "userpic", "BIOPHOTO", "USERPIC", "FACE"),
				kinds=("Photo", "Fetch"),
			)
	rows = parser.parse_photo_fields(body)
	return handshake.ack(len(rows) or 1)
