# import frappe


# @frappe.whitelist()
# def test_connection(machine_name):
#     pass


import frappe
import socket

from timebridge.timebridge.services.device_info import enqueue_device_info


@frappe.whitelist()
def get_device_info(machine_id):

    return enqueue_device_info(machine_id)


@frappe.whitelist()
def test_connection(machine_id):

    machine = frappe.get_doc(
        "Biometric Machine",
        machine_id
    )

    ip = machine.ip_address
    port = int(machine.port or 4370)

    try:

        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM
        )

        sock.settimeout(5)

        result = sock.connect_ex(
            (ip, port)
        )

        sock.close()


        if result == 0:

            frappe.db.set_value(
                "Biometric Machine",
                machine.name,
                "status",
                "Connected"
            )

            return {
                "status": "success",
                "message": f"{machine.machine_name} Connected"
            }


        else:

            frappe.db.set_value(
                "Biometric Machine",
                machine.name,
                "status",
                "Disconnected"
            )

            return {
                "status": "failed",
                "message": "Machine not reachable"
            }


    except Exception as e:

        frappe.log_error(
            frappe.get_traceback(),
            "Biometric Connection Error"
        )

        return {
            "status": "failed",
            "message": str(e)
        }
        