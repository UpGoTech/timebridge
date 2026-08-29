# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms import parser
from timebridge.timebridge.services.biometric_templates import normalize_bio_type, upsert_template


class TestBiometricTemplates(FrappeTestCase):
	def test_normalize_bio_type_sdk_index(self):
		self.assertEqual(normalize_bio_type("1"), "Fingerprint")
		self.assertEqual(normalize_bio_type("9"), "Face")

	def test_parse_templatev10_line(self):
		body = "Pin=101\tFingerID=2\tTemplate=BASE64DATA\tSize=512\tValid=1"
		records, skipped = parser.parse_templatev10(body)
		self.assertEqual(len(records), 1)
		self.assertEqual(records[0]["user_id"], "101")
		self.assertEqual(records[0]["template_index"], "2")

	def test_parse_biodata_line(self):
		body = "pin=55\ttype=9\tindex=0\ttmp=FACEDATA\tmajorver=10"
		records, skipped = parser.parse_biodata(body)
		self.assertEqual(len(records), 1)
		self.assertEqual(records[0]["user_id"], "55")
		self.assertEqual(records[0]["bio_type"], "9")

	def test_parse_options(self):
		body = "UserCount=100\nFPCount=200\nFaceCount=50\nTransactionCount=9999"
		opts = parser.parse_options(body)
		self.assertEqual(opts["users"], 100)
		self.assertEqual(opts["fingerprints"], 200)
		self.assertEqual(opts["faces"], 50)
		self.assertEqual(opts["punches_total"], 9999)

	def test_upsert_template_dedup(self):
		machine = self._ensure_machine()

		upsert_template(
			machine,
			"42",
			"Fingerprint",
			0,
			"TEMPLATE_A",
			source="ADMS Push",
			source_table="templatev10",
		)
		upsert_template(
			machine,
			"42",
			"Fingerprint",
			0,
			"TEMPLATE_B",
			source="ADMS Push",
			source_table="templatev10",
		)

		count = frappe.db.count(
			"TimeBridge Biometric Template",
			{"machine": machine, "user_id": "42", "bio_type": "Fingerprint", "template_index": 0},
		)
		self.assertEqual(count, 1)

		data = frappe.db.get_value(
			"TimeBridge Biometric Template",
			{"machine": machine, "user_id": "42"},
			"template_data",
		)
		self.assertEqual(data, "TEMPLATE_B")

	def _ensure_machine(self):
		name = frappe.db.get_value("TimeBridge Machine", {"machine_id": "MIRROR-TEST"}, "name")

		if name:
			return name

		doc = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": "MIRROR-TEST",
				"machine_name": "Mirror Test",
				"device_brand": "ZKTeco",
				"ip_address": "192.168.1.99",
				"port": 4370,
				"sdk_type": "PyZK",
			}
		)
		doc.insert(ignore_permissions=True)
		return doc.name
