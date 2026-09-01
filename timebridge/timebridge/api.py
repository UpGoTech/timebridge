# import frappe


# @frappe.whitelist()
# def test_connection(machine_name):
#     pass


import frappe
import socket

from frappe.utils import add_days, cint, now_datetime

from timebridge.timebridge.services.device_info import enqueue_device_info, get_progress


@frappe.whitelist()
def get_device_info(machine_id):

    return enqueue_device_info(machine_id)


@frappe.whitelist()
def request_all_data(machine_id, days=30):
    """
    Bring in a device's users and recent attendance.

    How that happens depends on the transport, and the two are not comparable.
    A dialable device is read on demand: we open a session and empty it, and
    the answer is a job to watch. A push device accepts no incoming connection
    at all, so it can only be *asked* — the request waits until it next polls
    us (roughly every 30s, per the Delay in our handshake) and the data follows
    on its own afterwards.

    A dated range rather than CHECK, deliberately: CHECK returns nothing on
    this hardware once the device believes its records were delivered, whereas    
    an explicit range ignores that pointer. The same is true of a bare
    DATA QUERY USERINFO — it is collected and answered with nothing — so user
    dialects follow the ATTLOG dump (tabs, date range, then PIN= from punches).

    Safe to press twice either way: punches carry their original timestamps and
    the unique punch_key rejects anything already stored.
    """

    from timebridge.timebridge.adms import commands
    from timebridge.timebridge.services.connection import is_push_device
    from timebridge.timebridge.services.pull_sync import enqueue_pull_sync

    machine = frappe.get_doc("TimeBridge Machine", machine_id)

    # Serial number is how a pushed batch is matched back to its machine. A
    # dialed device needs no such match — we know who we called — so the check
    # below must not stand in its way.
    if not is_push_device(machine):
        return enqueue_pull_sync(machine_id, days=days)

    if not machine.serial_number:
        return {
            "status": "failed",
            "message": "This machine has no serial number, so the device cannot be "
                       "matched when it answers. Fill in Serial Number first."
        }

    days = cint(days)
    if days < 0:
        days = 30

    end = now_datetime()
    # days == 0 means "everything the device still holds" — a wide floor date;
    # firmware may still return only what remains in its log.
    if days == 0:
        start_s = "2000-01-01 00:00:00"
        range_label = "all retained punches"
    else:
        start = add_days(end, -days)
        start_s = start.strftime("%Y-%m-%d 00:00:00")
        range_label = f"the last {days} days of punches"

    end_s = end.strftime("%Y-%m-%d 23:59:59")

    commands.start_user_fetch(
        machine_id,
        start_s,
        end_s,
        baseline=frappe.db.count("TimeBridge Machine User", {"machine": machine_id}),
    )
    # commands.queue_command(machine_id, commands.request_users())
    commands.queue_command(machine_id, "INFO")

    command_id = commands.queue_command(
        machine_id,
        # commands.resend_attendance_between(
        #     start.strftime("%Y-%m-%d 00:00:00"),
        #     end.strftime("%Y-%m-%d 23:59:59")
        # )
        commands.resend_attendance_between(start_s, end_s),
    )

    return {
        "status": "queued",
        "mode": "push",
        "command_id": command_id,
        "serial": machine.serial_number,
        "days": days,
        "baseline": frappe.db.count("TimeBridge Punch Log", {"machine": machine_id}),
        "baseline_syncs": frappe.db.count("TimeBridge Sync Log", {"machine": machine_id}),
        "last_contact": commands.last_contact(machine_id),
        "message": f"Asked the device for its users and {range_label}."
    }


@frappe.whitelist()
def send_users_to_device(machine_id):
    """
    Push TimeBridge Machine User name and id onto the terminal.

    ADMS queues commands for the next poll; PyZK writes immediately. Photos
    and biometric templates are not sent — see services/push_users.py.
    """

    from timebridge.timebridge.services.push_users import send_users_to_device as send

    return send(machine_id)


