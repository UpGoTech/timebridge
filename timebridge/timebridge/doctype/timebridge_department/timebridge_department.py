# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class TimeBridgeDepartment(Document):
# 	pass

import frappe
from frappe.model.document import Document


class TimeBridgeDepartment(Document):
    def validate(self):
        self.validate_duplicate_code()

    def validate_duplicate_code(self):
        if frappe.db.exists(
            "TimeBridge Department",
            {
                "branch": self.branch,
                "department_code": self.department_code,
                "name": ["!=", self.name]
            }
        ):
            frappe.throw(
                f"TimeBridge Department Code '{self.department_code}' already exists in this TimeBridge Branch."
            )


