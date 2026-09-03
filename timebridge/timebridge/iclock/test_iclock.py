# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.iclock import commands, discovery, handshake, handlers, peers, photos
from timebridge.timebridge.iclock.protocol import transflag_line
from timebridge.timebridge.iclock.renderer import IclockRenderer
from timebridge.timebridge.iclock.server import clear_server_enabled_cache, log_category_enabled


def enable_server(on=1):
	frappe.db.set_single_value("TimeBridge Settings", "adms_server_enabled", on)
	clear_server_enabled_cache()


def create_pending(serial):
	return discovery.create_pending_machine(
		machine_id=serial,
		machine_name=serial,
		serial_number=serial,
		require_discovery=False,
	)["machine"]


def _test_jpeg_bytes():
	"""Minimal valid JPEG — Frappe File rejects fake \\xff\\xd8 headers."""

	import io

	from PIL import Image

	buf = io.BytesIO()
	Image.new("RGB", (8, 8), color=(120, 80, 40)).save(buf, format="JPEG")
	return buf.getvalue()


class TestIclockServer(FrappeTestCase):
	def setUp(self):
		enable_server(0)

	def tearDown(self):
		enable_server(0)
		clear_server_enabled_cache()

	def test_disabled_renderer_does_not_claim_iclock(self):
		enable_server(0)
		renderer = IclockRenderer(path="iclock/cdata")
		self.assertFalse(renderer.can_render())

	def test_disabled_init_creates_nothing(self):
		enable_server(0)
		serial = f"OFF-{frappe.generate_hash(length=6)}"
		self.assertIsNone(
			handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		)
		self.assertFalse(
			frappe.db.exists("TimeBridge Machine", {"serial_number": serial})
		)
		self.assertFalse(
			frappe.db.exists("TimeBridge Machine", {"serial_number": serial})
		)
		self.assertFalse(
			frappe.db.exists("TimeBridge ADMS Log", {"serial_number": serial})
		)

	def test_enabled_renderer_claims_iclock(self):
		enable_server(1)
		renderer = IclockRenderer(path="iclock/cdata")
		self.assertTrue(renderer.can_render())

	def test_enabled_unknown_init_is_ok_not_handshake(self):
		enable_server(1)
		serial = f"PEND-{frappe.generate_hash(length=6)}"
		reply = handlers.handle_cdata(
			serial, {"SN": serial, "options": "all", "pushver": "2.4.1"}, "", "GET"
		)
		self.assertEqual(reply, "OK")
		self.assertNotIn("GET OPTION FROM", reply)
		self.assertFalse(
			frappe.db.exists("TimeBridge Machine", {"serial_number": serial})
		)

	def test_enabled_init_updates_manual_pending_machine(self):
		enable_server(1)
		serial = f"MAN-{frappe.generate_hash(length=6)}"
		create_pending(serial)
		reply = handlers.handle_cdata(
			serial, {"SN": serial, "options": "all", "pushver": "2.4.1"}, "", "GET"
		)
		self.assertEqual(reply, "OK")
		self.assertNotIn("GET OPTION FROM", reply)
		machine = frappe.db.get_value(
			"TimeBridge Machine", {"serial_number": serial}, ["name", "adms_status", "adms_pushver"], as_dict=True
		)
		self.assertEqual(machine.adms_status, "Pending")
		self.assertEqual(machine.adms_pushver, "2.4.1")
		self.assertTrue(frappe.db.get_value("TimeBridge Machine", machine.name, "adms_last_init_at"))

	def test_register_then_handshake(self):
		enable_server(1)
		serial = f"REG-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		reply = handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		self.assertIn(f"GET OPTION FROM: {serial}", reply)
		self.assertIn("TransFlag=TransData", reply)
		self.assertNotIn("TransFlag=0000000000", reply)
		self.assertIn("ErrorDelay=", reply)
		self.assertIn("Delay=", reply)
		self.assertIn("TransTimes=", reply)
		self.assertIn("TransInterval=", reply)
		self.assertIn("TimeZone=", reply)
		self.assertIn("Realtime=", reply)
		self.assertFalse(reply.split("TransFlag=")[1].split("\n")[0].strip().startswith("0"))

	def test_no_bootstrap_query_on_register(self):
		enable_server(1)
		serial = f"NB-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		queued = frappe.get_all(
			"TimeBridge Device Command",
			filters={"machine": name, "status": "Queued"},
			pluck="command",
		)
		self.assertFalse(any("QUERY ATTLOG" in (c or "") for c in queued))
		self.assertFalse(any("tablename=user" in (c or "") for c in queued))

	def test_attlog_not_stored_until_receive_ticked(self):
		enable_server(1)
		serial = f"AT-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		body = "5\t2026-09-01 10:00:00\t0\t15\t0\t0\n"
		with patch.object(frappe.db, "commit"):
			reply = handlers.handle_cdata(
				serial, {"SN": serial, "table": "ATTLOG", "Stamp": "9999"}, body, "POST"
			)
		self.assertEqual(reply, "OK: 1")
		self.assertEqual(frappe.db.count("TimeBridge Punch Log", {"machine": name}), 0)

		frappe.db.set_value("TimeBridge Machine", name, "receive_attlog", 1)
		with patch.object(frappe.db, "commit"):
			handlers.handle_cdata(
				serial, {"SN": serial, "table": "ATTLOG", "Stamp": "9999"}, body, "POST"
			)
		self.assertEqual(frappe.db.count("TimeBridge Punch Log", {"machine": name}), 1)

	def test_download_queues_only_ticked_types(self):
		enable_server(1)
		serial = f"DL-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		from timebridge.timebridge.iclock.api import download_data

		empty = download_data(name, days=7)
		self.assertEqual(empty["status"], "empty")

		frappe.db.set_value("TimeBridge Machine", name, "receive_attlog", 1)
		queued = download_data(name, days=7)
		self.assertEqual(queued["status"], "queued")
		self.assertIn("ATTLOG", queued["queued"])
		self.assertNotIn("tablename=user", queued["queued"])

	def test_userinfo_stored_on_explicit_download_without_receive_toggled(self):
		enable_server(1)
		serial = f"UQ-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		command_id = commands.queue_command(name, commands.request_users(), kind="Fetch")
		commands.start_download_session(name, "users", [command_id])
		handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")

		body = "PIN=5\tName=Asha\tPri=0\tCard=99\nPIN=6\tName=Biju\tPri=0\n"
		with patch.object(frappe.db, "commit"):
			reply = handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "USERINFO", "OpStamp": "1"},
				body,
				"POST",
			)
		self.assertEqual(reply, "OK: 2")
		self.assertEqual(frappe.db.count("TimeBridge Machine User", {"machine": name}), 2)

	def test_userinfo_multibatch_while_download_session_active(self):
		enable_server(1)
		serial = f"MB-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		command_id = commands.queue_command(name, commands.request_users(), kind="Fetch")
		session = commands.start_download_session(name, "users", [command_id])
		handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")

		batch1 = "PIN=1\tName=One\tPri=0\n" + "PIN=2\tName=Two\tPri=0\n"
		batch2 = "PIN=3\tName=Three\tPri=0\n"
		with patch.object(frappe.db, "commit"):
			handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "USERINFO", "OpStamp": "1"},
				batch1,
				"POST",
			)
			handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "USERINFO", "OpStamp": "2"},
				batch2,
				"POST",
			)
		self.assertEqual(frappe.db.count("TimeBridge Machine User", {"machine": name}), 3)
		progress = commands.download_progress(name, session["session_id"])
		self.assertIn(progress["phase"], ("receiving", "waiting", "done"))
		self.assertEqual(progress["stats"]["Machine users created"], 3)

	def test_querydata_users_stored_on_explicit_download(self):
		enable_server(1)
		serial = f"QD-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		command_id = commands.queue_command(name, commands.request_users(), kind="Fetch")
		commands.start_download_session(name, "users", [command_id])
		handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")

		body = (
			"user uid=1 cardno= pin=1 password= group=1 name=One privilege=0\n"
			"user uid=2 cardno= pin=2 password= group=1 name=Two privilege=0\n"
		)
		args = {
			"SN": serial,
			"type": "tabledata",
			"tablename": "user",
			"cmdid": str(command_id),
			"count": "2",
			"packcnt": "1",
			"packidx": "1",
		}
		with patch.object(frappe.db, "commit"):
			reply = handlers.handle_querydata(serial, args, body, "POST")
		self.assertEqual(reply, "user=2")
		self.assertEqual(frappe.db.count("TimeBridge Machine User", {"machine": name}), 2)

	def test_biophoto_during_users_download_session(self):
		import base64

		enable_server(1)
		serial = f"BP-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		command_id = commands.queue_command(name, commands.request_users(), kind="Fetch")
		commands.start_download_session(name, "users", [command_id])
		handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")

		content = base64.b64encode(_test_jpeg_bytes()).decode("ascii")
		with patch.object(frappe.db, "commit"):
			handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "USERINFO", "OpStamp": "1"},
				"PIN=9\tName=Nine\tPri=0\n",
				"POST",
			)
			handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "BIOPHOTO"},
				f"PIN=9\tCONTENT={content}\n",
				"POST",
			)
		photo = frappe.db.get_value(
			"TimeBridge Machine User",
			{"machine": name, "user_id": "9"},
			"photo",
		)
		self.assertTrue(photo)

	def test_operlog_biophoto_prefix_saved_on_user_download(self):
		import base64

		enable_server(1)
		serial = f"OP-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		command_id = commands.queue_command(name, commands.request_users(), kind="Fetch")
		commands.start_download_session(name, "users", [command_id])

		content = base64.b64encode(_test_jpeg_bytes()).decode("ascii")
		with patch.object(frappe.db, "commit"):
			handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "USERINFO", "OpStamp": "1"},
				"PIN=37\tName=Thirty Seven\tPri=0\n",
				"POST",
			)
			handlers.handle_cdata(
				serial,
				{"SN": serial, "table": "OPERLOG", "OpStamp": "2"},
				f"BIOPHOTO PIN=37\tFileName=37.jpg\tType=9\tSize=999\tContent={content}\n",
				"POST",
			)
		photo = frappe.db.get_value(
			"TimeBridge Machine User",
			{"machine": name, "user_id": "37"},
			"photo",
		)
		self.assertTrue(photo)

	def test_attlog_stored_on_explicit_download_without_receive_toggled(self):
		enable_server(1)
		serial = f"AQ-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		commands.queue_command(
			name,
			commands.resend_attendance_between("2026-09-01 00:00:00", "2026-09-01 23:59:59"),
			kind="Fetch",
		)
		handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")

		body = "5\t2026-09-01 10:00:00\t0\t15\t0\t0\n"
		with patch.object(frappe.db, "commit"):
			reply = handlers.handle_cdata(
				serial, {"SN": serial, "table": "ATTLOG", "Stamp": "9999"}, body, "POST"
			)
		self.assertEqual(reply, "OK: 1")
		self.assertEqual(frappe.db.count("TimeBridge Punch Log", {"machine": name}), 1)

	def test_create_pending_machine(self):
		serial = f"ADD-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		result = discovery.adopt_discovered_peer(serial)
		self.assertTrue(frappe.db.exists("TimeBridge Machine", result["machine"]))
		self.assertEqual(
			frappe.db.get_value("TimeBridge Machine", result["machine"], "adms_status"),
			"Pending",
		)
		serial2 = f"ADD2-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial2, "getrequest", "GET", {"SN": serial2})
		with self.assertRaises(frappe.ValidationError):
			discovery.adopt_discovered_peer(serial2, machine_id=serial)

	def test_undiscovered_serial_cannot_adopt(self):
		serial = f"NOPE-{frappe.generate_hash(length=6)}"
		with self.assertRaises(frappe.ValidationError):
			discovery.adopt_discovered_peer(serial)

	def test_list_discoverable_includes_heartbeat_peer(self):
		serial = f"HB-D-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		rows = discovery.list_discoverable()
		serials = [r["serial_number"] for r in rows]
		self.assertIn(serial, serials)

	def test_list_discoverable_includes_handshake_peer(self):
		serial = f"HS-D-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "cdata", "GET", {"SN": serial, "options": "all"})
		rows = discovery.list_discoverable()
		self.assertIn(serial, [r["serial_number"] for r in rows])

	def test_list_discoverable_excludes_ping_only_peer(self):
		serial = f"PG-D-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "ping", "GET", {"SN": serial})
		rows = discovery.list_discoverable()
		self.assertNotIn(serial, [r["serial_number"] for r in rows])

	def test_adopt_backfills_init_from_handshake_peer(self):
		serial = f"BF-{frappe.generate_hash(length=6)}"
		peers.record_contact(
			serial, "cdata", "GET", {"SN": serial, "options": "all", "pushver": "2.4.1"}
		)
		result = discovery.adopt_discovered_peer(serial)
		machine = frappe.db.get_value(
			"TimeBridge Machine",
			result["machine"],
			["adms_last_init_at", "adms_pushver"],
			as_dict=True,
		)
		self.assertTrue(machine.adms_last_init_at)
		self.assertEqual(machine.adms_pushver, "2.4.1")

	def test_timezone_minutes_for_ist(self):
		with patch("frappe.utils.get_system_timezone", return_value="Asia/Kolkata"):
			self.assertEqual(handshake.server_timezone_option(), "330")
		with patch("frappe.utils.get_system_timezone", return_value="UTC"):
			self.assertEqual(handshake.server_timezone_option(), "0")

	def test_transflag_empty_is_not_format_i_zeros(self):
		line = transflag_line({})
		self.assertEqual(line, "TransFlag=TransData")
		self.assertNotIn("0000000000", line)

	def test_ack_counts_records(self):
		self.assertEqual(handshake.ack(9), "OK: 9")
		self.assertEqual(handshake.ack(0), "OK: 0")