@frappe.whitelist()
def bulk_device_action(action, machines):
    """
    Run one device action across several machines and report on each.

    Exists so a room full of terminals can be handled from the list instead of
    opening each one. The per-machine dialogs stay where they are — they show
    a running commentary, which is useful for one device and unreadable for
    ten. This returns a single summary instead.

    Today's figures come back with every result whether the action succeeded or
    not: "the request failed" is far more useful next to "and nobody has
    punched there today either".
    """

    import json

    if isinstance(machines, str):
        machines = json.loads(machines)

    handlers = {
        "test_connection": _bulk_test_connection,
        "fetch_all_data": _bulk_fetch_all,
        "fetch_photos": _bulk_fetch_photos,
    }

    handler = handlers.get(action)

    if not handler:
        frappe.throw(f"Unknown action {action!r}")

    results = []

    for machine_id in machines:

        row = {
            "machine": machine_id,
            "machine_name": frappe.db.get_value("TimeBridge Machine", machine_id, "machine_name"),
        }

        row.update(_today_counts(machine_id))

        try:
            row.update(handler(machine_id))

        except Exception as e:
            # One bad device must not stop the rest of the batch.
            row.update({"ok": False, "message": str(e)})

        results.append(row)

    return {"action": action, "results": results}


def _today_counts(machine_id):
    """How many people punched at this machine today, and how many punches."""

    row = frappe.db.sql(
        """
        SELECT COUNT(DISTINCT COALESCE(employee, device_user_id)) AS people,
               COUNT(*) AS punches
        FROM `tabTimeBridge Punch Log`
        WHERE machine = %s AND DATE(timestamp) = CURDATE()
        """,
        machine_id,
        as_dict=True,
    )[0]

    return {"people_today": row.people or 0, "punches_today": row.punches or 0}


def _bulk_test_connection(machine_id):

    from timebridge.timebridge.services.connection import get_connector, is_push_device

    machine = frappe.get_doc("TimeBridge Machine", machine_id)

    if not is_push_device(machine):
        # Dialling a device can take the better part of two minutes, which is
        # far too long to do serially across a list. Queue it instead.
        enqueue_device_info(machine_id)
        return {"ok": True, "message": "Connection test queued"}

    health = get_connector(machine).health(machine)

    frappe.db.set_value("TimeBridge Machine", machine_id, "status", health["machine_status"])
    frappe.db.commit()

    return {"ok": health["status"] == "success", "message": health["message"]}


def _bulk_fetch_all(machine_id):

    result = request_all_data(machine_id)

    return {"ok": result.get("status") == "queued", "message": result.get("message")}


def _bulk_fetch_photos(machine_id):

    result = request_photos(machine_id)

    return {"ok": result.get("status") == "queued", "message": result.get("message")}


@frappe.whitelist()
def match_photos(machine_id, file_urls):
    """
    Attach uploaded pictures to the right people by reading their filenames.

    The device stores only face templates and cannot produce photographs, so
    they have to come from somewhere else — and doing sixteen people one form
    at a time is the kind of chore that never gets finished.

    A filename is matched, in this order, against: the device user id, the
    employee code, and then the person's name. Names are compared with spaces
    and punctuation stripped, because "SHUBHANGI KAMBLE.jpg",
    "shubhangi_kamble.jpg" and "Shubhangi-Kamble.jpg" all clearly mean the
    same person and refusing them would just send someone back to rename files.

    Anything unmatched is reported rather than guessed at — a photo on the
    wrong person is worse than no photo.
    """

    import json
    import os
    import re

    if isinstance(file_urls, str):
        file_urls = json.loads(file_urls)

    # Files are identified by their record name, not their url. Frappe stores
    # one copy of identical content, so two people given the same picture share
    # a url — looking a name up by url would then return whichever record was
    # written last and attach it to the wrong person.
    file_rows = frappe.get_all(
        "File",
        filters={"name": ["in", file_urls]},
        fields=["name", "file_name", "file_url"],
    )

    def normalise(value):
        return re.sub(r"[^a-z0-9]", "", (value or "").lower())

    users = frappe.get_all(
        "TimeBridge Machine User",
        filters={"machine": machine_id},
        fields=["name", "user_id", "user_name", "employee"],
    )

    by_user_id = {normalise(u.user_id): u for u in users}
    by_name = {normalise(u.user_name): u for u in users}

    by_code = {}

    for emp in frappe.get_all("TimeBridge Employee", fields=["name", "employee_code", "employee"]):
        for user in users:
            if user.employee == emp.name:
                by_code[normalise(emp.employee_code)] = user

    matched, unmatched = [], []

    for row in file_rows:

        file_name = row.file_name or row.name
        url = row.file_url
        stem = normalise(os.path.splitext(os.path.basename(file_name))[0])

        user = by_user_id.get(stem) or by_code.get(stem) or by_name.get(stem)

        if not user:
            unmatched.append(file_name)
            continue

        frappe.db.set_value("TimeBridge Machine User", user.name, "photo", url)

        # The TimeBridge Employee record is what most people actually open, so the picture
        # is put on both rather than only where it happened to be uploaded.
        if user.employee:
            frappe.db.set_value("TimeBridge Employee", user.employee, "photo", url)

        matched.append({
            "file": file_name,
            "user_id": user.user_id,
            "user_name": user.user_name,
            "employee": user.employee,
        })

    frappe.db.commit()

    return {
        "matched": matched,
        "unmatched": unmatched,
        "total": len(file_rows),
        "with_photo": frappe.db.count("TimeBridge Machine User", {"machine": machine_id, "photo": ["is", "set"]}),
        "users": len(users),
    }


