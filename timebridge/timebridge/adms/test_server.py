# Copyright (c) 2026, UPGO and Contributors
# See license.txt

from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.adms.server import web_port


class TestADMSServer(FrappeTestCase):

    def test_web_port_from_bench_config(self):
        self.assertEqual(web_port(), 80)
