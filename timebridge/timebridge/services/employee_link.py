# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Turn a device's user list into TimeBridge Employees, and attach them.

A sync of either kind only ever produces TimeBridge Machine Users: a device knows a number
and a name and nothing else. Attendance, though, is built per TimeBridge Employee —
`attendance_sync.rebuild_for_range` begins at `p.employee IS NOT NULL` — so
until every TimeBridge Machine User points at one, punches are stored and invisible. That
gap is what this module closes.

**Nothing here runs by itself, and it must not.** A name is the only evidence
available, and attaching the wrong one moves somebody's attendance onto another
person silently. So `plan()` decides nothing and writes nothing; it reports what
would happen, for a human to agree to, and `apply_plan()` recomputes the same
plan server-side rather than trusting a list posted back from a browser.

Two facts about real device data shape the rules below, both found on the
Fabrixcel unit (172 enrolments):

* **TimeBridge Employee Code is unique across every machine, but each device numbers its
  people from 1 on its own.** Seven of its ids already belonged to different
  people enrolled on another terminal — its user 4 is not the user 4 who was
  already a TimeBridge Employee. So a device id is used as a code only while it is free.

* **One person can hold two enrolments.** `09`/`F09` are both Amol Bawane. Left
  alone that becomes two TimeBridge Employees and one person's day is split across both,
  so same-named users are gathered onto one TimeBridge Employee by default.
"""

import frappe

from frappe.utils import getdate

from timebridge.timebridge.adms import logger

# Enrolments that are not people. Skipped rather than renamed or deleted: the
# device needs its administrator account, we simply do not want a TimeBridge Employee for
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
    """Existing TimeBridge Employees keyed on their comparable name."""

    rows = frappe.get_all("TimeBridge Employee", fields=["name", "employee"])

    return {normalise(row.employee): row.name for row in rows}


def taken_codes():

    return {
        row.employee_code
        for row in frappe.get_all("TimeBridge Employee", fields=["employee_code"])
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
    Fields the device cannot know, guessed from the TimeBridge Employees already on file.

    TimeBridge Organization and TimeBridge Branch are mandatory on TimeBridge Employee, so a bulk create needs
    an answer for them. The commonest existing value is offered as a starting
    point; the operator confirms or changes it.
    """

    def commonest(fieldname):

        rows = frappe.get_all(
            "TimeBridge Employee",
            fields=[fieldname, "count(name) as n"],
            group_by=fieldname,
            order_by="n desc",
            limit=1,
        )

        return rows[0].get(fieldname) if rows else None

    organization = commonest("organization") or (
        frappe.db.get_value("TimeBridge Organization", {}, "name")
    )

    branch = commonest("branch") or frappe.db.get_value("TimeBridge Branch", {}, "name")

    return {
        "organization": organization,
        "branch": branch,
        "shift": commonest("shift"),
    }


def list_candidates(machine=None):
    """
    Unlinked Machine Users an operator can turn into TimeBridge Employees.

    Optional machine filter keeps the picker readable when many devices share a
    site. Counts include linked rows so the dialog can show progress at a glance.
    """

    filters = {}
    if machine:
        filters["machine"] = machine

    rows = frappe.get_all(
        "TimeBridge Machine User",
        filters=filters,
        fields=["name", "user_id", "user_name", "machine", "employee", "is_active"],
        order_by="machine, user_id",
    )

    machine_ids = list({row.machine for row in rows if row.machine})
    machine_names = {}
    if machine_ids:
        machine_names = {
            m.name: m.machine_name or m.name
            for m in frappe.get_all(
                "TimeBridge Machine",
                filters={"name": ("in", machine_ids)},
                fields=["name", "machine_name"],
            )
        }

    candidates = []
    linked_candidates = []
    linked = 0

    for row in rows:
        item = {
            "name": row.name,
            "user_id": row.user_id,
            "user_name": row.user_name,
            "machine": row.machine,
            "machine_name": machine_names.get(row.machine, row.machine),
            "is_active": row.is_active,
            "employee": row.employee,
        }
        if row.employee:
            linked += 1
            linked_candidates.append(item)
            continue

        candidates.append(item)

    return {
        "total": len(rows),
        "linked": linked,
        "unlinked": len(candidates),
        "candidates": candidates,
        "linked_candidates": linked_candidates,
        "defaults": suggested_defaults(),
    }


