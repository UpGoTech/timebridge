# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import unittest

from timebridge.timebridge.adms import parser


class TestTemplateParser(unittest.TestCase):
	def test_parse_count_response(self):
		self.assertEqual(parser.parse_count_response("count=42"), 42)
		self.assertEqual(parser.parse_count_response("128"), 128)

	def test_is_template_table(self):
		self.assertTrue(parser.is_template_table({"tablename": "biodata"}, "TABLEDATA"))
		self.assertTrue(parser.is_template_table({}, "TEMPLATEV10"))

	def test_parse_options_tab_separated(self):
		body = "UserCount=10\tFPCount=20\tFaceCount=5"
		opts = parser.parse_options(body)
		self.assertEqual(opts["users"], 10)
		self.assertEqual(opts["fingerprints"], 20)
