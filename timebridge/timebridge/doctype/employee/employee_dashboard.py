# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
The Connections tab on an Employee.

Everything here already links back through a single `employee` field, so one
declaration gives the form a live view of that person's attendance, their raw
punches and their device mapping — without a custom page or report.
"""


def get_data():

    return {
        "fieldname": "employee",
        "non_standard_fieldnames": {},
        "transactions": [
            {
                "label": "Attendance",
                "items": ["TimeBridge Attendance"],
            },
            {
                "label": "Device Activity",
                "items": ["TimeBridge Punch Log", "Machine User"],
            },
        ],
    }
