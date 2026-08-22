# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Parsing for the ADMS / "iclock" push protocol.

Devices POST tab-delimited plain text, one record per line. Nothing here
touches the database or Frappe request state — it turns text into dicts so the
awkward part of this protocol can be unit tested without a device present.

ATTLOG line layout (fields beyond the 4th vary by firmware and are ignored):

    <user_id>\t<timestamp>\t<status>\t<verify_mode>\t<workcode>...

USERINFO lines are `key=value` pairs rather than positional:

    PIN=1\tName=Asha\tPri=0\tCard=123\tPasswd=\tGrp=1
"""

# Punch direction by device status code, reusing the mapping already proven in
# biometric_attendance/biometric_puller.py::get_punch_type — 0/4 are entry
# readers, 1/5 are exit readers. Unknown codes stay "Unknown" rather than being
# guessed at; this device's real codes are not yet confirmed against hardware.
PUNCH_DIRECTION_MAP = {
    "0": "In",
    "1": "Out",
    "4": "In",
    "5": "Out",
}

# Verify-mode codes. Anything unlisted becomes "Other" rather than being
# dropped, because an unrecognised reader type is still a real punch.
VERIFY_MODE_MAP = {
    "0": "Password",
    "1": "Fingerprint",
    "2": "Card",
    "15": "Face",
}


def parse_attlog(body):
    """
    Parse an ATTLOG payload into punch dicts.

    Returns (records, skipped), where skipped holds raw lines that could not be
    understood. A malformed line never aborts the batch — one bad row must not
    cost us the rest of a device's upload.
    """

    records = []
    skipped = []

    for line in (body or "").splitlines():

        # Deliberately not line.strip() before splitting: stripping would eat a
        # leading tab, shifting every field left by one, so a record with an
        # empty user id would have its timestamp read as the user id. Only
        # trailing carriage returns are safe to drop here.
        line = line.rstrip("\r")

        if not line.strip():
            continue

        parts = line.split("\t")

        # user id and timestamp are the minimum needed to store a punch
        if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
            skipped.append(line)
            continue

        status = parts[2].strip() if len(parts) > 2 else ""
        verify = parts[3].strip() if len(parts) > 3 else ""

        records.append({
            "device_user_id": parts[0].strip(),
            "timestamp": parts[1].strip(),
            "punch_direction": PUNCH_DIRECTION_MAP.get(status, "Unknown"),
            "verify_mode": VERIFY_MODE_MAP.get(verify, "Other" if verify else None),
            "device_status": status or None,
            "raw": line,
        })

    return records, skipped


def parse_userinfo(body):
    """
    Parse a USERINFO payload into user dicts.

    Lines carry `key=value` pairs, so field order cannot be relied on. A line
    without a PIN is unusable — that is the device's user id.
    """

    records = []
    skipped = []

    for line in (body or "").splitlines():

        line = line.strip()

        if not line:
            continue

        # Some firmwares prefix the record type on each line.
        if line.upper().startswith("USER "):
            line = line[5:]

        fields = {}

        for chunk in line.split("\t"):

            if "=" not in chunk:
                continue

            key, _, value = chunk.partition("=")
            fields[key.strip().upper()] = value.strip()

        user_id = fields.get("PIN")

        if not user_id:
            skipped.append(line)
            continue

        # A Bio-Photo row also has PIN, but Content is the picture, not a
        # person. Treated as a user it would rename everyone to "User 3".
        if fields.get("CONTENT") or fields.get("PHOTO"):
            continue

        privilege = fields.get("PRI") or "0"

        records.append({
            "user_id": user_id,
            "user_name": fields.get("NAME") or f"User {user_id}",
            "card_number": fields.get("CARD") or None,
            "privilege": "User" if privilege in ("0", "") else "Admin",
            "raw": line,
        })

    return records, skipped


def parse_table_name(table):
    """
    Normalise the `table` query parameter. Firmwares differ in case and some
    append options, e.g. "ATTLOG Stamp=9999".
    """

    if not table:
        return None

    parts = table.strip().split()

    return parts[0].upper() if parts else None


def parse_photo_fields(body):
    """
    PIN + base64 Content rows — how enrolment pictures travel in USERPIC /
    BIOPHOTO (and sometimes mixed into OPERLOG).

    One POST is a whole department, not one face. The JPEG decoder must not
    swallow the rest of the body as a single blob.
    """

    records = []

    for line in (body or "").splitlines():

        line = line.rstrip("\r")

        if not line.strip() or "=" not in line:
            continue

        fields = {}

        for chunk in line.split("\t"):

            if "=" not in chunk:
                continue

            key, _, value = chunk.partition("=")
            fields[key.strip().upper()] = value.strip()

        user_id = fields.get("PIN")
        content = fields.get("CONTENT") or fields.get("PHOTO")

        if not user_id or not content or len(content) < 64:
            continue

        records.append({
            "user_id": user_id,
            "content": content,
            "type": fields.get("TYPE"),
        })

    return records
