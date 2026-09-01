# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

# import frappe
# from frappe.model.document import Document


# class TimeBridgeSettings(Document):
# 	pass

from frappe.model.document import Document
import frappe


class TimeBridgeSettings(Document):

    def validate(self):
        self.validate_values()

    def validate_values(self):
        if self.default_port < 1 or self.default_port > 65535:
            frappe.throw("Default Port must be between 1 and 65535.")

        if self.connection_timeout < 1:
            frappe.throw("Connection Timeout must be greater than 0.")

        if self.retry_count < 0:
            frappe.throw("Retry Count cannot be negative.")

        if self.sync_interval < 1:
            frappe.throw("Sync Interval must be at least 1 minute.")

    def on_update(self):
        from timebridge.timebridge.iclock.server import clear_server_enabled_cache

        clear_server_enabled_cache()


