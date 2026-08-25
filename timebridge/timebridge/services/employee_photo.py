# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Put a device photograph onto the TimeBridge Employee record.

TimeBridge Machine User is where a picture first lands (push upload, pull read, or a
hand upload). Lists, the TimeBridge Employee form and the reports all read TimeBridge Employee, so
a face that stops on TimeBridge Machine User is a face nobody sees.

`adms.photos.sync_employee_photo` already does the write and already refuses
to overwrite a picture someone put on TimeBridge Employee by hand. This module is the
backfill: after a link or a pull, copy whatever is already sitting on the
device record. It does not replace that function, and it does not change how
photos arrive.
"""

import frappe

from timebridge.timebridge.adms.photos import save_photo, sync_employee_photo


def copy_linked_photos(machine_id):
    """
    For every TimeBridge Machine User on this terminal that has both a photo and an
    TimeBridge Employee, put that photo on the TimeBridge Employee.

    Safe to run again: sync_employee_photo is a no-op when the TimeBridge Employee
    already shows the same file, and it will not replace a hand-uploaded one.
    """

    rows = frappe.get_all(
        "TimeBridge Machine User",
        filters={
            "machine": machine_id,
            "photo": ["is", "set"],
            "employee": ["is", "set"],
        },
        fields=["photo", "employee"],
    )

    copied = 0

    for row in rows:

        before = frappe.db.get_value("TimeBridge Employee", row.employee, "photo")
        sync_employee_photo(row.employee, row.photo)

        if frappe.db.get_value("TimeBridge Employee", row.employee, "photo") != before:
            copied += 1

    return copied


def store_pulled_photos(machine_id, photos):
    """
    Attach JPEGs read off a dialled device, through the same saver the push
    path uses, so first-photo-wins and TimeBridge Employee sync stay one set of rules.
    """

    stored = 0

    for photo in photos or []:

        user_id = photo.get("user_id")
        image = photo.get("image_bytes")

        if not user_id or not image:
            continue

        if save_photo(machine_id, user_id, image, "PyZK Pull"):
            stored += 1

    return stored
