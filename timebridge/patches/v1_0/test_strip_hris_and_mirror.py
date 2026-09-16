# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.patches.v1_0 import strip_hris_and_mirror as strip


class TestStripHrisAndMirror(FrappeTestCase):
	DOCTYPE = "TB Strip Guard Employee"

	def setUp(self):
		self._scrub()

	def tearDown(self):
		self._scrub()

	def test_execute_does_not_delete_doctypes_with_data(self):
		"""Regression: old strip_hris deleted TimeBridge Employee and dropped its table."""
		doc = frappe.get_doc(
			{
				"doctype": "DocType",
				"name": self.DOCTYPE,
				"module": "TimeBridge",
				"custom": 1,
				"fields": [{"label": "Title", "fieldname": "title", "fieldtype": "Data"}],
				"permissions": [{"role": "System Manager", "read": 1, "write": 1, "create": 1}],
			}
		)
		doc.insert()
		row = frappe.get_doc({"doctype": self.DOCTYPE, "title": "keep-me"}).insert()
		frappe.db.commit()

		original = list(strip.DISCONTINUED_DOCTYPES)
		strip.DISCONTINUED_DOCTYPES = [self.DOCTYPE]
		try:
			strip.execute()
		finally:
			strip.DISCONTINUED_DOCTYPES = original

		self.assertTrue(frappe.db.exists("DocType", self.DOCTYPE))
		self.assertTrue(frappe.db.exists(self.DOCTYPE, row.name))
		self.assertEqual(frappe.db.get_value(self.DOCTYPE, row.name, "title"), "keep-me")

	def test_delete_meta_refuses_doctype(self):
		strip._delete_meta("DocType", "Employee")
		self.assertTrue(frappe.db.exists("DocType", "Employee"))

	def _scrub(self):
		if frappe.db.exists("DocType", self.DOCTYPE):
			frappe.db.sql(f"DELETE FROM `tab{self.DOCTYPE}`")
			frappe.delete_doc("DocType", self.DOCTYPE, force=1)
		if frappe.db.table_exists(self.DOCTYPE):
			frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{self.DOCTYPE}`")
		frappe.db.commit()
