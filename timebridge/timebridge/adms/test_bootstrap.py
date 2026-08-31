# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from unittest.mock import patch

from timebridge.timebridge.adms.sync import bootstrap


class TestADMSBootstrap(FrappeTestCase):
	@patch("timebridge.timebridge.adms.sync.bootstrap.commands.start_enroll_photo_fetch")
	@patch("timebridge.timebridge.adms.sync.bootstrap.commands.queue_command")
	def test_queue_initial_sync(self, mock_queue, mock_photos):
		mock_queue.return_value = "CMD-1"

		machine = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": "BOOT-008",
				"machine_name": "Bootstrap Test",
				"device_brand": "ZKTeco",
				"serial_number": "BOOT-SN-008",
				"ip_address": "192.168.1.3",
				"sdk_type": "ADMS",
			}
		).insert()

		result = bootstrap.queue_initial_sync(machine.name)
		self.assertEqual(result["status"], "Queued")
		self.assertEqual(mock_queue.call_count, 2)
		mock_photos.assert_called_once_with(machine.name)

		status = frappe.db.get_value("TimeBridge Machine", machine.name, "adms_bootstrap_status")
		self.assertEqual(status, "Queued")

		machine.delete()
