# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

import frappe

from frappe.model.document import Document
from frappe.utils import get_datetime


# The key is built from the three things that identify a punch on a device.
# It is stored in a unique column rather than expressed as a composite index,
# because a DocType JSON cannot declare one — see punch_key in the schema.
PUNCH_KEY_SEPARATOR = "::"


class TimeBridgePunchLog(Document):

    def before_insert(self):
        self.set_punch_key()

    def validate(self):
        self.set_punch_key()

    def set_punch_key(self):
        """
        ZK devices return their entire stored log on every read, so the same
        punch arrives again on every sync. This key is what makes those
        re-reads harmless: the second insert collides instead of duplicating.
        """

        if not (self.machine and self.device_user_id and self.timestamp):
            return

        self.punch_key = PUNCH_KEY_SEPARATOR.join([
            self.machine,
            str(self.device_user_id),
            get_datetime(self.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        ])


def build_punch_key(machine, device_user_id, timestamp):
    """
    Same key, callable without a document. Sync code uses this to check for
    an existing punch before attempting an insert.
    """

    return PUNCH_KEY_SEPARATOR.join([
        machine,
        str(device_user_id),
        get_datetime(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    ])


def punch_exists(machine, device_user_id, timestamp):

    return frappe.db.exists(
        "TimeBridge Punch Log",
        {"punch_key": build_punch_key(machine, device_user_id, timestamp)}
    )
