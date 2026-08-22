# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Turn a device's user list into Employees, and attach them.

A sync of either kind only ever produces Machine Users: a device knows a number
and a name and nothing else. Attendance, though, is built per Employee —
`attendance_sync.rebuild_for_range` begins at `p.employee IS NOT NULL` — so
until every Machine User points at one, punches are stored and invisible. That
gap is what this module closes.

**Nothing here runs by itself, and it must not.** A name is the only evidence
available, and attaching the wrong one moves somebody's attendance onto another
person silently. So `plan()` decides nothing and writes nothing; it reports what
would happen, for a human to agree to, and `apply_plan()` recomputes the same
plan server-side rather than trusting a list posted back from a browser.

Two facts about real device data shape the rules below, both found on the
Fabrixcel unit (172 enrolments):

* **Employee Code is unique across every machine, but each device numbers its
  people from 1 on its own.** Seven of its ids already belonged to different
  people enrolled on another terminal — its user 4 is not the user 4 who was
  already an Employee. So a device id is used as a code only while it is free.

* **One person can hold two enrolments.** `09`/`F09` are both Amol Bawane. Left
  alone that becomes two Employees and one person's day is split across both,
  so same-named users are gathered onto one Employee by default.
"""

import frappe

from frappe.utils import getdate

from timebridge.timebridge.adms import logger

# Enrolments that are not people. Skipped rather than renamed or deleted: the
# device needs its administrator account, we simply do not want an Employee for
# it. Nothing is hidden — the caller is told what was left out and why.
NON_PERSON_NAMES = {
    "ADMIN",
    "ADMINISTRATOR",
    "SUPERVISOR",
    "MASTER",
    "TEST",
    "GUEST",
    "USER",
}


def normalise(name):
    """
    Compare names the way a person reading them would: case and run-together
    spacing are not identity.

    Deliberately no fuzzy matching. "SUVARNAJICHKAR" and "SUVARNA JICHKAR" stay
    different here, because a near-miss that silently resolves to somebody is
    worse than one the operator is asked about.
    """

    return " ".join((name or "").split()).upper()


def is_non_person(user_name, user_id):
    """Placeholder and service accounts, including our own unnamed-user label."""

    normalised = normalise(user_name)

    return normalised in NON_PERSON_NAMES or normalised == f"USER {user_id}".upper()


def employees_by_name():
    """Existing Employees keyed on their comparable name."""

    rows = frappe.get_all("Employee", fields=["name", "employee_name"])

    return {normalise(row.employee_name): row.name for row in rows}


def taken_codes():

    return {
        row.employee_code
        for row in frappe.get_all("Employee", fields=["employee_code"])
        if row.employee_code
    }


def free_code(user_id, machine_code, taken):
    """
    Prefer the device's own user id; qualify it with the machine when that id is
    already spoken for elsewhere.

    The bare id is the more useful code — it is what somebody reads off the
    terminal — so it is kept wherever it is still free, and only the collisions
    grow a prefix.
    """

    if user_id not in taken:
        return user_id

    candidate = f"{machine_code}-{user_id}"

    suffix = 2

    while candidate in taken:
        candidate = f"{machine_code}-{user_id}-{suffix}"
        suffix += 1

    return candidate


def suggested_defaults():
    """
    Fields the device cannot know, guessed from the Employees already on file.

    Organization and Branch are mandatory on Employee, so a bulk create needs
    an answer for them. The commonest existing value is offered as a starting
    point; the operator confirms or changes it.
    """

    def commonest(fieldname):

        rows = frappe.get_all(
            "Employee",
            fields=[fieldname, "count(name) as n"],
            group_by=fieldname,
            order_by="n desc",
            limit=1,
        )

        return rows[0].get(fieldname) if rows else None

    organization = commonest("organization") or (
        frappe.db.get_value("Organization", {}, "name")
    )

    branch = commonest("branch") or frappe.db.get_value("Branch", {}, "name")

    return {
        "organization": organization,
        "branch": branch,
        "shift": commonest("shift"),
    }


def plan(machine_id, skip_non_person=True, merge_same_name=True):
    """
    Work out what attaching this machine's users would do, without doing it.

    Returns the rows in the order they would be acted on, plus counts and the
    defaults a caller needs to fill the mandatory Employee fields.
    """

    machine_code = (
        frappe.db.get_value("Biometric Machine", machine_id, "machine_id")
        or machine_id
    )

    users = frappe.get_all(
        "Machine User",
        filters={"machine": machine_id},
        fields=["name", "user_id", "user_name", "employee"],
        order_by="user_id",
    )

    existing = employees_by_name()
    taken = taken_codes()

    already_linked = 0
    skipped = []
    groups = {}

    for user in users:

        if user.employee:
            already_linked += 1
            continue

        if skip_non_person and is_non_person(user.user_name, user.user_id):
            skipped.append({
                "user_id": user.user_id,
                "user_name": user.user_name,
                "reason": "not a person",
            })
            continue

        # Grouping on the name is what folds two enrolments of one person onto a
        # single Employee. Turned off, each Machine User stands alone.
        key = normalise(user.user_name) if merge_same_name else user.name

        groups.setdefault(key, []).append(user)

    rows = []

    for members in groups.values():

        user_name = members[0].user_name

        match = existing.get(normalise(user_name))

        if match:

            rows.append({
                "action": "link",
                "user_name": user_name,
                "user_ids": [m.user_id for m in members],
                "machine_users": [m.name for m in members],
                "employee": match,
                "employee_code": frappe.db.get_value("Employee", match, "employee_code"),
            })

            continue

        code = free_code(members[0].user_id, machine_code, taken)

        # Reserved as we go, so two rows in one plan cannot claim one code.
        taken.add(code)

        rows.append({
            "action": "create",
            "user_name": user_name,
            "user_ids": [m.user_id for m in members],
            "machine_users": [m.name for m in members],
            "employee": None,
            "employee_code": code,
        })

    return {
        "machine": machine_id,
        "machine_name": frappe.db.get_value("Biometric Machine", machine_id, "machine_name"),
        "rows": rows,
        "skipped": skipped,
        "counts": {
            "link": sum(1 for row in rows if row["action"] == "link"),
            "create": sum(1 for row in rows if row["action"] == "create"),
            "merged": sum(1 for row in rows if len(row["user_ids"]) > 1),
            "skipped": len(skipped),
            "already_linked": already_linked,
        },
        "defaults": suggested_defaults(),
    }


def apply_plan(
    machine_id,
    date_of_joining,
    organization,
    branch,
    shift=None,
    skip_non_person=True,
    merge_same_name=True,
):
    """
    Create the missing Employees, attach every Machine User, and backfill punches.

    The plan is recomputed here rather than accepted from the caller, so what is
    written is decided by the same rules the operator was shown — and a stale
    browser tab cannot post yesterday's plan.

    One failure does not stop the rest: a name that will not save is reported by
    name and the remaining people are still attached.
    """

    if not date_of_joining:
        frappe.throw("Date of Joining is required — an Employee will not save without it.")

    if not organization or not branch:
        frappe.throw("Organization and Branch are required on Employee.")

    result = plan(machine_id, skip_non_person, merge_same_name)

    created = 0
    linked = 0
    failures = []

    for row in result["rows"]:

        try:
            employee = row["employee"]

            if not employee:

                employee = create_employee(
                    row,
                    machine_id,
                    date_of_joining,
                    organization,
                    branch,
                    shift,
                )

                created += 1

            for machine_user in row["machine_users"]:
                frappe.db.set_value("Machine User", machine_user, "employee", employee)
                linked += 1

        except Exception as e:

            frappe.log_error(
                frappe.get_traceback(),
                "TimeBridge: Employee Link Error"
            )

            failures.append({"user_name": row["user_name"], "error": str(e)})

    # Punches were stored before anyone knew whose they were. This is what makes
    # the history visible, not just the punches from here on.
    punches = logger.link_unmatched_punches(machine_id)

    from timebridge.timebridge.services.employee_photo import copy_linked_photos
    copy_linked_photos(machine_id)

    frappe.db.commit()

    return {
        "status": "success" if not failures else "partial",
        "created": created,
        "linked": linked,
        "punches_linked": punches,
        "skipped": result["skipped"],
        "failures": failures,
        "counts": result["counts"],
    }


def machine_employees(machine_id):
    """
    The Employees this machine's users point at.

    Membership is read from the Machine User links rather than from
    `Employee.biometric_machine`, because the link is what attendance actually
    follows and `biometric_machine` can only name one machine even for somebody
    enrolled on two.
    """

    linked = frappe.get_all(
        "Machine User",
        filters={"machine": machine_id, "employee": ("is", "set")},
        pluck="employee",
    )

    return sorted(set(linked))


def assignment_summary(machine_id):
    """
    What Organization, Branch and Shift this machine's people currently carry.

    Shown before any bulk change so the operator can see what they are about to
    overwrite — including the case where everyone already agrees, which means
    there is nothing to do.
    """

    employees = machine_employees(machine_id)

    if not employees:
        return {
            "employees": 0,
            "spread": [],
            "shared": 0,
            "defaults": suggested_defaults(),
        }

    spread = frappe.db.sql(
        """
        SELECT organization, branch, shift, COUNT(*) AS n
        FROM `tabEmployee`
        WHERE name IN %(names)s
        GROUP BY organization, branch, shift
        ORDER BY n DESC
        """,
        {"names": employees},
        as_dict=True,
    )

    for row in spread:
        row["organization_name"] = frappe.db.get_value(
            "Organization", row["organization"], "organization_name"
        )
        row["branch_name"] = frappe.db.get_value("Branch", row["branch"], "branch_name")
        row["shift_name"] = (
            frappe.db.get_value("Shift", row["shift"], "shift_name") if row["shift"] else None
        )

    # Somebody enrolled on two terminals would be changed by either machine's
    # action. Rare, but silently moving a shared person is exactly the kind of
    # surprise worth naming up front.
    shared = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT employee) AS n
        FROM `tabMachine User`
        WHERE employee IN %(names)s AND machine != %(machine)s
        """,
        {"names": employees, "machine": machine_id},
        as_dict=True,
    )[0].n

    return {
        "employees": len(employees),
        "spread": spread,
        "shared": shared,
        "defaults": suggested_defaults(),
    }


