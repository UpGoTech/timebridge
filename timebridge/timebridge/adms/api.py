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

from frappe.utils import cint

from timebridge.timebridge.adms import commands, logger, parser, photos, stamps
from timebridge.timebridge.services.machine_log import write_machine_log

# Handshake reply. The device parses these keys to decide how often to talk to
# us and what it is allowed to send. Realtime=1 asks it to push as punches
# happen rather than only on its own timer; Encrypt=0 keeps the body readable.
# TransFlag is a ten-position switch telling the device which kinds of data it
# is permitted to send us. Positions, in Attendance PUSH order:
#
#   1 AttLog   2 OpLog   3 AttPhoto  4 EnrollFP  5 EnrollUser
#   6 FPImage  7 ChgUser 8 ChgFP     9 FACE     10 UserPic
#
# This is NOT the order in the Security PUSH document kept in spec/, which is a
# different protocol: there EnrollUser is 4 and ChgUser is 5. Following it left
# "1111000000" asking for fingerprint enrolments while switching off the two
# flags — EnrollUser and ChgUser — that make the device report its people at all.
#
# Punches need AttLog and AttPhoto; TimeBridge Machine Users need EnrollUser
# and ChgUser on the OPERLOG table. OpLog (position 2) is the device audit
# channel (OPLOG rows — door opened, admin login). Fabrixcel Gate floods it
# with empty POSTs when enabled; USER rows are gated by EnrollUser (5), not
# OpLog (2). FACE and UserPic (positions 9 and 10) open during Fetch Photos.
TRANSFLAG_PUNCHES_ONLY = "1010101000"
TRANSFLAG_WITH_PHOTOS = "1010101011"

# The device polls /iclock/getrequest every Delay seconds and looks for new data
# to transmit every TransInterval minutes. Realtime=1 makes punches leave as
# they happen, but the interval still governs the catch-up sweep, and a firmware
# given no interval falls back to its own default.
HANDSHAKE_TEMPLATE = (
    "GET OPTION FROM: {serial}\n"
    "Stamp={stamp}\n"
    "ATTLOGStamp={stamp}\n"
    "OPERLOGStamp={opstamp}\n"
    "ATTPHOTOStamp=9999\n"
    "ErrorDelay=30\n"
    "Delay=30\n"
    "TransTimes=00:00;14:00\n"
    "TransInterval=1\n"
    "TransFlag={transflag}\n"
    "TimeZone={timezone}\n"
    "Realtime=1\n"
    "Encrypt=0\n"
)


def build_handshake(serial, machine=None):
    stamp, opstamp = stamps.handshake_stamps(machine)
    return HANDSHAKE_TEMPLATE.format(
        serial=serial or "UNKNOWN",
        stamp=stamp,
        opstamp=opstamp,
        transflag=current_transflag(),
        timezone=server_timezone_option(),
    )


