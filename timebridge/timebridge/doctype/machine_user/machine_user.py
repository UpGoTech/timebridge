# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class MachineUser(Document):
# 	pass

import frappe
from frappe.model.document import Document

class MachineUser(Document):
    def validate(self):
        self.validate_duplicate_user()

    def validate_duplicate_user(self):
        if frappe.db.exists(
            "Machine User",
            {
                "machine": self.machine,
                "user_id": self.user_id,
                "name": ["!=", self.name]
            }
        ):
            frappe.throw(
                f"User ID '{self.user_id}' already exists for this machine."
            )


