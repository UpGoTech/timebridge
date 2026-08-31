# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms.commands import (
	format_commands,
	format_userinfo_delete,
	format_userinfo_update,
)


class TestUserinfoCommands(FrappeTestCase):
	def test_update_payload_tabs_and_privilege(self):
		cmd = format_userinfo_update("12", "Asha", privilege="User", password="", card="99")
		self.assertTrue(cmd.startswith("DATA UPDATE USERINFO "))
		self.assertIn("PIN=12", cmd)
		self.assertIn("Name=Asha", cmd)
		self.assertIn("Pri=0", cmd)
		self.assertIn("Card=99", cmd)
		self.assertIn("\t", cmd)

	def test_admin_privilege(self):
		cmd = format_userinfo_update("1", "Boss", privilege="Admin")
		self.assertIn("Pri=14", cmd)

	def test_delete_payload(self):
		self.assertEqual(format_userinfo_delete("12"), "DATA DELETE USERINFO PIN=12")

	def test_format_empty_is_ok(self):
		self.assertEqual(format_commands([]), "OK")

	def test_format_wire_line(self):
		self.assertEqual(
			format_commands([{"id": 3, "command": "DATA QUERY USERINFO"}]),
			"C:3:DATA QUERY USERINFO",
		)
