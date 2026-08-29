# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS / "iclock" endpoint handlers.

The device drives everything here — it dials out to us on a timer and POSTs its
records. We never connect to it. This is the only way to get data out of an
eSSL AIFace MARS, which does not answer the classic pyzk pull protocol.

Device-side setup (AIFace MARS):
    Menu -> Comm -> Cloud Server Setting / ADMS
        Server Address: the host running Frappe (reachable from the device)
        Server Port:    the Frappe port, e.g. 8000
    The device then calls /iclock/cdata on its own schedule.

Routing note: the firmware's paths are fixed, so these are reached through the
ADMSRenderer page_renderer hook rather than /api/method/... See renderer.py.

Security note: these endpoints are necessarily unauthenticated — the device
cannot log in or carry a CSRF token. Pushes whose SN does not match a
registered TimeBridge Machine are rejected and logged, so an unknown sender
cannot create records.
"""

import frappe

from timebridge.timebridge.adms import commands, logger, parser, photos
from timebridge.timebridge.services import biometric_templates

# Handshake reply. The device parses these keys to decide how often to talk to
# us and what it is allowed to send. Realtime=1 asks it to push as punches
# happen rather than only on its own timer; Encrypt=0 keeps the body readable.
# TransFlag is a ten-position switch telling the device which kinds of data it
# is permitted to send us. Positions, in order:
#
#   1 AttLog   2 OpLog    3 AttPhoto  4 EnrollUser  5 ChgUser
#   6 EnrollFP 7 ChgFP    8 FPImage   9 FACE       10 UserPic
#
# Punches need AttLog, OpLog, AttPhoto and EnrollUser. FACE and UserPic
# (positions 9 and 10) are what permit enrolment photographs — Bio-Photo —
# and are opened only while Fetch Photos is running. The middle switches
# (fingerprint images and the rest) stay off: they are unused here, and
# turning every bit on is what some firmwares reject.
TRANSFLAG_PUNCHES_ONLY = "1111000000"
TRANSFLAG_WITH_PHOTOS = "1111000011"

HANDSHAKE_TEMPLATE = (
    "GET OPTION FROM: {serial}\n"
    "Stamp=9999\n"
    "OpStamp=9999\n"
    "ErrorDelay=30\n"
    "Delay=30\n"
    "TransFlag={transflag}\n"
    "Realtime=1\n"
    "Encrypt=0\n"
)


def current_transflag():
    """Which switches the handshake currently offers, per TimeBridge Settings."""

    from frappe.utils import cint

    if cint(frappe.db.get_single_value("TimeBridge Settings", "enable_photo_transfer")):
        return TRANSFLAG_WITH_PHOTOS

    return TRANSFLAG_PUNCHES_ONLY


def handle_cdata(serial, args, body, method, raw=None):
    """
    Both phases of the protocol land here:
      GET  /iclock/cdata?SN=...&options=all      -> handshake
      POST /iclock/cdata?SN=...&table=ATTLOG     -> punch records
      POST /iclock/cdata?SN=...&table=OPERLOG    -> user records
    """

    machine = logger.get_machine_by_serial(serial)

    if machine:
        commands.record_contact(machine, "handshake" if method in ("GET", "HEAD") else "upload")

    if method in ("GET", "HEAD"):
        return HANDSHAKE_TEMPLATE.format(
            serial=serial or "UNKNOWN", transflag=current_transflag()
        )

    if not machine:
        # Refuse to store data for a device nobody registered, but keep the
        # payload so the serial can be matched up afterwards.
        frappe.log_error(
            title="TimeBridge ADMS: unknown device serial",
            message=f"Serial {serial!r} matches no TimeBridge Machine.\n\nBody:\n{body[:2000]}",
        )
        return "OK"

    table = parser.parse_table_name(args.get("table"))

    if table == "ATTLOG":
        return _receive_attlog(machine, body)

    if table in ("OPERLOG", "USERINFO"):
        return _receive_userinfo(machine, body)

    if table in photos.PHOTO_TABLES:
        photos.handle_photo(machine, args, raw, body, table)
        return "OK"

    if table == "OPTIONS" or (table and table.upper() == "OPTIONS"):
        return _receive_options(machine, body)

    if parser.is_template_table(args, table):
        return _receive_templates(machine, args, table, body, source="ADMS Push")

    # Unrecognised table: acknowledge so the device does not retry forever,
    # but leave a trace that something arrived we do not handle yet.
    frappe.logger().info(f"[TimeBridge ADMS] {serial}: unhandled table {table!r}")

    return "OK"


def _receive_attlog(machine, body):

    records, skipped = parser.parse_attlog(body)

    sync_batch = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
    log_name = logger.open_sync_log(machine, "Attendance", sync_batch)

    try:
        result = logger.save_punches(machine, records, sync_batch=sync_batch)

        logger.close_sync_log(
            log_name,
            "Success",
            fetched=len(records) + len(skipped),
            created=result["created"],
            skipped=result["duplicates"] + result["invalid"] + len(skipped),
            error=(
                f"{len(skipped)} unparseable line(s), {result['invalid']} bad timestamp(s), "
                f"{result['unmatched']} punch(es) with no TimeBridge Machine User"
                if (skipped or result["invalid"] or result["unmatched"]) else None
            ),
        )

        frappe.db.commit()

        frappe.logger().info(
            f"[TimeBridge ADMS] {machine}: {result['created']} new, "
            f"{result['duplicates']} dup, {result['unmatched']} unmatched"
        )

        if _mirror_verify_active(machine):
            commands.note_mirror_attlog_batch(machine, len(records))

    except Exception:
        frappe.db.rollback()
        logger.close_sync_log(log_name, "Failed", fetched=len(records),
                              error=frappe.get_traceback()[:1000])
        frappe.db.commit()
        frappe.log_error(title="TimeBridge ADMS: ATTLOG failed", message=frappe.get_traceback())

    # The device only wants an acknowledgement. Reporting a failure here would
    # make it discard the batch, and we would rather keep it for a retry.
    return "OK"


def _receive_userinfo(machine, body):

    records, skipped = parser.parse_userinfo(body)
    photo_rows = parser.parse_photo_fields(body)

    if records:

        sync_batch = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        log_name = logger.open_sync_log(machine, "Users", sync_batch)

        try:
            result = logger.save_users(machine, records)

            # Devices routinely send punches before the users they belong to, so
            # backfill the links now that more users are known.
            linked = logger.link_unmatched_punches(machine)

            logger.close_sync_log(
                log_name,
                "Success",
                fetched=len(records) + len(skipped),
                created=result["created"],
                skipped=len(skipped),
                error=(f"{linked} earlier punch(es) linked" if linked else None),
            )

            frappe.db.set_value("TimeBridge Machine", machine, "last_user_sync",
                                frappe.utils.now_datetime())
            frappe.db.commit()

        except Exception:
            frappe.db.rollback()
            logger.close_sync_log(log_name, "Failed", fetched=len(records),
                                  error=frappe.get_traceback()[:1000])
            frappe.db.commit()
            frappe.log_error(title="TimeBridge ADMS: USERINFO failed", message=frappe.get_traceback())

    # Enrolment pictures often ride in OPERLOG as PIN + Content, not as a
    # USERPIC table. Harvest them even when the POST had no people to save.
    if photo_rows:

        try:
            if photos.save_photos_from_fields(machine, photo_rows, "BIOPHOTO"):
                frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(
                title="TimeBridge ADMS: OPERLOG photo harvest failed",
                message=frappe.get_traceback(),
            )

    return "OK"


def handle_getrequest(serial, args, body, method, raw=None):
    """
    The device asking "any commands for me?".

    This poll is the only opening we get — the device accepts no incoming
    connections — so it is where a "send your data again" request is handed
    over.
    """

    machine = logger.get_machine_by_serial(serial)

    if not machine:
        return "OK"

    commands.record_contact(machine, "poll")

    pending = commands.pop_commands(machine)

    if pending:
        frappe.logger().info(
            f"[TimeBridge ADMS] {machine}: sending {len(pending)} command(s)"
        )

    return commands.format_commands(pending)


def handle_devicecmd(serial, args, body, method, raw=None):
    """
    The device reporting what happened to a command we sent.

    Only logged. The real evidence that a re-upload worked is punches arriving
    on /iclock/cdata, not this acknowledgement.
    """

    machine = logger.get_machine_by_serial(serial)

    if machine:
        commands.record_contact(machine, "command result")

        if _mirror_verify_active(machine):
            _handle_mirror_devicecmd(machine, body)

        frappe.logger().info(f"[TimeBridge ADMS] {machine}: command result {body[:200]!r}")

    return "OK"


def handle_querydata(serial, args, body, method, raw=None):
    """
    Device upload in reply to a DATA QUERY command.

    Count probes use type=count; template pulls use type=tabledata.
    """

    machine = logger.get_machine_by_serial(serial)

    if not machine:
        return "OK"

    commands.record_contact(machine, "querydata")

    query_type = (args.get("type") or "").strip().lower()
    tablename = (args.get("tablename") or "").strip().lower()

    if method == "POST" and query_type == "count":
        return _receive_count_probe(machine, tablename, body)

    if method == "POST" and query_type == "tabledata" and tablename in ("biodata", "templatev10"):
        return _receive_templates(machine, args, None, body, source="ADMS Query")

    if _mirror_verify_active(machine) and method == "POST" and tablename == "attlog":
        records, _ = parser.parse_attlog(body)
        commands.note_mirror_attlog_batch(machine, len(records))

    return "OK"


def _mirror_verify_active(machine):
    """Whether a mirror verify run is in progress."""

    state = frappe.cache().get_value(commands.mirror_verify_key(machine)) or {}
    return bool(state.get("active"))


def _receive_options(machine, body):
    """Device parameter push (§4.6) — inventory counts."""

    counts = parser.parse_options(body)
    commands.note_mirror_options(machine, counts)
    return "OK"


def _receive_count_probe(machine, tablename, body):
    """DATA COUNT response on querydata."""

    count = parser.parse_count_response(body)
    commands.note_mirror_count(machine, tablename or "unknown", count)
    return "OK"


def _receive_templates(machine, args, table, body, source):
    """Ingest templatev10 / biodata uploads."""

    source_table = parser.template_upload_source(args, table)

    if source_table == "templatev10":
        records, skipped = parser.parse_templatev10(body)
    else:
        records, skipped = parser.parse_biodata(body)

    if not records:
        return "OK"

    try:
        created, updated = biometric_templates.upsert_templates(
            machine, records, source=source, source_table=source_table
        )
        frappe.db.commit()
        frappe.logger().info(
            f"[TimeBridge ADMS] {machine}: templates {created} new, {updated} updated "
            f"({len(skipped)} skipped)"
        )
    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="TimeBridge ADMS: template ingest failed",
            message=frappe.get_traceback(),
        )

    return "OK"


def _handle_mirror_devicecmd(machine, body):
    """Parse GET OPTIONS response delivered via devicecmd."""

    counts = parser.parse_options(body)

    if counts:
        commands.note_mirror_options(machine, counts)


def handle_ping(serial, args, body, method, raw=None):
    """Some firmwares probe this before talking properly."""

    return "OK"


def handle_fdata(serial, args, body, method, raw=None):
    """
    Photograph upload. Most firmwares POST raw JPEG bytes here.

    Kept separate from cdata because the payload is binary — decoding it as
    text, which cdata does, would corrupt every image.
    """

    machine = logger.get_machine_by_serial(serial)

    if not machine:

        frappe.log_error(
            title="TimeBridge ADMS: photo from unknown device serial",
            message=f"Serial {serial!r} matches no TimeBridge Machine.",
        )

        return "OK"

    commands.record_contact(machine, "photo upload")

    if method == "POST":
        photos.handle_photo(machine, args, raw, body, "fdata")

    return "OK"