class TestAdmsConsole(FrappeTestCase):
	def setUp(self):
		enable_server(1)

	def tearDown(self):
		enable_server(0)
		clear_server_enabled_cache()

	def test_unknown_contact_creates_peer_not_machine(self):
		serial = f"UNK-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		self.assertTrue(frappe.db.exists("TimeBridge ADMS Peer", {"serial_number": serial}))
		self.assertFalse(frappe.db.exists("TimeBridge Machine", {"serial_number": serial}))

	def test_heartbeat_log_disabled_by_default(self):
		frappe.db.set_single_value("TimeBridge Settings", "log_adms_heartbeat", 0)
		frappe.db.set_single_value("TimeBridge Settings", "log_adms_ping", 0)
		clear_server_enabled_cache()
		self.assertFalse(log_category_enabled("Heartbeat"))
		self.assertFalse(log_category_enabled("Ping"))

	def test_heartbeat_not_written_when_disabled(self):
		frappe.db.set_single_value("TimeBridge Settings", "log_adms_heartbeat", 0)
		clear_server_enabled_cache()
		serial = f"HB-{frappe.generate_hash(length=6)}"
		from timebridge.timebridge.iclock.audit import write_log

		write_log(serial, "getrequest", "GET", {"SN": serial}, response="OK")
		self.assertFalse(
			frappe.db.exists("TimeBridge ADMS Log", {"serial_number": serial, "category": "Heartbeat"})
		)

	def test_peer_reboot_delivered_on_getrequest(self):
		serial = f"RB-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		peers.queue_serial_command(serial, "REBOOT")
		reply = handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")
		self.assertIn("REBOOT", reply)

	def test_device_command_requires_registered(self):
		serial = f"DC-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		from timebridge.timebridge.iclock.api import queue_device_command

		with self.assertRaises(frappe.ValidationError):
			queue_device_command(name, "INFO")

	def test_pending_peer_reboot_before_register(self):
		serial = f"PR-{frappe.generate_hash(length=6)}"
		create_pending(serial)
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		peers.queue_serial_command(serial, "REBOOT")
		reply = handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")
		self.assertIn("REBOOT", reply)

	def test_list_roster_includes_last_seen_at(self):
		serial = f"LS-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		rows = peers.list_roster()
		match = [r for r in rows if r["serial_number"] == serial]
		self.assertEqual(len(match), 1)
		self.assertTrue(match[0]["last_seen_at"])

	def test_dismiss_peer_removes_unknown(self):
		serial = f"DS-{frappe.generate_hash(length=6)}"
		peers.record_contact(serial, "getrequest", "GET", {"SN": serial})
		peer = frappe.db.get_value("TimeBridge ADMS Peer", {"serial_number": serial}, "name")
		peers.dismiss_peer(serial=serial)
		self.assertFalse(frappe.db.exists("TimeBridge ADMS Peer", peer))

	def test_info_request_progress(self):
		from timebridge.timebridge.iclock import stats

		serial = f"INF-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		queued = commands.start_info_request(name)
		cmd_id = queued["command_id"]
		self.assertEqual(commands.info_progress(name, cmd_id)["phase"], "queued")

		cmd_name = frappe.db.get_value(
			"TimeBridge Device Command",
			{"machine": name, "command_id": cmd_id},
			"name",
		)
		frappe.db.set_value("TimeBridge Device Command", cmd_name, "status", "Sent")
		stats.apply_info_command_body(name, "UserCount=5\tTransactionCount=10\tFWVersion=1.0")

		done = commands.info_progress(name, cmd_id)
		self.assertEqual(done["phase"], "done")
		self.assertEqual(done["info"].get("Users"), 5)
		self.assertEqual(done["info"].get("Attendance records"), 10)
		self.assertEqual(done["info"].get("Firmware"), "1.0")


