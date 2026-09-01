# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Parse Attendance PUSH payloads. No database."""

import re

PUNCH_DIRECTION_MAP = {"0": "In", "1": "Out", "4": "In", "5": "Out"}
VERIFY_MODE_MAP = {"0": "Password", "1": "Fingerprint", "2": "Card", "15": "Face"}


def parse_table_name(table):
	if not table:
		return None
	parts = table.strip().split()
	return parts[0].upper() if parts else None


def parse_attlog(body):
	records = []
	skipped = []

	for line in (body or "").splitlines():
		line = line.rstrip("\r")
		if not line.strip():
			continue
		parts = line.split("\t")
		if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
			skipped.append(line)
			continue
		status = parts[2].strip() if len(parts) > 2 else ""
		verify = parts[3].strip() if len(parts) > 3 else ""
		records.append(
			{
				"device_user_id": parts[0].strip(),
				"timestamp": parts[1].strip(),
				"punch_direction": PUNCH_DIRECTION_MAP.get(status, "Unknown"),
				"verify_mode": VERIFY_MODE_MAP.get(verify, "Other" if verify else None),
				"device_status": status or None,
				"raw": line,
			}
		)

	return records, skipped


def parse_userinfo(body):
	records = []
	skipped = []

	for line in (body or "").splitlines():
		line = line.strip()
		if not line:
			continue
		if line.upper().startswith("USER "):
			line = line[5:]
		fields = {}
		for chunk in line.split("\t"):
			if "=" not in chunk:
				continue
			key, _, value = chunk.partition("=")
			fields[key.strip().upper()] = value.strip()
		user_id = fields.get("PIN")
		if not user_id:
			skipped.append(line)
			continue
		if fields.get("CONTENT") or fields.get("PHOTO"):
			continue
		privilege = fields.get("PRI") or "0"
		records.append(
			{
				"user_id": user_id,
				"user_name": fields.get("NAME") or f"User {user_id}",
				"card_number": fields.get("CARD") or None,
				"privilege": "User" if privilege in ("0", "") else "Admin",
				"raw": line,
			}
		)

	return records, skipped


def parse_oplog(body):
	records = []
	for line in (body or "").splitlines():
		line = line.rstrip("\r")
		if not line.strip() or not line.upper().startswith("OPLOG"):
			continue
		parts = line.split("\t")
		head = parts[0].split()
		records.append(
			{
				"op_type": head[1] if len(head) > 1 else None,
				"op_who": parts[1].strip() if len(parts) > 1 else None,
				"op_time": parts[2].strip() if len(parts) > 2 else None,
				"raw": line,
			}
		)
	return records


def parse_photo_fields(body):
	records = []
	for line in (body or "").splitlines():
		line = line.rstrip("\r")
		if not line.strip() or "=" not in line:
			continue
		fields = {}
		for chunk in line.split("\t"):
			if "=" not in chunk:
				continue
			key, _, value = chunk.partition("=")
			fields[key.strip().upper()] = value.strip()
		user_id = fields.get("PIN")
		content = fields.get("CONTENT") or fields.get("PHOTO")
		if user_id and content:
			records.append({"user_id": user_id, "content": content})
	return records


def parse_options(body):
	result = {}
	for line in (body or "").splitlines():
		line = line.strip()
		if not line or "=" not in line:
			continue
		for chunk in line.replace("\t", "\n").replace(",", "\n").split("\n"):
			if "=" not in chunk:
				continue
			key, _, value = chunk.partition("=")
			upper = key.strip().upper()
			value = value.strip()
			if upper in ("USERCOUNT", "USERS"):
				result["users"] = _int(value)
			elif upper in ("TRANSACTIONCOUNT", "ATTLOGCOUNT", "RECORDS"):
				result["punches_total"] = _int(value)
			elif upper in ("FPCOUNT", "FINGERCOUNT"):
				result["fingerprints"] = _int(value)
			elif upper in ("FACECOUNT",):
				result["faces"] = _int(value)
			elif upper in ("BIOPHOTOCOUNT", "USERPICCOUNT"):
				result["photos"] = _int(value)
			elif upper == "FWVERSION" or upper == "FIRMWARE":
				result["firmware"] = value
	return {k: v for k, v in result.items() if v is not None}


def parse_getrequest_info(info):
	text = (info or "").strip()
	if not text:
		return {}
	parts = [part.strip() for part in text.split(",")]
	ip_idx = None
	for index, part in enumerate(parts):
		if re.match(r"^\d+\.\d+\.\d+\.\d+$", part):
			ip_idx = index
			break
	if ip_idx is None or ip_idx < 3:
		return {}
	result = {
		"firmware": parts[0] if ip_idx > 3 else None,
		"users": _int(parts[ip_idx - 3]),
		"fingerprints": _int(parts[ip_idx - 2]),
		"punches_total": _int(parts[ip_idx - 1]),
		"device_ip": parts[ip_idx],
	}
	if ip_idx + 4 < len(parts):
		result["faces"] = _int(parts[ip_idx + 4])
	return {k: v for k, v in result.items() if v is not None}


def _int(value):
	try:
		return int(str(value).strip())
	except (TypeError, ValueError):
		return None


def body_line_count(body):
	return len([line for line in (body or "").splitlines() if line.strip()])
