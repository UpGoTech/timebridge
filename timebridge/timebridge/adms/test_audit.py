# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms.ingress import audit


class TestADMSRequestLogAudit(FrappeTestCase):
	def setUp(self):
		super().setUp()
		frappe.db.delete("TimeBridge ADMS Request Log")

	def test_classify_attlog(self):
		self.assertEqual(
			audit.classify("cdata", "POST", {"table": "ATTLOG"}),
			"Attendance",
		)

	def test_unknown_serial_always_logs(self):
		audit.write_request_log(
			serial="UNKNOWN-SN-008",
			endpoint="getrequest",
			method="GET",
			args={"SN": "UNKNOWN-SN-008"},
			response="OK",
		)
		self.assertEqual(
			frappe.db.count("TimeBridge ADMS Request Log", {"serial_number": "UNKNOWN-SN-008"}),
			1,
		)

	def test_registered_machine_respects_heartbeat_toggle(self):
		machine = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": "AUDIT-008",
				"machine_name": "Audit Test",
				"device_brand": "ZKTeco",
				"serial_number": "AUDIT-SN-008",
				"ip_address": "192.168.1.1",
				"sdk_type": "ADMS",
				"log_adms_heartbeat": 0,
				"log_adms_attendance": 1,
			}
		).insert()

		audit.write_request_log(
			serial="AUDIT-SN-008",
			endpoint="getrequest",
			method="GET",
			args={"SN": "AUDIT-SN-008"},
			response="OK",
		)
		self.assertEqual(
			frappe.db.count("TimeBridge ADMS Request Log", {"machine": machine.name}),
			0,
		)

		audit.write_request_log(
			serial="AUDIT-SN-008",
			endpoint="cdata",
			method="POST",
			args={"SN": "AUDIT-SN-008", "table": "ATTLOG"},
			body="1\t2026-01-01 09:00:00\t0\t1\t0\t0\t0",
			response="OK: 1",
		)
		self.assertEqual(
			frappe.db.count(
				"TimeBridge ADMS Request Log",
				{"machine": machine.name, "category": "Attendance"},
			),
			1,
		)

		machine.delete()
