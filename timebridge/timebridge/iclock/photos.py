# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Store enrolment JPEGs on TimeBridge Machine User."""

import base64
import re

import frappe
from frappe.utils import cint

from timebridge.timebridge.services.machine_log import write_machine_log

PHOTO_TABLES = {"ATTPHOTO", "USERPIC", "USERPHOTO", "FACE", "BIOPHOTO"}
ENROLL_SOURCES = {"USERPIC", "USERPHOTO", "BIOPHOTO", "FACE", "fdata"}
PUNCH_SOURCES = {"ATTPHOTO"}
IMAGE_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")
PHOTO_FILENAME = re.compile(
	r"^\d{8,14}[-_](?P<user_id>[^-_.\s]+)\.(?:jpe?g|png|bmp)$",
	re.IGNORECASE,
)


def looks_like_image(data):
	return isinstance(data, bytes) and data.startswith(IMAGE_SIGNATURES)


def user_id_from_filename(value):
	match = PHOTO_FILENAME.match(value or "")
	return match.group("user_id") if match else value


def is_punch_snapshot(source, args):
	if source in PUNCH_SOURCES:
		return True
	pin = str(args.get("PIN") or args.get("pin") or "").strip()
	return bool(PHOTO_FILENAME.match(pin))


def extract_user_id(args, body_text):
	for key in ("PIN", "pin", "UserID", "userid", "USERID"):
		if args.get(key):
			return user_id_from_filename(str(args[key]).strip())
	match = re.search(r"\bPIN=([^\s\t&]+)", body_text or "")
	return user_id_from_filename(match.group(1).strip()) if match else None


def decode_image(raw_bytes, body_text):
	if looks_like_image(raw_bytes):
		return raw_bytes
	if isinstance(raw_bytes, bytes):
		for signature in IMAGE_SIGNATURES:
			start = raw_bytes.find(signature)
			if start > 0:
				return raw_bytes[start:]
	match = re.search(
		r"(?:CONTENT|PHOTO|IMAGE)=([A-Za-z0-9+/=\r\n]+)",
		body_text or "",
	)
	candidate = match.group(1) if match else (body_text or "").strip()
	if len(candidate) < 64:
		return None
	try:
		decoded = base64.b64decode(candidate, validate=False)
	except Exception:
		return None
	return decoded if looks_like_image(decoded) else None


def decode_field_image(content):
	if not content or len(content) < 64:
		return None
	try:
		decoded = base64.b64decode(content, validate=False)
	except Exception:
		return None
	return decoded if looks_like_image(decoded) else None


def save_photos_from_fields(machine, rows, source):
	saved = 0
	for row in rows:
		image = decode_field_image(row.get("content"))
		if not image:
			continue
		if save_photo(machine, row["user_id"], image, source):
			saved += 1
	return saved


def save_photo(machine, user_id, image_bytes, source):
	existing = frappe.db.get_value(
		"TimeBridge Machine User",
		{"machine": machine, "user_id": user_id},
		["name", "photo", "retake_photo"],
		as_dict=True,
	)
	if not existing:
		write_machine_log(
			machine=machine,
			level="Warning",
			event="Photo",
			message=f"Photo for unknown user id {user_id!r}",
		)
		return None

	enroll = source in ENROLL_SOURCES
	replace = enroll or cint(existing.retake_photo)
	if existing.photo and not replace:
		return existing.photo

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": f"{machine}-{user_id}.jpg",
			"attached_to_doctype": "TimeBridge Machine User",
			"attached_to_name": existing.name,
			"attached_to_field": "photo",
			"content": image_bytes,
			"decode": False,
			"is_private": 0,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_value(
		"TimeBridge Machine User", existing.name, "photo", file_doc.file_url
	)
	if cint(existing.retake_photo):
		frappe.db.set_value(
			"TimeBridge Machine User", existing.name, "retake_photo", 0
		)
	if enroll:
		frappe.db.set_value(
			"TimeBridge Machine User", existing.name, "face_registered", 1
		)
	return file_doc.file_url


def handle_photo(machine, args, raw_bytes, body_text, source):
	try:
		if is_punch_snapshot(source, args):
			return
		from timebridge.timebridge.iclock import parser

		rows = parser.parse_photo_fields(body_text)
		if rows:
			save_photos_from_fields(machine, rows, source)
			return
		user_id = extract_user_id(args, body_text)
		image = decode_image(raw_bytes, body_text)
		if user_id and image:
			save_photo(machine, user_id, image, source)
	except Exception:
		frappe.log_error(
			title="TimeBridge iclock: photo failed",
			message=frappe.get_traceback(),
		)
