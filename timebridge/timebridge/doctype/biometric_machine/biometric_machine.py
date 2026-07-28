# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class BiometricMachine(Document):
# 	pass

from frappe.model.document import Document
import ipaddress
import frappe


class BiometricMachine(Document):

    def validate(self):
        self.validate_ip()
        self.validate_port()

    def validate_ip(self):
        if self.ip_address:
            try:
                ipaddress.ip_address(self.ip_address)
            except ValueError:
                frappe.throw("Please enter a valid IP Address.")

    def validate_port(self):
        if self.port and (self.port < 1 or self.port > 65535):
            frappe.throw("Port must be between 1 and 65535.")