@frappe.whitelist()
def request_photos(machine_id):
    """
    Ask a push device for its enrolled photographs.

    Two things have to happen: the FACE and UserPic switches must be opened in
    the handshake (a device is not permitted to send pictures otherwise), and
    the request itself has to wait for the device's next poll.

    Opening those switches is the risky half — a firmware that does not
    understand them may reject the handshake and go silent, taking the punch
    feed with it. So this records how the device was behaving beforehand, and
    photo_fetch_status() closes the switches again the moment it looks like
    that has happened.
    """

    from timebridge.timebridge.adms import commands

    machine = frappe.get_doc("TimeBridge Machine", machine_id)

    if not machine.serial_number:
        return {
            "status": "failed",
            "message": "This machine has no serial number, so the device cannot be "
                       "matched when it answers.",
        }

    contact = commands.last_contact(machine_id) or {}

    if not contact.get("at"):
        return {
            "status": "failed",
            "message": "This device is not currently talking to us, so it cannot be "
                       "asked for anything. Get it sending punches first.",
        }

    frappe.db.set_single_value("TimeBridge Settings", "enable_photo_transfer", 1)

    baseline = frappe.db.count(
        "TimeBridge Machine User",
        {"machine": machine_id, "photo": ["is", "set"]},
    )

    commands.start_enroll_photo_fetch(machine_id, baseline)
    frappe.db.commit()

    return {
        "status": "queued",
        "baseline_photos": baseline,
        "last_contact": contact.get("at"),
        "message": "Photo switches opened and the request queued. Waiting for the "
                   "device to collect it.",
    }


@frappe.whitelist()
def photo_fetch_status(machine_id, last_contact_before=None):
    """
    How is the photo request going — and is the device still alive?

    The second question is the important one. If the device has fallen silent
    since the switches were opened, they are closed again here rather than
    left for someone to notice later, because a silent device means no punches.
    """

    from frappe.utils import time_diff_in_seconds

    from timebridge.timebridge.adms import commands

    contact = commands.last_contact(machine_id) or {}

    minutes_quiet = None

    if contact.get("at"):
        minutes_quiet = time_diff_in_seconds(frappe.utils.now_datetime(), contact["at"]) / 60

    # Two full poll cycles of silence. The device checks in every 30s, so this
    # is well past coincidence while still reacting quickly.
    went_quiet = minutes_quiet is None or minutes_quiet > 2

    reverted = False

    if went_quiet and cint(
        frappe.db.get_single_value("TimeBridge Settings", "enable_photo_transfer")
    ):
        frappe.db.set_single_value("TimeBridge Settings", "enable_photo_transfer", 0)
        frappe.db.commit()
        reverted = True

    photos_now = frappe.db.count(
        "TimeBridge Machine User",
        {"machine": machine_id, "photo": ["is", "set"]},
    )

    if not went_quiet and not reverted:
        commands.advance_enroll_photo_fetch(machine_id, photos_now)

    fetch_state = frappe.cache().get_value(commands.photo_fetch_key(machine_id)) or {}

    return {
        "photos": photos_now,
        "with_photo": photos_now,
        "users": frappe.db.count("TimeBridge Machine User", {"machine": machine_id}),
        "pending_commands": commands.pending_count(machine_id),
        "fetch_round": cint(fetch_state.get("round")),
        "last_contact": contact.get("at"),
        "minutes_quiet": minutes_quiet,
        "device_quiet": went_quiet,
        "reverted": reverted,
        "photo_transfer_on": cint(
            frappe.db.get_single_value("TimeBridge Settings", "enable_photo_transfer")
        ),
    }