def server_timezone_option():
    """
    TimeZone for the handshake, in the encoding the protocol asks for: whole
    hours when the offset has none, otherwise minutes — so +05:30 is 330, not
    5.5. The device syncs its clock from this together with the Date header, and
    a wrong value shifts every punch it reports afterwards.
    """

    from datetime import datetime
    from zoneinfo import ZoneInfo

    try:
        offset = datetime.now(
            ZoneInfo(frappe.utils.get_system_timezone())
        ).utcoffset()
        minutes = int(offset.total_seconds() // 60)
    except Exception:
        return "0"

    if minutes % 60 == 0:
        return str(minutes // 60)

    return str(minutes)


def ack(count):
    """
    Acknowledge a data upload.

    Attendance PUSH §11.2-11.5: a POST is answered with "OK: <n>" naming how
    many records were processed, and "when an error occurs, the error
    description is replied". A bare "OK" is neither, so the firmware reads the
    upload as failed, keeps the batch and re-sends it on every cycle — which is
    what had this device pushing the same 128 records hundreds of times over.

    The count is everything the device handed us, duplicates included: a punch
    we already hold was still processed successfully, and answering "OK: 0" to a
    batch we have seen before restarts the same loop.
    """

    return f"OK: {cint(count)}"


def current_transflag():
    """Which switches the handshake currently offers, per TimeBridge Settings."""

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
        if machine:
            write_machine_log(
                machine=machine,
                serial=serial,
                level="Info",
                event="Handshake",
                message="ADMS handshake",
            )
        return build_handshake(serial, machine)

    if not machine:
        write_machine_log(
            serial=serial,
            level="Warning",
            event="Upload",
            message=f"Upload from unknown serial {serial!r}",
            details=body[:2000] if body else None,
        )
        return "OK"

    table = parser.parse_table_name(args.get("table"))

    if table == "ATTLOG":
        return _receive_attlog(machine, args, body)

    if table in ("OPERLOG", "USERINFO"):
        return _receive_userinfo(machine, args, body)

    if table in photos.PHOTO_TABLES:
        photo_rows = parser.parse_photo_fields(body)
        photos.handle_photo(machine, args, raw, body, table)
        count = len(photo_rows) or 1
        write_machine_log(
            machine=machine,
            level="Info",
            event="Upload",
            message=f"{table}: {count} photo row(s)",
        )
        return ack(count)

    if table == "OPTIONS" or (table and table.upper() == "OPTIONS"):
        write_machine_log(
            machine=machine,
            level="Info",
            event="Upload",
            message="OPTIONS parameter upload",
            details=body[:500] if body else None,
        )
        return "OK"

    if parser.is_template_table(args, table):
        line_count = _body_line_count(body)
        write_machine_log(
            machine=machine,
            level="Info",
            event="Upload",
            message=f"{table}: {line_count} template row(s)",
        )
        return ack(line_count)

    # Unrecognised table: acknowledge so the device does not retry forever,
    # but leave a trace that something arrived we do not handle yet.
    write_machine_log(
        machine=machine,
        serial=serial,
        level="Warning",
        event="Upload",
        message=f"Unhandled ADMS table {table!r}",
    )

    return ack(_body_line_count(body))


def _body_line_count(body):
    """How many records a payload carried, for the acknowledgement."""

    return len([line for line in (body or "").splitlines() if line.strip()])


def _operlog_is_heartbeat(records, op_rows, photo_rows):
    """True when the POST carried nothing TimeBridge models as users/ops/photos."""

    return not records and not op_rows and not photo_rows


def _operlog_ack_count(body, records, skipped, op_rows, photo_rows):
    """Lines the device sent — under-counting reads as a partial failure."""

    count = max(
        _body_line_count(body),
        len(records) + len(skipped),
        len(op_rows),
        len(photo_rows),
    )
    # Fabrixcel Gate (NCD8251400238) re-posts empty OPERLOG every ~200 ms when
    # answered OK: 0. Same failure mode as ATTLOG duplicates — the batch was
    # accepted, so the count must not read as zero.
    if count == 0:
        return 1

    return count


def _receive_attlog(machine, args, body):

    records, skipped = parser.parse_attlog(body)
    table = parser.parse_table_name(args.get("table"))
    fetched = len(records) + len(skipped)

    try:
        result = logger.save_punches(machine, records)

        sync_batch = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        log_name = logger.open_sync_log(machine, "Attendance", sync_batch)
        logger.close_sync_log(
            log_name,
            "Success",
            fetched=fetched,
            created=result["created"],
            skipped=result["duplicates"] + result["invalid"] + len(skipped),
            error=(
                f"{len(skipped)} unparseable line(s), {result['invalid']} bad timestamp(s), "
                f"{result['unmatched']} punch(es) with no TimeBridge Machine User"
                if (skipped or result["invalid"] or result["unmatched"]) else None
            ),
        )
        write_machine_log(
            machine=machine,
            level="Info",
            event="Upload",
            message=(
                f"ATTLOG: {fetched} row(s), {result['created']} new, "
                f"{result['duplicates']} duplicate(s)"
            ),
        )

        stamps.record_attlog_stamp(machine, args, table, records)

        frappe.db.commit()

        frappe.logger().info(
            f"[TimeBridge ADMS] {machine}: {result['created']} new, "
            f"{result['duplicates']} dup, {result['unmatched']} unmatched"
        )

    except Exception:
        frappe.db.rollback()
        tb = frappe.get_traceback()
        sync_batch = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
        log_name = logger.open_sync_log(machine, "Attendance", sync_batch)
        logger.close_sync_log(log_name, "Failed", fetched=fetched, error=tb[:1000])
        write_machine_log(
            machine=machine,
            level="Error",
            event="Upload",
            message="ATTLOG ingest failed",
            details=tb,
        )
        frappe.db.commit()
        frappe.log_error(title="TimeBridge ADMS: ATTLOG failed", message=tb)

        # Nothing was stored, so ask for the batch again. The protocol's retry
        # signal is an error description in a 200 body — an HTTP 500 is what
        # makes the firmware throw the records away, and that is still avoided.
        return "Error: ATTLOG ingest failed"

    return ack(fetched)


def _receive_userinfo(machine, args, body):

    records, skipped = parser.parse_userinfo(body)
    photo_rows = parser.parse_photo_fields(body)
    op_rows = parser.parse_oplog(body)
    table = parser.parse_table_name(args.get("table"))

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
            write_machine_log(
                machine=machine,
                level="Info",
                event="Upload",
                message=(
                    f"OPERLOG: {len(records) + len(skipped)} user row(s), "
                    f"{result['created']} new"
                ),
            )

            frappe.db.set_value("TimeBridge Machine", machine, "last_user_sync",
                                frappe.utils.now_datetime())
            stamps.record_operlog_stamp(
                machine,
                args,
                table,
                op_rows=op_rows,
                heartbeat=_operlog_is_heartbeat(records, op_rows, photo_rows),
            )
            frappe.db.commit()

        except Exception:
            frappe.db.rollback()
            tb = frappe.get_traceback()
            logger.close_sync_log(log_name, "Failed", fetched=len(records),
                                  error=tb[:1000])
            write_machine_log(
                machine=machine,
                level="Error",
                event="Upload",
                message="USERINFO ingest failed",
                details=tb,
            )
            frappe.db.commit()
            frappe.log_error(title="TimeBridge ADMS: USERINFO failed", message=tb)

            return "Error: USERINFO ingest failed"

    else:
        # Most OPERLOG uploads carry no people — operation rows, photo fields,
        # or an empty heartbeat. Non-empty batches are logged; empty heartbeats
        # only advance the stamp (Fabrixcel floods them when answered OK: 0).
        fetched = _body_line_count(body)
        heartbeat = _operlog_is_heartbeat(records, op_rows, photo_rows)

        if not heartbeat:
            operlog_note = (
                f"{len(op_rows)} operation row(s), {len(photo_rows)} photo row(s), "
                "no user records"
            )
            sync_batch = frappe.utils.now_datetime().strftime("%Y-%m-%d %H:%M:%S")
            log_name = logger.open_sync_log(machine, "Users", sync_batch)
            logger.close_sync_log(
                log_name,
                "Success",
                fetched=fetched,
                created=0,
                skipped=len(skipped),
                error=operlog_note,
            )
            write_machine_log(
                machine=machine,
                level="Info",
                event="Upload",
                message=f"OPERLOG: {operlog_note}",
            )

        stamps.record_operlog_stamp(
            machine, args, table, op_rows=op_rows, heartbeat=_operlog_is_heartbeat(records, op_rows, photo_rows)
        )
        frappe.db.commit()

    # Enrolment pictures often ride in OPERLOG as PIN + Content, not as a
    # USERPIC table. Harvest them even when the POST had no people to save.
    if photo_rows:

        try:
            if photos.save_photos_from_fields(machine, photo_rows, "BIOPHOTO"):
                frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            tb = frappe.get_traceback()
            write_machine_log(
                machine=machine,
                level="Error",
                event="Photo",
                message="OPERLOG photo harvest failed",
                details=tb,
            )
            frappe.log_error(
                title="TimeBridge ADMS: OPERLOG photo harvest failed",
                message=tb,
            )

    # Count every line the device sent, not just the ones we model. An OPERLOG
    # is a mixed bag of USER, OPLOG and photo rows, and under-counting it reads
    # to the firmware as a partial failure.
    return ack(_operlog_ack_count(body, records, skipped, op_rows, photo_rows))


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

    write_machine_log(
        machine=machine,
        serial=serial,
        level="Info",
        event="Heartbeat",
        message="ADMS heartbeat (getrequest)",
    )

    pending = commands.pop_commands(machine)

    if pending:
        write_machine_log(
            machine=machine,
            serial=serial,
            level="Info",
            event="Command",
            message=f"Sending {len(pending)} command(s) to device",
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

        write_machine_log(
            machine=machine,
            serial=serial,
            level="Info",
            event="Command",
            message="Device command result",
            details=body[:500] if body else None,
        )

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

    tablename = (args.get("tablename") or "").strip()
    write_machine_log(
        machine=machine,
        serial=serial,
        level="Info",
        event="Upload",
        message=f"querydata {method} {tablename or 'unknown table'}".strip(),
        details=body[:500] if body else None,
    )

    if method == "POST" and tablename.lower() in ("biodata", "templatev10"):
        return "OK"

    return "OK"


def handle_ping(serial, args, body, method, raw=None):
    """Some firmwares probe this before talking properly."""

    machine = logger.get_machine_by_serial(serial)
    if machine:
        write_machine_log(
            machine=machine,
            serial=serial,
            level="Info",
            event="Ping",
            message="ADMS ping",
        )

    return "OK"


def handle_fdata(serial, args, body, method, raw=None):
    """
    Photograph upload. Most firmwares POST raw JPEG bytes here.

    Kept separate from cdata because the payload is binary — decoding it as
    text, which cdata does, would corrupt every image.
    """

    machine = logger.get_machine_by_serial(serial)

    if not machine:

        write_machine_log(
            serial=serial,
            level="Warning",
            event="Photo",
            message=f"Photo from unknown serial {serial!r}",
        )

        return "OK"

    commands.record_contact(machine, "photo upload")

    if method == "POST":
        photos.handle_photo(machine, args, raw, body, "fdata")
        payload = raw if raw is not None else body
        size = len(payload) if payload else 0
        write_machine_log(
            machine=machine,
            serial=serial,
            level="Info",
            event="Upload",
            message=f"fdata photo upload ({size} bytes)",
        )

    return "OK"
