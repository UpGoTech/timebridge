# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Receiving user and punch photographs from a push device.

Firmwares disagree about how pictures arrive — some POST them to /iclock/fdata
as raw bytes with the user id in the query string, others send them on cdata
under a table name with the image base64-encoded in the body. Both shapes are
accepted here, because guessing wrong means silently discarding photographs
and then wondering why none ever appear.

Nothing about this is guaranteed to fire: whether a device sends pictures at
all depends on its own settings and on whether it stores them. Anything that
arrives in a shape not recognised is logged in full rather than dropped, so
the format can be read off a real payload instead of guessed at.
"""

import base64
import re

import frappe

from frappe.utils import cint

from timebridge.timebridge.adms import parser

# Tables that carry pictures rather than punches, across the firmwares that
# name them differently.
PHOTO_TABLES = {"ATTPHOTO", "USERPIC", "USERPHOTO", "FACE", "BIOPHOTO"}

# Enrolment pictures (Bio-Photo / User Photo). Daily punch snapshots are
# ATTPHOTO — those are a different setting on the device and must not become
# the face on Machine User or Employee.
ENROLL_PHOTO_SOURCES = {"USERPIC", "USERPHOTO", "BIOPHOTO"}
PUNCH_PHOTO_SOURCES = {"ATTPHOTO"}

# JPEG and PNG magic numbers — used to tell an actual image from base64 text
# or from a stray error string.
IMAGE_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")

MAX_LOGGED_BYTES = 1500


def looks_like_image(data):

    return isinstance(data, bytes) and data.startswith(IMAGE_SIGNATURES)


# The AIFace MARS does not put a user id in PIN at all. It puts the name of
# the file it is uploading:
#
#     PIN=20260811175148-4.jpg
#          └────┬─────┘ └┬┘
#          when it was    who it was
#          taken          (device user id)
#
# Read literally that is a user id of "20260811175148-4.jpg", which matches
# nobody, and every photograph was logged as unattributable.
PHOTO_FILENAME = re.compile(
    r"^\d{8,14}[-_](?P<user_id>[^-_.\s]+)\.(?:jpe?g|png|bmp)$", re.IGNORECASE
)


def user_id_from_filename(value):
    """
    Pull the device user id back out of an uploaded photo's file name.

    Returns the value unchanged when it is not a file name, so firmwares that
    do send a plain id keep working.
    """

    match = PHOTO_FILENAME.match(value or "")

    return match.group("user_id") if match else value


def is_punch_snapshot(source, args):
    """
    True when this is a daily attendance picture, not the one taken at enroll.

    ATTPHOTO is that table. Some firmwares POST the same snapshot to /fdata
    with PIN=YYYYMMDDHHMMSS-<userid>.jpg — the filename, not the table name,
    is what gives it away.
    """

    if source in PUNCH_PHOTO_SOURCES:
        return True

    pin = ""

    for key in ("PIN", "pin"):
        if args.get(key):
            pin = str(args[key]).strip()
            break

    return bool(PHOTO_FILENAME.match(pin))


def extract_user_id(args, body_text):
    """
    The user id can be in the query string or the body, depending on firmware.

    Returns None when it cannot be found — a picture we cannot attribute to a
    person is useless, and inventing an owner would be worse than dropping it.
    """

    for key in ("PIN", "pin", "UserID", "userid", "USERID"):
        if args.get(key):
            return user_id_from_filename(str(args[key]).strip())

    match = re.search(r"\bPIN=([^\s\t&]+)", body_text or "")

    return user_id_from_filename(match.group(1).strip()) if match else None


def decode_image(raw_bytes, body_text):
    """
    Get image bytes out of whatever arrived.

    Raw binary is used as-is. Otherwise the body is searched for a base64
    blob, which is how the cdata-style uploads carry the picture.
    """

    if looks_like_image(raw_bytes):
        return raw_bytes

    # This firmware puts its own header lines first and the picture straight
    # after them, with no separator and no encoding:
    #
    #     PIN=20260811175148-4.jpg
    #     SN=TBS2260500936
    #     size=48750
    #     CMD=uploadphoto
    #     <JPEG bytes>
    #
    # So the body neither starts with an image nor holds base64, and both of
    # the paths below missed it. Looking for the signature anywhere in the
    # bytes costs nothing and catches every layout of this shape.
    if isinstance(raw_bytes, bytes):

        for signature in IMAGE_SIGNATURES:

            start = raw_bytes.find(signature)

            if start > 0:
                return raw_bytes[start:]

    # CMD=... PIN=... SIZE=... CONTENT=<base64>
    match = re.search(r"(?:CONTENT|PHOTO|IMAGE)=([A-Za-z0-9+/=\r\n]+)", body_text or "")

    candidate = match.group(1) if match else (body_text or "").strip()

    if len(candidate) < 64:
        return None

    try:
        decoded = base64.b64decode(candidate, validate=False)
    except Exception:
        return None

    return decoded if looks_like_image(decoded) else None


def decode_field_image(content):
    """Turn one Content= / PHOTO= value into JPEG bytes, or None."""

    if not content or len(content) < 64:
        return None

    try:
        decoded = base64.b64decode(content, validate=False)
    except Exception:
        return None

    return decoded if looks_like_image(decoded) else None


def save_photos_from_fields(machine, rows, source):
    """
    Store every PIN + Content row that actually decodes as a picture.

    Returns how many were written. Callers commit.
    """

    saved = 0

    for row in rows:

        image = decode_field_image(row.get("content"))

        if not image:
            continue

        if save_photo(machine, row["user_id"], image, source):
            saved += 1

    return saved


def sync_employee_photo(employee, file_url, replace=False):
    """
    Put the same picture on the Employee record.

    Machine User is the device's record of a person; Employee is the company's.
    Reports, lists and the person's own page all read Employee, so a face that
    only ever reaches Machine User is a face nobody sees.

    The same file is pointed at rather than written twice — one picture, two
    records referring to it.
    """

    if not employee or not file_url:
        return

    current = frappe.db.get_value("Employee", employee, "photo")

    # A photograph someone uploaded by hand outranks anything a camera caught
    # at a doorway, so it is only overwritten when a retake was asked for.
    if current and not replace:
        return

    if current != file_url:
        frappe.db.set_value("Employee", employee, "photo", file_url)


def save_photo(machine, user_id, image_bytes, source):
    """
    Attach the picture to the Machine User and show it on the record.

    Returns the file url, or None when the user is not one we know — an
    unknown id means the device and our records disagree, which is worth
    seeing rather than papering over.
    """

    existing = frappe.db.get_value(
        "Machine User",
        {"machine": machine, "user_id": user_id},
        ["name", "photo", "retake_photo", "employee"],
        as_dict=True,
    )

    if not existing:
        frappe.log_error(
            title="TimeBridge ADMS: photo for unknown user",
            message=f"Machine {machine} sent a photo for user id {user_id!r}, "
                    f"which has no Machine User record.",
        )
        return None

    machine_user = existing.name

    # Enrolment photos replace whatever is already on the record — including
    # a leftover daily punch snapshot, which is not the face taken at register.
    enroll = source in ENROLL_PHOTO_SOURCES or source in ("fdata", "FACE")
    replace = enroll or cint(existing.retake_photo)

    if existing.photo and not replace:

        sync_employee_photo(existing.employee, existing.photo)

        frappe.logger().info(
            f"[TimeBridge ADMS] {machine}: user {user_id} already has a photo "
            f"— not replacing it"
        )
        return existing.photo

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": f"{machine}-{user_id}.jpg",
        "attached_to_doctype": "Machine User",
        "attached_to_name": machine_user,
        "attached_to_field": "photo",
        "content": image_bytes,
        "decode": False,
        "is_private": 0,
    }).insert(ignore_permissions=True)

    frappe.db.set_value("Machine User", machine_user, "photo", file_doc.file_url)

    # Asked for once, honoured once. Left set, every punch would go on
    # replacing the picture and the tick would mean nothing.
    if cint(existing.retake_photo):
        frappe.db.set_value("Machine User", machine_user, "retake_photo", 0)

    sync_employee_photo(
        existing.employee, file_doc.file_url, replace=True
    )

    if source in ENROLL_PHOTO_SOURCES or source in ("FACE", "fdata"):
        frappe.db.set_value("Machine User", machine_user, "face_registered", 1)

    frappe.logger().info(
        f"[TimeBridge ADMS] {machine}: saved photo for user {user_id} -> {file_doc.file_url}"
    )

    return file_doc.file_url


def handle_photo(machine, args, raw_bytes, body_text, source):
    """
    Store one incoming picture. Always returns without raising.

    A failure here must never break the upload: the device would retry the
    whole batch, and punches matter more than portraits.
    """

    try:

        if is_punch_snapshot(source, args):

            frappe.logger().info(
                f"[TimeBridge ADMS] {machine}: punch snapshot "
                f"({source}) — not stored as the profile photo"
            )
            return

        # A Bio-Photo POST is many PIN + Content rows. The single-blob decoder
        # would swallow the whole body as one picture and fail.
        field_rows = parser.parse_photo_fields(body_text)

        if field_rows:

            saved = save_photos_from_fields(
                machine, field_rows, source if source in ENROLL_PHOTO_SOURCES else "BIOPHOTO"
            )

            if saved:
                frappe.db.commit()
                return

        user_id = extract_user_id(args, body_text)
        image = decode_image(raw_bytes, body_text)

        # "Take photo and save" also photographs the people the device failed
        # to recognise, and those arrive with no id or a zero. That is the
        # setting working as chosen, not a fault, so it is noted quietly
        # instead of filling the error log with one entry per stranger.
        if image and user_id in (None, "", "0"):

            frappe.logger().info(
                f"[TimeBridge ADMS] {machine}: photo with no user id "
                f"({source}) — unrecognised person, not stored"
            )
            return

        if not user_id or not image:

            frappe.log_error(
                title="TimeBridge ADMS: unrecognised photo payload",
                message=(
                    f"machine={machine} source={source}\n"
                    f"user_id={user_id!r} image_found={bool(image)}\n"
                    f"args={dict(args)}\n"
                    f"first bytes: {(raw_bytes or b'')[:80]!r}\n"
                    f"body starts: {(body_text or '')[:MAX_LOGGED_BYTES]}"
                ),
            )
            return

        save_photo(machine, user_id, image, source)
        frappe.db.commit()

    except Exception:
        frappe.db.rollback()
        frappe.log_error(
            title="TimeBridge ADMS: photo save failed",
            message=frappe.get_traceback(),
        )