@frappe.whitelist()
def stop_photo_transfer():
    """Close the photo switches — used when the fetch finishes or is closed."""

    frappe.db.set_single_value("TimeBridge Settings", "enable_photo_transfer", 0)
    frappe.db.commit()

    return {"photo_transfer_on": 0}


@frappe.whitelist()
def connection_health(machine_id):
    """
    Everything needed to answer "is this working, and if not, what do I do?".

    Exists so the answer lives on the page rather than in a terminal. The
    checks it cannot make from here — whether Windows' port proxy points at
    the right place — are inferred from whether the device is actually
    arriving, which is the only thing that really matters anyway.
    """

    import socket
    import subprocess

    from timebridge.timebridge.adms import commands

    machine = frappe.get_doc("TimeBridge Machine", machine_id)

    contact = commands.last_contact(machine_id) or {}

    last_punch = frappe.db.sql(
        """
        SELECT MAX(creation) FROM `tabTimeBridge Punch Log` WHERE machine = %s
        """,
        machine_id,
    )[0][0]

    # The address the device must be pointed at is the Windows LAN IP, which
    # this process cannot see from inside WSL — it only knows the gateway it
    # routes through. Reported as "ask the fixer" rather than guessed at.
    wsl_ip = None

    try:
        wsl_ip = subprocess.run(
            ["hostname", "-I"], capture_output=True, text=True, timeout=5
        ).stdout.split()[0]
    except Exception:
        pass

    # Does our own receiver answer? Port comes from the bench config so a
    # site on 8003 (or any other webserver_port) is not reported as down.
    web_port = cint(frappe.conf.get("webserver_port")) or 8000
    receiver_ok = False

    try:
        with socket.create_connection(("127.0.0.1", web_port), timeout=3):
            receiver_ok = True
    except OSError:
        pass

    minutes_since = None

    if contact.get("at"):
        minutes_since = int(
            frappe.utils.time_diff_in_seconds(frappe.utils.now_datetime(), contact["at"]) / 60
        )

    from timebridge.timebridge.services.connection import is_push_device

    is_push = is_push_device(machine)
    device_reachable = None
    port = cint(machine.port) or 4370

    # Pull devices are dialled by us — probe their IP:port. Push devices dial
    # us, so this probe would be meaningless and is skipped.
    if not is_push and machine.ip_address:
        try:
            with socket.create_connection((machine.ip_address, port), timeout=3):
                device_reachable = True
        except OSError:
            device_reachable = False

    return {
        "machine_name": machine.machine_name,
        "serial_number": machine.serial_number,
        "ip_address": machine.ip_address,
        "port": port,
        "sdk_type": machine.sdk_type or "PyZK",
        "is_push": is_push,
        "machine_status": machine.status,
        "device_reachable": device_reachable,
        "receiver_ok": receiver_ok,
        "web_port": web_port,
        "wsl_ip": wsl_ip,
        "last_contact": contact.get("at"),
        "last_contact_kind": contact.get("kind"),
        "minutes_since_contact": minutes_since,
        "last_punch": last_punch,
        "punches_total": frappe.db.count("TimeBridge Punch Log", {"machine": machine_id}),
        "punches_today": frappe.db.count(
            "TimeBridge Punch Log",
            {"machine": machine_id, "timestamp": [">=", frappe.utils.today()]},
        ),
        "users": frappe.db.count("TimeBridge Machine User", {"machine": machine_id}),
        "pending_commands": commands.pending_count(machine_id),
    }


