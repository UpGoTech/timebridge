# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.iclock import commands, discovery, handshake, handlers, peers
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
	)["machine"]


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
		self.assertFalse(any("QUERY USERINFO" in (c or "") for c in queued))

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
		self.assertNotIn("USERINFO", queued["queued"])

	def test_create_pending_machine(self):
		serial = f"ADD-{frappe.generate_hash(length=6)}"
		result = discovery.create_pending_machine(serial, serial, serial)
		self.assertTrue(frappe.db.exists("TimeBridge Machine", result["machine"]))
		self.assertEqual(
			frappe.db.get_value("TimeBridge Machine", result["machine"], "adms_status"),
			"Pending",
		)
		with self.assertRaises(frappe.ValidationError):
			discovery.create_pending_machine(serial, f"{serial}-2", serial)

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

	def test_userinfo(self):
		from timebridge.timebridge.iclock.parser import parse_userinfo

		records, skipped = parse_userinfo("PIN=5\tName=Asha\tPri=0\tCard=99")
		self.assertEqual(skipped, [])
		self.assertEqual(records[0]["user_id"], "5")
		self.assertEqual(records[0]["user_name"], "Asha")

	def test_command_wire_format(self):
		self.assertEqual(
			commands.format_commands([{"id": 3, "command": "DATA QUERY USERINFO"}]),
			"C:3:DATA QUERY USERINFO",
		)
		self.assertEqual(commands.format_commands([]), "OK")