def apply_assignment(machine_id, organization=None, branch=None, shift=None):
    """
    Set Organization, Branch and Shift on this machine's Employees.

    An update and nothing else: no record is created, deleted or unlinked, so
    punches, attendance and the Machine User links are all untouched. That is
    the whole reason this exists rather than a "reset and redo" — the link is
    not what needs changing.

    A blank argument leaves that field alone, and an Employee already holding
    the requested value is not counted as changed.
    """

    updates = {
        field: value
        for field, value in (
            ("organization", organization),
            ("branch", branch),
            ("shift", shift),
        )
        if value
    }

    if not updates:
        frappe.throw("Choose at least one of Organization, Branch or Shift to change.")

    employees = machine_employees(machine_id)

    changed = 0

    for name in employees:

        current = frappe.db.get_value("Employee", name, list(updates), as_dict=True) or {}

        delta = {
            field: value
            for field, value in updates.items()
            if current.get(field) != value
        }

        if not delta:
            continue

        frappe.db.set_value("Employee", name, delta)

        changed += 1

    frappe.db.commit()

    return {
        "employees": len(employees),
        "changed": changed,
        "fields": list(updates),

        # Shift decides late and half-day, so the figures already stored are
        # stale the moment it moves. The caller says so rather than leaving the
        # operator to discover it from wrong numbers.
        "needs_rebuild": "shift" in updates and changed > 0,
    }


def create_employee(row, machine_id, date_of_joining, organization, branch, shift=None):
    """
    One Employee for one person, carrying the device details that identify them.

    machine_user records only the first enrolment when a person holds two; the
    Machine User side of the link is set for every one of them, and that is the
    direction attendance reads.
    """

    doc = frappe.get_doc({
        "doctype": "Employee",
        "employee_code": row["employee_code"],
        "employee_name": row["user_name"],
        "date_of_joining": getdate(date_of_joining),
        "organization": organization,
        "branch": branch,
        "shift": shift or None,
        "biometric_machine": machine_id,
        "machine_user": row["machine_users"][0],
        "is_active": 1,
    })

    doc.insert(ignore_permissions=True)

    return doc.name
