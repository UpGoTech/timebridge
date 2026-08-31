# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms import photos


class TestADMSPhotoSave(FrappeTestCase):
	def test_save_photo_attaches_to_machine_user(self):
		machine = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine",
				"machine_id": "PHOTO-008",
				"machine_name": "Photo Test",
				"device_brand": "ZKTeco",
				"serial_number": "PHOTO-SN-008",
				"ip_address": "192.168.1.2",
				"sdk_type": "ADMS",
			}
		).insert()

		mu = frappe.get_doc(
			{
				"doctype": "TimeBridge Machine User",
				"machine": machine.name,
				"user_id": "42",
				"user_name": "User 42",
				"is_active": 1,
			}
		).insert()

		jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 20

		mock_file = MagicMock()
		mock_file.file_url = "/files/test-42.jpg"
		mock_file.insert = MagicMock(return_value=mock_file)

		with patch.object(photos.frappe, "get_doc", return_value=mock_file):
			url = photos.save_photo(machine.name, "42", jpeg, "USERPIC")

		self.assertEqual(url, "/files/test-42.jpg")
		self.assertEqual(
			frappe.db.get_value("TimeBridge Machine User", mu.name, "photo"),
			"/files/test-42.jpg",
		)
		self.assertEqual(
			frappe.db.get_value("TimeBridge Machine User", mu.name, "face_registered"),
			1,
		)

		frappe.delete_doc("TimeBridge Machine User", mu.name, force=True)
		machine.delete()
