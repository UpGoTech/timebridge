# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Picks the right driver for a machine from its SDK Type.

Every option the TimeBridge Machine form offers is answered here. A dropdown
that lists four choices and crashes on three of them is worse than no
dropdown — the user has no way to tell a wrong selection from a broken app.
So the two that are not built say exactly that, by name, instead of throwing
"Unsupported SDK Type".
"""

import frappe

from timebridge.timebridge.sdk_connectors.essl_connector import ADMSConnector

# SDK types whose devices dial out to us rather than answering us. Nothing
# may try to open a connection to these.
PUSH_SDK_TYPES = {"ADMS"}

NOT_BUILT = {
    "Matrix": (
        "Matrix devices are not supported yet — no driver has been written for "
        "them. Use PyZK if the device speaks the ZK protocol, or ADMS if it "
        "pushes to a server."
    ),
    "Custom": (
        "Custom means a driver written for one specific device, and none exists "
        "yet. Pick PyZK or ADMS, or ask for a driver to be built."
    ),
}


def is_push_device(device):
    """True when the device sends to us and cannot be dialled."""

    return (device.sdk_type or "") in PUSH_SDK_TYPES


def get_connector(device):

    sdk_type = device.sdk_type or ""

    if sdk_type == "PyZK":
        from timebridge.timebridge.sdk_connectors.pyzk_connector import PyZKConnector

        return PyZKConnector()

    if sdk_type == "ADMS":
        return ADMSConnector()

    if sdk_type in NOT_BUILT:
        frappe.throw(NOT_BUILT[sdk_type])

    frappe.throw(
        f"No driver for SDK Type {sdk_type!r}. Choose PyZK (device answers us) "
        f"or ADMS (device sends to us)."
    )
