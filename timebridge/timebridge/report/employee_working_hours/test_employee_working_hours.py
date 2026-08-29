# Copyright (c) 2026, UPGO and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate

from timebridge.timebridge.report.employee_working_hours.employee_working_hours import execute


class TestEmployeeWorkingHours(FrappeTestCase):
    def setUp(self):
        self.organization = frappe.get_doc(
            {
                "doctype": "TimeBridge Organization",
                "organization_code": "WH-ORG",
                "organization_name": "Working Hours Test Org",
            }
        ).insert()

        self.branch = frappe.get_doc(
            {
                "doctype": "TimeBridge Branch",
                "organization": self.organization.name,
                "branch_code": "WH-BR",
                "branch_name": "Working Hours Test Branch",
            }
        ).insert()

        self.employee = frappe.get_doc(
            {
                "doctype": "TimeBridge Employee",
                "employee_code": "WH-TEST-001",
                "employee_name": "HR Name Should Not Show",
                "date_of_joining": "2026-01-01",
                "organization": self.organization.name,
                "branch": self.branch.name,
                "is_active": 1,
            }
        ).insert()

        self.machine = frappe.get_doc(
            {
                "doctype": "TimeBridge Machine",
                "machine_id": "WH-MACHINE",
                "machine_name": "Working Hours Test Machine",
                "device_brand": "ZKTeco",
                "ip_address": "192.168.1.99",
                "port": 4370,
                "sdk_type": "PyZK",
            }
        ).insert()

        self.machine_user = frappe.get_doc(
            {
                "doctype": "TimeBridge Machine User",
                "machine": self.machine.name,
                "user_id": "101",
                "user_name": "Device User Name",
                "employee": self.employee.name,
            }
        ).insert()

        self.first = getdate("2026-08-02")
        self.last = getdate("2026-08-04")

        self._punch(self.last, "09:00:00")
        self._punch(self.last, "18:00:00")

    def tearDown(self):
        frappe.db.delete("TimeBridge Punch Log", {"machine_user": self.machine_user.name})
        frappe.db.delete("TimeBridge Machine User", {"name": self.machine_user.name})
        frappe.db.delete("TimeBridge Machine", {"name": self.machine.name})
        frappe.db.delete("TimeBridge Employee", {"name": self.employee.name})
        frappe.db.delete("TimeBridge Branch", {"name": self.branch.name})
        frappe.db.delete("TimeBridge Organization", {"name": self.organization.name})

    def _punch(self, punch_date, time_str):
        frappe.get_doc(
            {
                "doctype": "TimeBridge Punch Log",
                "machine": self.machine.name,
                "device_user_id": "101",
                "machine_user": self.machine_user.name,
                "employee": self.employee.name,
                "employee_name": "Punch Log Employee Name",
                "timestamp": f"{punch_date} {time_str}",
                "source": "PyZK Pull",
            }
        ).insert()

    def test_execute_returns_every_day_in_range(self):
        columns, rows, heading, *_ = execute(
            {
                "machine_user": self.machine_user.name,
                "from_date": self.first,
                "to_date": self.last,
            }
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual([c["fieldname"] for c in columns][-1], "working_hours")
        self.assertIn("Device User Name", heading)
        self.assertNotIn("HR Name Should Not Show", heading)

        by_date = {row["attendance_date"]: row for row in rows}

        self.assertEqual(by_date[self.last]["status_code"], "P")
        self.assertEqual(by_date[self.last]["first_in"], "09:00")
        self.assertEqual(by_date[self.last]["last_out"], "18:00")
        self.assertEqual(by_date[self.last]["working_hours"], 9)

        self.assertEqual(by_date[add_days(self.first, 1)]["status_code"], "")

        # Sunday 2026-08-02 is a weekly off with default settings.
        self.assertEqual(by_date[self.first]["status_code"], "R")

    def test_rejects_inverted_dates(self):
        with self.assertRaises(frappe.ValidationError):
            execute(
                {
                    "machine_user": self.machine_user.name,
                    "from_date": self.last,
                    "to_date": self.first,
                }
            )

    def test_punches_without_employee_link_still_report(self):
        frappe.db.delete("TimeBridge Punch Log", {"machine_user": self.machine_user.name})

        self._punch(self.last, "09:00:00")
        self._punch(self.last, "18:00:00")
        frappe.db.set_value("TimeBridge Punch Log", {"machine_user": self.machine_user.name}, "employee", None)

        _, rows, heading, *_ = execute(
            {
                "machine_user": self.machine_user.name,
                "from_date": self.last,
                "to_date": self.last,
            }
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["working_hours"], 9)
        self.assertIn("Device User Name", heading)
