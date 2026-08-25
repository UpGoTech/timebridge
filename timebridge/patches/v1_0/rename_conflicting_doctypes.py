import frappe


# Old names collide with ERPNext / HR. Rename only if TimeBridge owns them.
RENAMES = [
    ("Organization", "TimeBridge Organization"),
    ("Branch", "TimeBridge Branch"),
    ("Department", "TimeBridge Department"),
    ("Shift", "TimeBridge Shift"),
    ("Employee", "TimeBridge Employee"),
    ("Biometric Machine", "TimeBridge Machine"),
    ("Machine User", "TimeBridge Machine User"),
]


def execute():
    for old, new in RENAMES:
        _rename_if_ours(old, new)


def _rename_if_ours(old, new):
    if not frappe.db.exists("DocType", old):
        return
    if frappe.db.exists("DocType", new):
        return
    if frappe.db.get_value("DocType", old, "module") != "TimeBridge":
        return

    frappe.rename_doc("DocType", old, new, force=True, show_alert=False)
