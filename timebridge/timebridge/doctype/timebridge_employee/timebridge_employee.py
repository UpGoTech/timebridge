# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class TimeBridgeEmployee(Document):
	def validate(self):
		self.set_full_name()
		self.validate_duplicate_employee_code()

	def set_full_name(self):
		self.employee = " ".join(
			part for part in (self.first_name, self.middle_name, self.last_name) if part
		)

	def validate_duplicate_employee_code(self):
		if frappe.db.exists(
			"TimeBridge Employee",
			{
				"employee_code": self.employee_code,
				"name": ["!=", self.name],
			},
		):
			frappe.throw(
				f"TimeBridge Employee Code '{self.employee_code}' already exists."
			)