def plan(machine_id, skip_non_person=True, merge_same_name=True, machine_user_names=None):
    """
    Work out what attaching this machine's users would do, without doing it.

    Returns the rows in the order they would be acted on, plus counts and the
    defaults a caller needs to fill the mandatory TimeBridge Employee fields.

    machine_user_names limits the plan to those TimeBridge Machine User names —
    used when the operator picks people from the Machine User list.
    """

    machine_code = (
        frappe.db.get_value("TimeBridge Machine", machine_id, "machine_id")
        or machine_id
    )

    users = frappe.get_all(
        "TimeBridge Machine User",
        filters={"machine": machine_id},
        fields=["name", "user_id", "user_name", "employee"],
        order_by="user_id",
    )

    if machine_user_names is not None:
        allowed = set(machine_user_names)
        users = [user for user in users if user.name in allowed]

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
        # single TimeBridge Employee. Turned off, each TimeBridge Machine User stands alone.
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
                "employee_code": frappe.db.get_value("TimeBridge Employee", match, "employee_code"),
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
        "machine_name": frappe.db.get_value("TimeBridge Machine", machine_id, "machine_name"),
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
    machine_user_names=None,
):
    """
    Create the missing TimeBridge Employees, attach every TimeBridge Machine User, and backfill punches.

    The plan is recomputed here rather than accepted from the caller, so what is
    written is decided by the same rules the operator was shown — and a stale
    browser tab cannot post yesterday's plan.

    One failure does not stop the rest: a name that will not save is reported by
    name and the remaining people are still attached.

    machine_user_names, when set, only acts on those Machine Users (see plan).
    """

    if not date_of_joining:
        frappe.throw("Date of Joining is required — a TimeBridge Employee will not save without it.")

    if not organization or not branch:
        frappe.throw("TimeBridge Organization and TimeBridge Branch are required on TimeBridge Employee.")

    result = plan(
        machine_id,
        skip_non_person,
        merge_same_name,
        machine_user_names=machine_user_names,
    )

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
                frappe.db.set_value("TimeBridge Machine User", machine_user, "employee", employee)
                linked += 1

        except Exception as e:

            frappe.log_error(
                frappe.get_traceback(),
                "TimeBridge: TimeBridge Employee Link Error"
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


def apply_selected(
    machine_user_names,
    date_of_joining,
    organization,
    branch,
    shift=None,
    skip_non_person=True,
    merge_same_name=True,
):
    """
    Create & link for an explicit set of Machine Users, possibly across machines.

    Groups by machine and reuses apply_plan so linking, punch backfill, and
    photo copy stay identical to the Machine form path.
    """

    names = machine_user_names
    if isinstance(names, str):
        names = frappe.parse_json(names)

    names = list(names or [])
    if not names:
        frappe.throw("Select at least one Machine User.")

    rows = frappe.get_all(
        "TimeBridge Machine User",
        filters={"name": ("in", names)},
        fields=["name", "machine"],
    )

    if not rows:
        frappe.throw("None of the selected Machine Users were found.")

    by_machine = {}
    for row in rows:
        by_machine.setdefault(row.machine, []).append(row.name)

    created = 0
    linked = 0
    punches_linked = 0
    failures = []
    skipped = []

    for machine_id, mu_names in by_machine.items():
        result = apply_plan(
            machine_id,
            date_of_joining=date_of_joining,
            organization=organization,
            branch=branch,
            shift=shift,
            skip_non_person=skip_non_person,
            merge_same_name=merge_same_name,
            machine_user_names=mu_names,
        )
        created += result.get("created") or 0
        linked += result.get("linked") or 0
        punches_linked += result.get("punches_linked") or 0
        failures.extend(result.get("failures") or [])
        skipped.extend(result.get("skipped") or [])

    return {
        "status": "success" if not failures else "partial",
        "created": created,
        "linked": linked,
        "punches_linked": punches_linked,
        "skipped": skipped,
        "failures": failures,
        "machines": len(by_machine),
    }


def machine_employees(machine_id):
    """
    The TimeBridge Employees this machine's users point at.

    Membership is read from the TimeBridge Machine User links rather than from
    `TimeBridge Employee.biometric_machine`, because the link is what attendance actually
    follows and `biometric_machine` can only name one machine even for somebody
    enrolled on two.
    """

    linked = frappe.get_all(
        "TimeBridge Machine User",
        filters={"machine": machine_id, "employee": ("is", "set")},
        pluck="employee",
    )

    return sorted(set(linked))


def assignment_summary(machine_id):
    """
    What TimeBridge Organization, TimeBridge Branch and TimeBridge Shift this machine's people currently carry.

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
        FROM `tabTimeBridge Employee`
        WHERE name IN %(names)s
        GROUP BY organization, branch, shift
        ORDER BY n DESC
        """,
        {"names": employees},
        as_dict=True,
    )

    for row in spread:
        row["organization_name"] = frappe.db.get_value(
            "TimeBridge Organization", row["organization"], "organization_name"
        )
        row["branch_name"] = frappe.db.get_value("TimeBridge Branch", row["branch"], "branch_name")
        row["shift_name"] = (
            frappe.db.get_value("TimeBridge Shift", row["shift"], "shift_name") if row["shift"] else None
        )

    # Somebody enrolled on two terminals would be changed by either machine's
    # action. Rare, but silently moving a shared person is exactly the kind of
    # surprise worth naming up front.
    shared = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT employee) AS n
        FROM `tabTimeBridge Machine User`
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


