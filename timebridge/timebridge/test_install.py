# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import importlib.util

from frappe.tests.utils import FrappeTestCase

from timebridge.install import ensure_pyzk


class TestInstall(FrappeTestCase):

	def test_ensure_pyzk_noop_when_installed(self):
		self.assertIsNotNone(importlib.util.find_spec("zk"))
		ensure_pyzk()
