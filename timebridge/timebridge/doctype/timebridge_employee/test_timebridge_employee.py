# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestTimeBridgeEmployee(FrappeTestCase):
	def test_full_name_joins_name_parts(self):
		doc = frappe.new_doc("TimeBridge Employee")
		doc.first_name = "Asha"
		doc.middle_name = "K"
		doc.last_name = "Patil"
		doc.set_full_name()
		self.assertEqual(doc.employee, "Asha K Patil")

	def test_full_name_skips_empty_parts(self):
		doc = frappe.new_doc("TimeBridge Employee")
		doc.first_name = "Vina"
		doc.set_full_name()
		self.assertEqual(doc.employee, "Vina")