@frappe.whitelist()
def rebuild_attendance(from_date=None, to_date=None, employee=None):
    """
    Rebuild attendance rows from stored punches.

    Runs synchronously: 816 punches across 226 days took well under a second,
    and a background job here would only reintroduce the "did anything
    happen?" problem the progress dialog exists to solve.
    """

    from timebridge.timebridge.services import attendance_sync

    return attendance_sync.rebuild_for_range(
        from_date=from_date or None,
        to_date=to_date or None,
        employee=employee or None,
    )


@frappe.whitelist()
def fetch_status(machine_id):
    """
    How is the re-upload going? Polled by the form while it waits.

    Reports three separate things, because they fail in different ways: has
    the device collected the request, has it spoken to us at all recently, and
    have punches actually landed.
    """

    from timebridge.timebridge.adms import commands
    users_now = frappe.db.count("TimeBridge Machine User", {"machine": machine_id})
    commands.advance_user_fetch(machine_id, users_now, drip=False)

    fetch_state = frappe.cache().get_value(commands.user_fetch_key(machine_id)) or {}
    user_round = cint(fetch_state.get("round"))
    missing = commands.missing_user_pins(machine_id)
    punch_people = len(commands.punch_pins(machine_id))

    # Sync Logs are the honest measure of whether the device answered.
    # Counting only *new* punches would call a correct re-fetch a failure —
    # a device that dutifully re-sends 800 already-stored records adds none,
    # because the unique punch_key rejects every one of them.
    recent = frappe.get_all(
        "TimeBridge Sync Log",
        filters={"machine": machine_id},
        fields=["name", "sync_type", "status", "records_fetched",
                "records_created", "records_skipped", "creation"],
        order_by="creation desc",
        limit=5
    )

    return {
        "punches": frappe.db.count("TimeBridge Punch Log", {"machine": machine_id}),
        # "users": frappe.db.count("TimeBridge Machine User", {"machine": machine_id}),
        "users": users_now,
        "device_registered_users": frappe.db.get_value(
            "TimeBridge Machine", machine_id, "device_registered_users"
        ),
        "sync_logs": frappe.db.count("TimeBridge Sync Log", {"machine": machine_id}),
        "recent_syncs": recent,
        "pending_commands": commands.pending_count(machine_id),
        # "last_contact": commands.last_contact(machine_id)
        "last_contact": commands.last_contact(machine_id),
        "user_fetch_round": user_round,
        "user_fetch_active": bool(fetch_state) and (not punch_people or bool(missing)),
        "missing_users": len(missing),
        "punch_people": punch_people,
    }


@frappe.whitelist()
def preview_employee_link(machine_id, skip_non_person=1, merge_same_name=1, machine_users=None):
    """
    What would attaching this machine's users to TimeBridge Employees do?

    Read-only on purpose. Names are the only evidence a device gives, so the
    operator sees the whole plan — who is matched, who would be created under
    which code, and who is left out — before anything is written.

    machine_users (optional JSON list of Machine User names) narrows the plan.
    """

    from timebridge.timebridge.services.employee_link import plan

    names = frappe.parse_json(machine_users) if machine_users else None

    return plan(
        machine_id,
        skip_non_person=cint(skip_non_person),
        merge_same_name=cint(merge_same_name),
        machine_user_names=names,
    )


@frappe.whitelist()
def create_and_link_employees(
    machine_id,
    date_of_joining,
    organization,
    branch,
    shift=None,
    skip_non_person=1,
    merge_same_name=1,
    machine_users=None,
):
    """
    Create the TimeBridge Employees this machine's users need, attach them, and backfill.

    Synchronous: a few hundred inserts finish well inside a request, and the
    operator is waiting on the answer to decide whether to rebuild attendance.

    machine_users (optional) limits create/link to those Machine User names.
    """

    from timebridge.timebridge.services.employee_link import apply_plan

    names = frappe.parse_json(machine_users) if machine_users else None

    return apply_plan(
        machine_id,
        date_of_joining=date_of_joining,
        organization=organization,
        branch=branch,
        shift=shift or None,
        skip_non_person=cint(skip_non_person),
        merge_same_name=cint(merge_same_name),
        machine_user_names=names,
    )


@frappe.whitelist()
def list_machine_users_for_employee_create(machine=None):
    """
    Candidates for Create TimeBridge Employee from the Machine User list.

    Returns counts plus every unlinked user (optionally for one machine).
    """

    from timebridge.timebridge.services.employee_link import list_candidates

    return list_candidates(machine=machine or None)


