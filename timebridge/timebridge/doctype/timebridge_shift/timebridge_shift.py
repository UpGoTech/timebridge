# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class TimeBridgeShift(Document):
# 	pass


import frappe
from frappe.model.document import Document


class TimeBridgeShift(Document):
    def validate(self):
        self.validate_duplicate_code()

    def validate_duplicate_code(self):
        if frappe.db.exists(
            "TimeBridge Shift",
            {
                "organization": self.organization,
                "shift_code": self.shift_code,
                "name": ["!=", self.name]
            }
        ):
            frappe.throw(
                f"TimeBridge Shift Code '{self.shift_code}' already exists."
            )



