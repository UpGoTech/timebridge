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

import re

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

_KV_SPACED = re.compile(r"(\w+)\s*=\s*([^=\t]+)")


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


# --- Device options (Push SDK §4.6) ---


def parse_options(body):
    """
    Parse device parameter push or GET OPTIONS response.

    Returns dict with normalised keys: users, punches, fingerprints, faces, …
    """

    result = {}

    for line in (body or "").splitlines():
        line = line.strip()

        if not line or "=" not in line:
            continue

        for chunk in line.replace("\t", "\n").split("\n"):
            if "=" not in chunk:
                continue

            key, _, value = chunk.partition("=")
            key = key.strip()
            value = value.strip()

            if not key:
                continue

            upper = key.upper()

            if upper in ("USERCOUNT", "USERS"):
                result["users"] = _int_or_none(value)
            elif upper in ("TRANSACTIONCOUNT", "ATTLOGCOUNT", "RECORDS"):
                result["punches_total"] = _int_or_none(value)
            elif upper in ("FPCOUNT", "FINGERCOUNT", "FINGERPRINTCOUNT"):
                result["fingerprints"] = _int_or_none(value)
            elif upper in ("FACECOUNT", "FACECOUNT10"):
                result["faces"] = _int_or_none(value)
            elif upper in ("BIOPHOTOCOUNT", "USERPICCOUNT"):
                result["photos"] = _int_or_none(value)
            elif upper in ("BIODATACOUNT",):
                result["biodata"] = _int_or_none(value)

    return result


def _int_or_none(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def parse_count_response(body):
    """Parse DATA COUNT response — tab-separated count=N or plain integer."""

    text = (body or "").strip()

    if not text:
        return None

    for chunk in text.replace("\t", "\n").split("\n"):
        chunk = chunk.strip()

        if "=" in chunk:
            _, _, value = chunk.partition("=")
            parsed = _int_or_none(value)
            if parsed is not None:
                return parsed

    return _int_or_none(text)


def parse_devicecmd_fields(body):
    """Parse key=value lines from a devicecmd acknowledgement."""

    fields = {}

    for line in (body or "").replace("&", "\n").splitlines():
        line = line.strip()

        if not line or "=" not in line:
            continue

        key, _, value = line.partition("=")
        fields[key.strip().upper()] = value.strip()

    return fields


def count_probe_kind_from_text(text):
    """Guess which DATA COUNT table a response belongs to."""

    upper = (text or "").upper()

    if "ATTLOG" in upper or "TRANSACTION" in upper or "RECORD" in upper:
        return "attlog"

    if "BIODATA" in upper or "FINGER" in upper or "TEMPLATE" in upper:
        return "biodata"

    if "BIOPHOTO" in upper or "USERPIC" in upper or "PHOTO" in upper:
        return "biophoto"

    return None


def parse_getrequest_info(info):
    """
    Parse the INFO query parameter from /iclock/getrequest.

    Format (Push SDK): firmware, users, fingerprints, records, device IP, …
    """

    import re

    text = (info or "").strip()

    if not text:
        return {}

    parts = [part.strip() for part in text.split(",")]
    ip_idx = None

    for index, part in enumerate(parts):
        if re.match(r"^\d+\.\d+\.\d+\.\d+$", part):
            ip_idx = index
            break

    if ip_idx is None or ip_idx < 3:
        return {}

    result = {}

    try:
        result["users"] = _int_or_none(parts[ip_idx - 3])
        result["fingerprints"] = _int_or_none(parts[ip_idx - 2])
        result["punches_total"] = _int_or_none(parts[ip_idx - 1])

        if ip_idx + 4 < len(parts):
            result["faces"] = _int_or_none(parts[ip_idx + 4])
    except (IndexError, TypeError):
        return {}

    return {key: value for key, value in result.items() if value is not None}


# --- Biometric templates (Push SDK §7.7 / §7.11) ---


def is_template_table(args, table):
    """Whether this upload carries biometric templates."""

    tablename = (args.get("tablename") or "").strip().lower()

    if table == "TABLEDATA" and tablename in ("biodata", "templatev10"):
        return True

    return (table or "").upper() in ("TEMPLATEV10", "BIODATA")


def template_upload_source(args, table):
    tablename = (args.get("tablename") or "").strip().lower()

    if table == "TABLEDATA" and tablename:
        return tablename.lower()

    if table:
        return table.lower()

    return "biodata"


def parse_templatev10(body):
    """Parse templatev10 lines: Pin=… FingerID=… Template=… Size=… Valid=…"""

    return _parse_template_body(body, default_bio_type="Fingerprint", source_table="templatev10")


def parse_biodata(body):
    """Parse unified biodata lines: pin=… type=… index=… tmp=… majorver=… minorver=…"""

    return _parse_template_body(body, source_table="biodata")


def _parse_template_body(body, default_bio_type=None, source_table=None):
    records = []
    skipped = []

    for line in (body or "").splitlines():
        line = line.rstrip("\r").strip()

        if not line or "=" not in line:
            continue

        fields = {}

        for chunk in line.split("\t") if "\t" in line else [line]:
            for match in _KV_SPACED.finditer(chunk):
                fields[match.group(1).upper()] = match.group(2).strip()

            if "=" in chunk and "\t" not in chunk:
                key, _, value = chunk.partition("=")
                fields[key.strip().upper()] = value.strip()

        user_id = fields.get("PIN") or fields.get("USERID") or fields.get("UID")

        template_data = (
            fields.get("TEMPLATE")
            or fields.get("TMP")
            or fields.get("CONTENT")
            or fields.get("DATA")
        )

        if not user_id or not template_data:
            skipped.append(line)
            continue

        bio_type = fields.get("TYPE") or default_bio_type or "Other"
        template_index = fields.get("FINGERID") or fields.get("INDEX") or fields.get("NO") or "0"

        records.append({
            "user_id": user_id,
            "bio_type": bio_type,
            "template_index": template_index,
            "template_data": template_data,
            "algorithm_major": fields.get("MAJORVER") or fields.get("MAJOR") or 10,
            "algorithm_minor": fields.get("MINORVER") or fields.get("MINOR") or 0,
            "template_format": fields.get("FORMAT"),
            "valid": 0 if fields.get("VALID") in ("0", "false", "False") else 1,
            "size": fields.get("SIZE"),
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