@frappe.whitelist()
def create_and_link_selected_employees(
    machine_users,
    date_of_joining,
    organization,
    branch,
    shift=None,
    skip_non_person=1,
    merge_same_name=1,
):
    """
    Create & link TimeBridge Employees for the Machine Users the operator checked.

    Accepts users from more than one machine; grouping and punch backfill stay
    per-machine inside employee_link.apply_selected.
    """

    from timebridge.timebridge.services.employee_link import apply_selected

    return apply_selected(
        machine_users,
        date_of_joining=date_of_joining,
        organization=organization,
        branch=branch,
        shift=shift or None,
        skip_non_person=cint(skip_non_person),
        merge_same_name=cint(merge_same_name),
    )


@frappe.whitelist()
def employee_assignment_summary(machine_id):
    """What TimeBridge Organization, TimeBridge Branch and TimeBridge Shift this machine's TimeBridge Employees carry now."""

    from timebridge.timebridge.services.employee_link import assignment_summary

    return assignment_summary(machine_id)


@frappe.whitelist()
def update_employee_assignment(
    machine_id,
    organization=None,
    branch=None,
    shift=None,
    date_of_joining=None,
):
    """
    Change TimeBridge Organization / TimeBridge Branch / TimeBridge Shift / DOJ
    on this machine's existing TimeBridge Employees.

    Separate from create_and_link_employees on purpose: that one only ever fills
    in people who have none, so it cannot be used to correct the people it
    already created. This corrects them without disturbing a single link.
    """

    from timebridge.timebridge.services.employee_link import apply_assignment

    return apply_assignment(
        machine_id,
        organization=organization or None,
        branch=branch or None,
        shift=shift or None,
        date_of_joining=date_of_joining or None,
    )


@frappe.whitelist()
def update_selected_employee_defaults(
    machine_users,
    organization=None,
    branch=None,
    shift=None,
    date_of_joining=None,
):
    """
    Correct defaults on TimeBridge Employees linked to the checked Machine Users.

    Used from the Machine User list — no Device button required.
    """

    from timebridge.timebridge.services.employee_link import apply_assignment_selected

    return apply_assignment_selected(
        machine_users,
        organization=organization or None,
        branch=branch or None,
        shift=shift or None,
        date_of_joining=date_of_joining or None,
    )


@frappe.whitelist()
def pull_sync_progress(machine_id):
    """
    Where has the queued fetch got to?

    Separate from get_device_info_progress because the two runs are independent
    and can overlap — sharing one cache key would let a connection test
    overwrite the progress of a fetch that is still storing rows.
    """

    from timebridge.timebridge.services.pull_sync import get_progress as pull_progress

    return pull_progress(machine_id)


@frappe.whitelist()
def get_device_info_progress(machine_id):
    """
    Where has the queued device read got to?

    The form polls this instead of listening on the realtime port. Under WSL2
    only IPv4 listeners reach Windows, and Frappe's socketio binds IPv6, so
    realtime events never arrive in the browser here. Polling uses the ordinary
    web port, which does work — and keeps the fix inside this app rather than
    patching Frappe.
    """

    return get_progress(machine_id)


