from frappe.tests.utils import FrappeTestCase

from timebridge.timebridge.query_compat import rewrite_text


class TestQueryCompat(FrappeTestCase):
	def test_rewrites_qualified_employee_name(self):
		raw = "`tabTimeBridge Employee`.`employee_name` asc, `tabTimeBridge Employee`.`name` asc"
		self.assertEqual(
			rewrite_text(raw, "TimeBridge Employee"),
			"`tabTimeBridge Employee`.`employee` asc, `tabTimeBridge Employee`.`name` asc",
		)

	def test_rewrites_link_title_field(self):
		raw = "employee.employee_name as employee_employee_name"
		self.assertEqual(
			rewrite_text(raw, "TimeBridge Attendance"),
			"employee.employee as employee_employee_name",
		)

	def test_leaves_attendance_own_name_field(self):
		raw = "`tabTimeBridge Attendance`.`employee_name`"
		self.assertEqual(rewrite_text(raw, "TimeBridge Attendance"), raw)
