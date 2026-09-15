# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.patches.v1_0.rename_conflicting_doctypes import _rename_if_ours
from timebridge.patches.v1_0.repair_foreign_link_options_after_rename import (
	_repair_foreign_rewrites,
)


class TestRenameConflictingDoctypes(FrappeTestCase):
	"""frappe.rename_doc rewrites Link options site-wide; our patch must not."""

	OLD = "TB Rename Conflict Old"
	NEW = "TB Rename Conflict New"
	FOREIGN = "TB Rename Foreign Holder"
	OWNED = "TB Rename Owned Holder"

	def setUp(self):
		self._scrub()

	def tearDown(self):
		self._scrub()

	def test_rename_preserves_foreign_link_options(self):
		self._make_doctype(
			self.OLD,
			module="TimeBridge",
			fields=[{"label": "Title", "fieldname": "title", "fieldtype": "Data"}],
		)
		self._make_doctype(
			self.FOREIGN,
			module="Core",
			fields=[
				{
					"label": "Link",
					"fieldname": "tb_link",
					"fieldtype": "Link",
					"options": self.OLD,
				}
			],
		)
		self._make_doctype(
			self.OWNED,
			module="TimeBridge",
			fields=[
				{
					"label": "Link",
					"fieldname": "tb_link",
					"fieldtype": "Link",
					"options": self.OLD,
				}
			],
		)

		_rename_if_ours(self.OLD, self.NEW)

		self.assertTrue(frappe.db.exists("DocType", self.NEW))
		self.assertFalse(frappe.db.exists("DocType", self.OLD))
		self.assertEqual(
			frappe.db.get_value(
				"DocField", {"parent": self.FOREIGN, "fieldname": "tb_link"}, "options"
			),
			self.OLD,
		)
		self.assertEqual(
			frappe.db.get_value(
				"DocField", {"parent": self.OWNED, "fieldname": "tb_link"}, "options"
			),
			self.NEW,
		)

	def test_repair_restores_already_rewritten_foreign_options(self):
		"""Sites that already ran the old rename patch need a one-shot repair."""
		self._make_doctype(
			self.NEW,
			module="TimeBridge",
			fields=[{"label": "Title", "fieldname": "title", "fieldtype": "Data"}],
		)
		self._make_doctype(
			self.FOREIGN,
			module="Core",
			fields=[
				{
					"label": "Link",
					"fieldname": "tb_link",
					"fieldtype": "Link",
					"options": self.NEW,
				}
			],
		)
		self._make_doctype(
			self.OWNED,
			module="TimeBridge",
			fields=[
				{
					"label": "Link",
					"fieldname": "tb_link",
					"fieldtype": "Link",
					"options": self.NEW,
				}
			],
		)

		_repair_foreign_rewrites(self.OLD, self.NEW)

		self.assertEqual(
			frappe.db.get_value(
				"DocField", {"parent": self.FOREIGN, "fieldname": "tb_link"}, "options"
			),
			self.OLD,
		)
		self.assertEqual(
			frappe.db.get_value(
				"DocField", {"parent": self.OWNED, "fieldname": "tb_link"}, "options"
			),
			self.NEW,
		)

	def _scrub(self):
		for name in (self.NEW, self.OLD, self.FOREIGN, self.OWNED):
			if frappe.db.exists("DocType", name):
				frappe.delete_doc("DocType", name, force=1)
			table = f"tab{name}"
			if frappe.db.table_exists(name):
				frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `{table}`")
		frappe.db.commit()

	def _make_doctype(self, name, module, fields):
		doc = frappe.get_doc(
			{
				"doctype": "DocType",
				"name": name,
				"module": module,
				"custom": 1,
				"fields": fields,
				"permissions": [{"role": "System Manager", "read": 1}],
			}
		)
		doc.insert()
		return doc
