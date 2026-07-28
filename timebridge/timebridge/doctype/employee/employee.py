# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class Employee(Document):
# 	pass

import frappe
from frappe.model.document import Document


class Employee(Document):

    def validate(self):
        self.validate_duplicate_employee_code()

    def validate_duplicate_employee_code(self):
        if frappe.db.exists(
            "Employee",
            {
                "employee_code": self.employee_code,
                "name": ["!=", self.name]
            }
        ):
            frappe.throw(
                f"Employee Code '{self.employee_code}' already exists."
            )



