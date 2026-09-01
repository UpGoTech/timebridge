"""Map old TimeBridge Employee.employee_name list queries to Full Name (`employee`)."""

import json

import frappe

OLD_QUALIFIED = "`tabTimeBridge Employee`.`employee_name`"
NEW_QUALIFIED = "`tabTimeBridge Employee`.`employee`"
OLD_PLAIN = "tabTimeBridge Employee.employee_name"
NEW_PLAIN = "tabTimeBridge Employee.employee"

REPORTVIEW_CMDS = {
	"frappe.desk.reportview.get",
	"frappe.desk.reportview.get_list",
	"frappe.desk.reportview.get_count",
}

LINKED_LISTS = {
	"TimeBridge Employee",
	"TimeBridge Attendance",
	"TimeBridge Leave",
	"TimeBridge Punch Log",
	"TimeBridge Machine User",
}


def remap_old_employee_name():
	if frappe.form_dict.get("cmd") not in REPORTVIEW_CMDS:
		return
	doctype = frappe.form_dict.get("doctype")
	_rewrite_key("fields", doctype)
	_rewrite_key("order_by", doctype)
	_rewrite_key("filters", doctype)
	_rewrite_key("or_filters", doctype)


def rewrite_text(value, doctype=None):
	if not isinstance(value, str):
		return value
	value = value.replace(OLD_QUALIFIED, NEW_QUALIFIED).replace(OLD_PLAIN, NEW_PLAIN)
	if doctype in LINKED_LISTS:
		value = value.replace("employee.employee_name", "employee.employee")
	return value


def _rewrite_key(key, doctype):
	raw = frappe.form_dict.get(key)
	if raw in (None, ""):
		return
	if isinstance(raw, str):
		try:
			parsed = json.loads(raw)
		except (TypeError, ValueError):
			rewritten = rewrite_text(raw, doctype)
			if rewritten != raw:
				frappe.form_dict[key] = rewritten
			return
		new_value = _rewrite_loaded(parsed, doctype)
		if new_value != parsed:
			frappe.form_dict[key] = json.dumps(new_value)
		return
	new_value = _rewrite_loaded(raw, doctype)
	if new_value != raw:
		frappe.form_dict[key] = new_value


def _rewrite_loaded(value, doctype):
	if isinstance(value, str):
		return rewrite_text(value, doctype)
	if isinstance(value, list):
		return [_rewrite_loaded(item, doctype) for item in value]
	return value
