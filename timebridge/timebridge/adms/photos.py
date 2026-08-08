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

# Tables that carry pictures rather than punches, across the firmwares that
# name them differently.
PHOTO_TABLES = {"ATTPHOTO", "USERPIC", "USERPHOTO", "FACE", "BIOPHOTO"}

# JPEG and PNG magic numbers — used to tell an actual image from base64 text
# or from a stray error string.
IMAGE_SIGNATURES = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")

MAX_LOGGED_BYTES = 1500


def looks_like_image(data):

    return isinstance(data, bytes) and data.startswith(IMAGE_SIGNATURES)


def extract_user_id(args, body_text):
    """
    The user id can be in the query string or the body, depending on firmware.

    Returns None when it cannot be found — a picture we cannot attribute to a
    person is useless, and inventing an owner would be worse than dropping it.
    """

    for key in ("PIN", "pin", "UserID", "userid", "USERID"):
        if args.get(key):
            return str(args[key]).strip()

    match = re.search(r"\bPIN=([^\s\t&]+)", body_text or "")

    return match.group(1).strip() if match else None


def decode_image(raw_bytes, body_text):
    """
    Get image bytes out of whatever arrived.

    Raw binary is used as-is. Otherwise the body is searched for a base64
    blob, which is how the cdata-style uploads carry the picture.
    """

    if looks_like_image(raw_bytes):
        return raw_bytes

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


def save_photo(machine, user_id, image_bytes, source):
    """
    Attach the picture to the Machine User and show it on the record.

    Returns the file url, or None when the user is not one we know — an
    unknown id means the device and our records disagree, which is worth
    seeing rather than papering over.
    """

    machine_user = frappe.db.get_value(
        "Machine User", {"machine": machine, "user_id": user_id}, "name"
    )

    if not machine_user:
        frappe.log_error(
            title="TimeBridge ADMS: photo for unknown user",
            message=f"Machine {machine} sent a photo for user id {user_id!r}, "
                    f"which has no Machine User record.",
        )
        return None

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

    # The device only sends a face image for someone actually enrolled with a
    # face, so this is evidence rather than an assumption.
    if source in ("USERPIC", "FACE", "fdata"):
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

        user_id = extract_user_id(args, body_text)
        image = decode_image(raw_bytes, body_text)

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
