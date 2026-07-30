import frappe

from timebridge.timebridge.sdk_connectors.pyzk_connector import PyZKConnector


def get_connector(device):

    if device.sdk_type == "PyZK":
        return PyZKConnector()

    frappe.throw(f"Unsupported SDK Type : {device.sdk_type}")