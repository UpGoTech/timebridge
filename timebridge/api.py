# import frappe


# @frappe.whitelist()
# def test_connection(machine_name):
#     pass


import frappe

@frappe.whitelist()
def test_connection(machine_id=None):
    return {
        "status": "success",
        "message": "API Working"
    }