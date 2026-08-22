# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe

from frappe.model.document import Document
from frappe.utils import getdate


ATTENDANCE_KEY_SEPARATOR = "::"


class TimeBridgeAttendance(Document):

    def before_insert(self):
        self.set_attendance_key()

    def validate(self):
        self.set_attendance_key()
        self.validate_timing()

    def set_attendance_key(self):
        """
        One row per employee per day. Derivation reruns over the same punches
        whenever a late punch arrives, so this key is what turns a rerun into
        an update instead of a duplicate day.
        """

        if not (self.employee and self.attendance_date):
            return

        self.attendance_key = ATTENDANCE_KEY_SEPARATOR.join([
            self.employee,
            str(getdate(self.attendance_date))
        ])

    def validate_timing(self):

        if self.first_in and self.last_out and self.last_out < self.first_in:
            frappe.throw("Last Out cannot be earlier than First In.")


def build_attendance_key(employee, attendance_date):

    return ATTENDANCE_KEY_SEPARATOR.join([
        employee,
        str(getdate(attendance_date))
    ])
