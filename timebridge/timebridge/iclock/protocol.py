# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Attendance PUSH TransFlag — Format II only (spec §5)."""

RECEIVE_TYPES = (
	("AttLog", "receive_attlog"),
	("OpLog", "receive_oplog"),
	("AttPhoto", "receive_attphoto"),
	("EnrollUser", "receive_enrolluser"),
	("ChgUser", "receive_chguser"),
	("EnrollFP", "receive_enrollfp"),
	("ChgFP", "receive_chgfp"),
	("FPImag", "receive_fpimage"),
	("FACE", "receive_face"),
	("UserPic", "receive_userpic"),
	("WORKCODE", "receive_workcode"),
	("BioPhoto", "receive_biophoto"),
)

RECEIVE_FIELDS = tuple(field for _, field in RECEIVE_TYPES)


def transflag_line(machine_row):
	"""
	Format II: TransFlag=TransData AttLog OpLog …

	An empty type list means no auto-upload. Do not emit Format I zeros:
	the PDF says TransFlag=0000000000 still uploads attendance photos.
	"""

	if not machine_row:
		return "TransFlag=TransData"

	enabled = []
	for token, field in RECEIVE_TYPES:
		if machine_row.get(field):
			enabled.append(token)

	if not enabled:
		return "TransFlag=TransData"

	return "TransFlag=TransData " + " ".join(enabled)


def receives(machine_row, field):
	if not machine_row:
		return False
	return bool(machine_row.get(field))