class TestIclockParser(FrappeTestCase):
	def test_attlog_basic(self):
		from timebridge.timebridge.iclock.parser import parse_attlog

		records, skipped = parse_attlog(
			"1\t2026-07-30 10:05:12\t0\t1\t0\t0\n2\t2026-07-30 19:02:44\t1\t15\t0\t0"
		)
		self.assertEqual(len(records), 2)
		self.assertEqual(skipped, [])
		self.assertEqual(records[0]["punch_direction"], "In")
		self.assertEqual(records[1]["verify_mode"], "Face")

	def test_attlog_does_not_strip_leading_tab(self):
		from timebridge.timebridge.iclock.parser import parse_attlog

		records, skipped = parse_attlog("\t2026-07-30 10:00:00\t0")
		self.assertEqual(records, [])
		self.assertEqual(len(skipped), 1)

	def test_querydata_users(self):
		from timebridge.timebridge.iclock.parser import parse_querydata_users

		body = (
			"user uid=1 cardno= pin=1000 password= group=1 starttime=0 endtime=0 "
			"name=Asha privilege=0 disable=0 verify=0\n"
		)
		records, skipped = parse_querydata_users(body)
		self.assertEqual(skipped, [])
		self.assertEqual(records[0]["user_id"], "1000")
		self.assertEqual(records[0]["user_name"], "Asha")

	def test_userinfo(self):
		from timebridge.timebridge.iclock.parser import parse_userinfo

		records, skipped = parse_userinfo("PIN=5\tName=Asha\tPri=0\tCard=99")
		self.assertEqual(skipped, [])
		self.assertEqual(records[0]["user_id"], "5")
		self.assertEqual(records[0]["user_name"], "Asha")

	def test_photo_fields_operlog_biophoto_prefix(self):
		from timebridge.timebridge.iclock.parser import parse_photo_fields

		content = "A" * 100
		body = f"BIOPHOTO PIN=37\tFileName=37.jpg\tType=9\tContent={content}"
		records = parse_photo_fields(body)
		self.assertEqual(len(records), 1)
		self.assertEqual(records[0]["user_id"], "37")
		self.assertEqual(records[0]["content"], content)

	def test_command_wire_format(self):
		self.assertEqual(
			commands.request_users(),
			"DATA QUERY USERINFO",
		)
		self.assertEqual(
			commands.format_commands(
				[{"id": 3, "command": commands.request_users()}]
			),
			"C:3:DATA QUERY USERINFO",
		)
		self.assertEqual(commands.format_commands([]), "OK")


