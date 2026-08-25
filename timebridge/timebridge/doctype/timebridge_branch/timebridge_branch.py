# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class TimeBridgeBranch(Document):
# 	pass

import frappe
from frappe.model.document import Document


class TimeBridgeBranch(Document):
    def validate(self):
        self.validate_duplicate_code()

    def validate_duplicate_code(self):
        if frappe.db.exists(
            "TimeBridge Branch",
            {
                "organization": self.organization,
                "branch_code": self.branch_code,
                "name": ["!=", self.name]
            }
        ):
            frappe.throw(
                f"TimeBridge Branch Code '{self.branch_code}' already exists in this TimeBridge Organization."
            )

