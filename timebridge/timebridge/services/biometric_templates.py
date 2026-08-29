# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Biometric template vault — store and count enrollment templates on the server.

Unique key: (machine, user_id, bio_type, template_index, algorithm_major, algorithm_minor)
"""

import frappe

from frappe.utils import cint

# Push SDK biodata type index → our Select options
BIO_TYPE_MAP = {
	"1": "Fingerprint",
	"2": "Finger Vein",
	"3": "Face",
	"4": "Palm Vein",
	"5": "Palm Print",
	"8": "Face",
	"9": "Face",
}

BIO_TYPE_TO_SDK = {
	"Fingerprint": ("1",),
	"Face": ("3", "8", "9"),
	"Finger Vein": ("2",),
	"Palm Vein": ("4",),
	"Palm Print": ("5",),
}


def normalize_bio_type(raw):
	"""Map SDK type index or label to our bio_type Select value."""

	if not raw:
		return "Other"

	text = str(raw).strip()

	if text in BIO_TYPE_MAP:
		return BIO_TYPE_MAP[text]

	lower = text.lower()

	for label in ("Fingerprint", "Face", "Finger Vein", "Palm Vein", "Palm Print"):
		if label.lower() == lower:
			return label

	return "Other"


def upsert_template(
	machine,
	user_id,
	bio_type,
	template_index,
	template_data,
	*,
	algorithm_major=10,
	algorithm_minor=0,
	template_format=None,
	valid=1,
	source=None,
	source_table=None,
	size=None,
):
	"""
	Insert or update one template row. Returns True if created, False if updated.
	"""

	bio_type = normalize_bio_type(bio_type)
	user_id = str(user_id).strip()
	template_index = cint(template_index)
	algorithm_major = cint(algorithm_major)
	algorithm_minor = cint(algorithm_minor)

	if not machine or not user_id or not template_data:
		return False

	existing = frappe.db.get_value(
		"TimeBridge Biometric Template",
		{
			"machine": machine,
			"user_id": user_id,
			"bio_type": bio_type,
			"template_index": template_index,
			"algorithm_major": algorithm_major,
			"algorithm_minor": algorithm_minor,
		},
		"name",
	)

	machine_user = frappe.db.get_value(
		"TimeBridge Machine User",
		{"machine": machine, "user_id": user_id},
		"name",
	)

	fields = {
		"machine": machine,
		"machine_user": machine_user,
		"user_id": user_id,
		"bio_type": bio_type,
		"template_index": template_index,
		"algorithm_major": algorithm_major,
		"algorithm_minor": algorithm_minor,
		"template_format": template_format,
		"valid": cint(valid),
		"template_data": template_data,
		"size": cint(size) or len(template_data or ""),
		"source": source,
		"source_table": source_table,
	}

	if existing:
		doc = frappe.get_doc("TimeBridge Biometric Template", existing)
		doc.update(fields)
		doc.save(ignore_permissions=True)
		_update_machine_user_bio_flags(machine, user_id)
		return False

	doc = frappe.get_doc({"doctype": "TimeBridge Biometric Template", **fields})
	doc.insert(ignore_permissions=True)
	_update_machine_user_bio_flags(machine, user_id)
	return True


def upsert_templates(machine, records, source, source_table):
	"""Bulk upsert from parsed template dicts. Returns (created, updated)."""

	created = updated = 0

	for row in records or []:
		was_new = upsert_template(
			machine,
			row.get("user_id"),
			row.get("bio_type"),
			row.get("template_index"),
			row.get("template_data"),
			algorithm_major=row.get("algorithm_major", 10),
			algorithm_minor=row.get("algorithm_minor", 0),
			template_format=row.get("template_format"),
			valid=row.get("valid", 1),
			source=source,
			source_table=source_table,
			size=row.get("size"),
		)
		if was_new:
			created += 1
		else:
			updated += 1

	return created, updated


def _update_machine_user_bio_flags(machine, user_id):
	"""Refresh finger_count / face_registered from stored templates."""

	fp = frappe.db.count(
		"TimeBridge Biometric Template",
		{"machine": machine, "user_id": user_id, "bio_type": "Fingerprint"},
	)
	face = frappe.db.count(
		"TimeBridge Biometric Template",
		{"machine": machine, "user_id": user_id, "bio_type": "Face"},
	)

	name = frappe.db.get_value(
		"TimeBridge Machine User",
		{"machine": machine, "user_id": user_id},
		"name",
	)

	if not name:
		return

	frappe.db.set_value("TimeBridge Machine User", name, "finger_count", fp, update_modified=False)
	frappe.db.set_value(
		"TimeBridge Machine User",
		name,
		"face_registered",
		1 if face else 0,
		update_modified=False,
	)


def count_templates(machine, bio_type=None):
	"""Count stored templates, optionally filtered by bio_type."""

	filters = {"machine": machine}

	if bio_type:
		filters["bio_type"] = normalize_bio_type(bio_type)

	return frappe.db.count("TimeBridge Biometric Template", filters)


def count_all_template_types(machine):
	"""Return fingerprint and face counts from the vault."""

	return {
		"fingerprints": count_templates(machine, "Fingerprint"),
		"faces": count_templates(machine, "Face"),
	}