class TestAdmsCommandLab(FrappeTestCase):
	def test_normalize_raw_command_strips_prefix(self):
		from timebridge.timebridge.iclock.debug_feed import normalize_raw_command

		self.assertEqual(
			normalize_raw_command("C:9:DATA QUERY USERINFO"),
			"DATA QUERY USERINFO",
		)
		self.assertEqual(normalize_raw_command("  INFO  "), "INFO")

	def test_queue_raw_command_requires_registered(self):
		from timebridge.timebridge.iclock.api import queue_raw_command

		serial = f"LAB-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		with self.assertRaises(frappe.ValidationError):
			queue_raw_command(name, "INFO")

	def test_queue_requires_started_session(self):
		from timebridge.timebridge.iclock.api import queue_raw_command

		serial = f"LAB-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		with self.assertRaises(frappe.ValidationError):
			queue_raw_command(name, "INFO")

	def test_queue_and_poll_debug_feed(self):
		from timebridge.timebridge.iclock import lab_session
		from timebridge.timebridge.iclock.api import (
			poll_debug_feed,
			queue_raw_command,
			start_lab_session,
		)

		serial = f"LAB-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)

		started = start_lab_session(name)
		self.assertTrue(started["scrap_mode"])

		queued = queue_raw_command(name, "C:5:INFO")
		self.assertEqual(queued["command"], "INFO")
		self.assertTrue(queued["command_id"])
		self.assertTrue(queued["scrap_mode"])
		self.assertFalse(
			frappe.db.exists(
				"TimeBridge Device Command",
				{"machine": name, "command_id": queued["command_id"]},
			)
		)

		lab_session.handle_scrap_request(
			serial,
			"devicecmd",
			{"SN": serial},
			f"ID={queued['command_id']}&Return=0&CMD=DATA",
			"POST",
		)

		feed = poll_debug_feed(
			name,
			since=queued["queued_at"],
			command_id=queued["command_id"],
		)
		self.assertTrue(feed["scrap_mode"])
		self.assertEqual(feed["command"]["status"], "Done")
		self.assertTrue(feed["logs"])
		self.assertEqual(feed["parsed_devicecmd"][0]["return_code"], "0")
		self.assertEqual(feed["parsed_devicecmd"][0]["return_label"], "0 (OK)")

	def test_lab_scrap_skips_user_ingest_and_adms_log(self):
		from timebridge.timebridge.iclock.api import (
			poll_debug_feed,
			queue_raw_command,
			start_lab_session,
		)
		from timebridge.timebridge.iclock import lab_session

		enable_server(1)
		serial = f"LS-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		start_lab_session(name)
		queue_raw_command(name, "DATA QUERY USERINFO")

		before_users = frappe.db.count("TimeBridge Machine User", {"machine": name})
		before_logs = frappe.db.count("TimeBridge ADMS Log", {"machine": name})

		reply = lab_session.handle_scrap_request(
			serial,
			"cdata",
			{"SN": serial, "table": "USERINFO", "OpStamp": "1"},
			"PIN=1\tName=One\tPri=0\n",
			"POST",
		)
		self.assertEqual(reply, "OK: 1")
		self.assertEqual(
			frappe.db.count("TimeBridge Machine User", {"machine": name}), before_users
		)
		self.assertEqual(
			frappe.db.count("TimeBridge ADMS Log", {"machine": name}), before_logs
		)

		feed = poll_debug_feed(name)
		self.assertTrue(feed["scrap_mode"])
		self.assertEqual(len(feed["logs"]), 1)
		self.assertIn("PIN=1", feed["logs"][0]["body_preview"])

	def test_lab_queue_survives_and_is_delivered_on_getrequest(self):
		from timebridge.timebridge.iclock.api import queue_raw_command, start_lab_session
		from timebridge.timebridge.iclock import lab_session

		enable_server(1)
		serial = f"LQ-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		start_lab_session(name)

		first = queue_raw_command(name, "INFO")
		second = queue_raw_command(name, "DATA QUERY USERINFO")
		self.assertEqual(second["pending_commands"], 2)

		reply = lab_session.handle_scrap_request(
			serial, "getrequest", {"SN": serial}, "", "GET"
		)
		self.assertIn(f"C:{first['command_id']}:INFO", reply)
		self.assertIn(f"C:{second['command_id']}:DATA QUERY USERINFO", reply)
		self.assertEqual(lab_session.pending_lab_command_count(name), 0)

		# A second poll must not re-send — queue was emptied on first getrequest.
		again = lab_session.handle_scrap_request(
			serial, "getrequest", {"SN": serial}, "", "GET"
		)
		self.assertEqual(again, "OK")

	def test_stop_lab_session_clears_scrap_and_queues_reboot(self):
		from timebridge.timebridge.iclock.api import (
			queue_raw_command,
			start_lab_session,
			stop_lab_session,
		)

		enable_server(1)
		serial = f"ST-{frappe.generate_hash(length=6)}"
		name = create_pending(serial)
		handlers.handle_cdata(serial, {"SN": serial, "options": "all"}, "", "GET")
		discovery.register_machine(name)
		start_lab_session(name)
		queue_raw_command(name, "CHECK")

		stopped = stop_lab_session(name, reboot=1)
		self.assertFalse(stopped["scrap_mode"])
		self.assertEqual(stopped["pending_cleared"], 1)
		self.assertTrue(stopped["reboot_queued"])

		from timebridge.timebridge.iclock import lab_session

		self.assertFalse(lab_session.is_active(name))

		reboot = frappe.db.get_value(
			"TimeBridge Device Command",
			{"machine": name, "command_id": stopped["reboot_command_id"]},
			["command", "status"],
			as_dict=True,
		)
		self.assertEqual(reboot.command, "REBOOT")
		self.assertEqual(reboot.status, "Queued")

		# Normal getrequest now delivers the reboot (scrap mode off).
		reply = handlers.handle_getrequest(serial, {"SN": serial}, "", "GET")
		self.assertIn("REBOOT", reply)
