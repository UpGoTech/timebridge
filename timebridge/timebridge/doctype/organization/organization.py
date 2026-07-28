# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class Organization(Document):
# 	pass

import frappe
from frappe.model.document import Document


class Organization(Document):
    def validate(self):
        self.validate_duplicate_code()

    def validate_duplicate_code(self):
        if frappe.db.exists(
            "Organization",
            {
                "organization_code": self.organization_code,
                "name": ["!=", self.name]
            }
        ):
            frappe.throw(
                f"Organization Code '{self.organization_code}' already exists."
            )



