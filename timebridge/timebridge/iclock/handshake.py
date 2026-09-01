# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Attendance PUSH handshake (PDF §5) and upload ack (§11.2–11.5)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import cint

from timebridge.timebridge.iclock import stamps
from timebridge.timebridge.iclock.protocol import transflag_line

PUSH_PROT_VER = "2.4.1"
SERVER_VER = "2.4.1"
PUSH_OPTIONS = (
	"FingerFunOn,FaceFunOn,UserCount,TransactionCount,FPCount,"
	"FaceCount,UserPicFunOn,BioPhotoFunOn"
)


def ack(count):
	return f"OK: {cint(count)}"


def server_timezone_option():
	try:
		offset = datetime.now(
			ZoneInfo(frappe.utils.get_system_timezone())
		).utcoffset()
		minutes = int(offset.total_seconds() // 60)
	except Exception:
		return "0"

	if minutes % 60 == 0:
		return str(minutes // 60)
	return str(minutes)


def build_handshake(serial, machine_row=None):
	att, oper, photo = stamps.handshake_stamps(machine_row)
	return (
		f"GET OPTION FROM: {serial or 'UNKNOWN'}\n"
		f"Stamp={att}\n"
		f"ATTLOGStamp={att}\n"
		f"OPERLOGStamp={oper}\n"
		f"ATTPHOTOStamp={photo}\n"
		f"BIODATAStamp=9999\n"
		f"IDCARDStamp=9999\n"
		f"ERRORLOGStamp=9999\n"
		f"ErrorDelay=30\n"
		f"Delay=30\n"
		f"TransTimes=00:00;14:00\n"
		f"TransInterval=1\n"
		f"{transflag_line(machine_row)}\n"
		f"TimeZone={server_timezone_option()}\n"
		f"Realtime=1\n"
		f"Encrypt=0\n"
		f"ServerVer={SERVER_VER}\n"
		f"PushProtVer={PUSH_PROT_VER}\n"
		f"PushOptionsFlag=1\n"
		f"PushOptions={PUSH_OPTIONS}\n"
	)