def apply_assignment(
    machine_id,
    organization=None,
    branch=None,
    shift=None,
    date_of_joining=None,
    employee_names=None,
):
    """
    Set TimeBridge Organization, TimeBridge Branch, TimeBridge Shift and/or
    Date of Joining on this machine's TimeBridge Employees.

    An update and nothing else: no record is created, deleted or unlinked, so
    punches, attendance and the TimeBridge Machine User links are all untouched. That is
    the whole reason this exists rather than a "reset and redo" — the link is
    not what needs changing.

    A blank argument leaves that field alone, and a TimeBridge Employee already holding
    the requested value is not counted as changed.

    employee_names, when set, limits the update to those TimeBridge Employees
    (used when the operator picks people from Machine User list).
    """

    if employee_names is not None:
        employees = list(dict.fromkeys(employee_names))
    else:
        employees = machine_employees(machine_id)

    return apply_on_employees(
        employees,
        organization=organization,
        branch=branch,
        shift=shift,
        date_of_joining=date_of_joining,
    )


def apply_assignment_selected(
    machine_user_names,
    organization=None,
    branch=None,
    shift=None,
    date_of_joining=None,
):
    """
    Update defaults on TimeBridge Employees linked to the chosen Machine Users.
    """

    names = machine_user_names
    if isinstance(names, str):
        names = frappe.parse_json(names)

    names = list(names or [])
    if not names:
        frappe.throw("Select at least one Machine User.")

    employees = frappe.get_all(
        "TimeBridge Machine User",
        filters={"name": ("in", names), "employee": ("is", "set")},
        pluck="employee",
    )
    employees = list(dict.fromkeys(employees))

    if not employees:
        frappe.throw("Selected Machine Users have no linked TimeBridge Employee.")

    return apply_on_employees(
        employees,
        organization=organization,
        branch=branch,
        shift=shift,
        date_of_joining=date_of_joining,
    )


def apply_on_employees(
    employees,
    organization=None,
    branch=None,
    shift=None,
    date_of_joining=None,
):
    """Write the chosen fields onto an explicit list of TimeBridge Employees."""

    updates = {
        field: value
        for field, value in (
            ("organization", organization),
            ("branch", branch),
            ("shift", shift),
        )
        if value
    }

    if date_of_joining:
        updates["date_of_joining"] = getdate(date_of_joining)

    if not updates:
        frappe.throw(
            "Choose at least one of Date of Joining, TimeBridge Organization, "
            "TimeBridge Branch or TimeBridge Shift to change."
        )

    if not employees:
        frappe.throw("No TimeBridge Employees to update.")

    changed = 0

    for name in employees:

        current = frappe.db.get_value("TimeBridge Employee", name, list(updates), as_dict=True) or {}

        delta = {}
        for field, value in updates.items():
            cur = current.get(field)
            if field == "date_of_joining":
                cur = getdate(cur) if cur else None
                if cur == value:
                    continue
            elif cur == value:
                continue
            delta[field] = value

        if not delta:
            continue

        frappe.db.set_value("TimeBridge Employee", name, delta)

        changed += 1

    frappe.db.commit()

    return {
        "employees": len(employees),
        "changed": changed,
        "fields": list(updates),

        # TimeBridge Shift decides late and half-day, so the figures already stored are
        # stale the moment it moves. The caller says so rather than leaving the
        # operator to discover it from wrong numbers.
        "needs_rebuild": "shift" in updates and changed > 0,
    }


def create_employee(row, machine_id, date_of_joining, organization, branch, shift=None):
    """
    One TimeBridge Employee for one person, carrying the device details that identify them.

    machine_user records only the first enrolment when a person holds two; the
    TimeBridge Machine User side of the link is set for every one of them, and that is the
    direction attendance reads.
    """

    doc = frappe.get_doc({
        "doctype": "TimeBridge Employee",
        "employee_code": row["employee_code"],
        "first_name": row["user_name"],
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