@frappe.whitelist()
def test_connection(machine_id):

    machine = frappe.get_doc(
        "TimeBridge Machine",
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
                "TimeBridge Machine",
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
                "TimeBridge Machine",
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
        

# Ports a ZK-family terminal is actually likely to be speaking on. 4370 is the
# documented default and the one every setup guide repeats, but firmwares in
# the field drift: the K300 at Dantoli answers on 4368 and refuses 4370
# outright. Telnet and HTTP are probed too — not as candidates, but because an
# open one proves the device is alive and only the service port is wrong.
ZK_PORT_CANDIDATES = (4370, 4368, 4369, 4371, 4372, 5005, 5010, 5500)
LIVENESS_PORTS = (23, 80, 8080)

# One second each. Eight candidates plus three liveness checks is eleven
# seconds worst case, and every one of them is a port that either answers at
# once or is not there — a longer wait buys nothing.
PORT_PROBE_TIMEOUT = 1


@frappe.whitelist()
def find_device_port(machine_id):
    """
    Work out which port a device is really listening on.

    Test Connection can only report that the configured port did not answer.
    That leaves three very different situations looking identical: the address
    is wrong, the device is asleep, or the device is right there but listening
    somewhere else. Telling them apart used to mean someone running probes by
    hand at a terminal.

    Nothing here changes the machine. It reports what it found and leaves the
    decision — and the saving — to whoever pressed the button.
    """

    from timebridge.timebridge.services.device_info import probe_socket

    machine = frappe.db.get_value(
        "TimeBridge Machine", machine_id, ["ip_address", "port"], as_dict=True
    )

    if not machine or not machine.ip_address:
        return {"checked": False, "message": "This machine has no IP address to scan."}

    configured = cint(machine.port)

    open_ports = []
    refused = False

    def look(port):
        """A refused connection is a live host saying no — worth knowing."""

        nonlocal refused

        ok, detail = probe_socket(machine.ip_address, port, timeout=PORT_PROBE_TIMEOUT)

        if ok:
            open_ports.append(port)
        elif "refused" in (detail or "").lower():
            refused = True

    for port in ZK_PORT_CANDIDATES:
        look(port)

    for port in LIVENESS_PORTS:
        look(port)

    # Only a plausible protocol port is offered as the answer. Telnet being
    # open says the device is awake; it does not mean attendance can be read
    # over it, and suggesting it would send someone down a dead end.
    suggestion = next(
        (p for p in ZK_PORT_CANDIDATES if p in open_ports and p != configured), None
    )

    return {
        "checked": True,
        "ip_address": machine.ip_address,
        "configured_port": configured,
        "open_ports": open_ports,
        "suggestion": suggestion,
        # Something answered — either an open port or an explicit refusal — so
        # the address itself is right and the device is powered on.
        "reachable": bool(open_ports) or refused,
    }


@frappe.whitelist()
def start_photo_collection(machine_id):
    """
    Open a photo-collecting session and report where it stands.

    Collecting is not something this can do on its own: pictures arrive
    because people punch, and the device has to be set to photograph them.
    What is missing without this is any sense of progress — sixteen names to
    keep in your head, and no moment where the job is done.

    The transfer switch is opened here because a session with it shut would
    wait forever for photographs the device was never permitted to send.
    """

    frappe.db.set_single_value("TimeBridge Settings", "enable_photo_transfer", 1)
    frappe.db.commit()

    return photo_collection_status(machine_id)


@frappe.whitelist()
def photo_collection_status(machine_id):
    """
    Who on this device has a photograph, and who is still to be caught.

    Somebody flagged for a retake counts as outstanding even though a picture
    is on file: the one there is the one being replaced, so the job is not
    finished until a new one lands.
    """

    rows = frappe.db.sql(
        """
        SELECT mu.name, mu.user_id, mu.user_name, mu.photo, mu.retake_photo,
               emp.employee
        FROM `tabTimeBridge Machine User` mu
        LEFT JOIN `tabTimeBridge Employee` emp ON emp.name = mu.employee
        WHERE mu.machine = %(machine)s
        ORDER BY CAST(mu.user_id AS UNSIGNED), mu.user_id
        """,
        {"machine": machine_id},
        as_dict=True,
    )

    done = []
    pending = []

    for row in rows:

        entry = {
            "machine_user": row.name,
            "user_id": row.user_id,
            "name": row.employee or row.user_name or row.user_id,
            "photo": row.photo,
        }

        if row.photo and not cint(row.retake_photo):
            done.append(entry)
        else:
            entry["retaking"] = bool(row.photo and cint(row.retake_photo))
            pending.append(entry)

    return {
        "total": len(rows),
        "done": done,
        "pending": pending,
        "finished": bool(rows) and not pending,
    }


@frappe.whitelist()
def request_photo_retake(machine_user):
    """
    Put one person back in the queue for a fresh photograph.

    The picture already on file is left alone until a new one arrives, so a
    poor photo is still better than none while waiting for the next punch.
    """

    frappe.db.set_value("TimeBridge Machine User", machine_user, "retake_photo", 1)
    frappe.db.commit()

    return {"machine_user": machine_user, "retake": True}
