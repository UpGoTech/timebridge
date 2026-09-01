# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import now_datetime

from timebridge.timebridge.services.device_records import save_users
from timebridge.timebridge.report.device_roll.device_roll import build_rows
from timebridge.timebridge.services.user_write import create_users, upsert_local_user


class TestDeskOwnedUsersAndRoll(FrappeTestCase):
	def setUp(self):
		self.tag = frappe.generate_hash(length=8)
		self.machine = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": f"TEST-003-{self.tag}",
				"machine_name": f"Test IO {self.tag}",
				"device_brand": "ZKTeco",
				"ip_address": "127.0.0.1",
				"port": 4370,
				"sdk_type": "ADMS",
				"serial_number": f"SN-003-{self.tag}",
			}
		).insert()

	def test_inbound_userinfo_does_not_overwrite_desk_name(self):
		name, created = upsert_local_user(
			self.machine.name, "12", "Desk Name", privilege="User"
		)
		self.assertTrue(created)
		save_users(
			self.machine.name,
			[{"user_id": "12", "user_name": "Device Name", "privilege": "Admin", "card_number": "1"}],
		)
		row = frappe.db.get_value(
			"TimeBridge Machine User",
			name,
			["user_name", "privilege", "card_number"],
			as_dict=True,
		)
		self.assertEqual(row.user_name, "Desk Name")
		self.assertEqual(row.privilege, "User")

	def test_inbound_creates_unknown_pin(self):
		save_users(
			self.machine.name,
			[{"user_id": "99", "user_name": "New Person", "privilege": "User"}],
		)
		self.assertTrue(
			frappe.db.exists(
				"TimeBridge Machine User",
				{"machine": self.machine.name, "user_id": "99"},
			)
		)

	def test_fan_out_skips_existing_pin(self):
		upsert_local_user(self.machine.name, "12", "Asha")
		result = create_users("12", "Asha", [self.machine.name])
		self.assertTrue(result["results"][0]["skipped"])

	def test_roll_yes_no(self):
		upsert_local_user(self.machine.name, "12", "Asha")
		upsert_local_user(self.machine.name, "13", "Absent PIN")
		frappe.get_doc(
			{
				"doctype": "TimeBridge Punch Log",
				"machine": self.machine.name,
				"device_user_id": "12",
				"timestamp": now_datetime(),
				"source": "ADMS Push",
			}
		).insert()
		today = frappe.utils.today()
		rows = {r["user_id"]: r for r in build_rows(self.machine.name, today, today)}
		self.assertEqual(rows["12"]["punched"], "Yes")
		self.assertEqual(rows["13"]["punched"], "No")
