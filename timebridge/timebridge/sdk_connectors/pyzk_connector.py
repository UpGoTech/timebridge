import time

import frappe

from frappe.utils import cint

# Used when TimeBridge Settings has never been saved and so reports
# nothing, mirroring the defaults declared in its schema.
DEFAULT_CONNECTION_TIMEOUT = 30
DEFAULT_RETRY_COUNT = 3

# Waited between attempts, multiplied by the attempt number.
RETRY_BACKOFF_SECONDS = 2

# The same mappings adms/parser.py applies to pushed records, keyed on ints
# because pyzk hands these over already decoded. Both paths must agree, or the
# transport would change what a punch appears to mean.
#
# Codes outside the map stay Unknown rather than being guessed at. The AIFace
# units here report punch=255 ("not stated") on every record, so direction is
# left to attendance_sync, which reads it from the day's first and last punch.
PUNCH_DIRECTION_MAP = {0: "In", 1: "Out", 4: "In", 5: "Out"}

VERIFY_MODE_MAP = {0: "Password", 1: "Fingerprint", 2: "Card", 15: "Face"}


def _pyzk():
    """Import pyzk only when a PyZK device is actually used."""

    try:
        from zk import ZK
        from zk.exception import ZKErrorResponse
    except ImportError as exc:
        frappe.throw(
            "The pyzk library is not installed. Run "
            "<code>bench setup requirements --python</code> or "
            "<code>bench pip install pyzk</code> to connect PyZK pull devices.",
            title="PyZK Not Available",
            exc=exc,
        )

    return ZK, ZKErrorResponse


class PyZKConnector:

    def connect(self, device, on_attempt=None):
        """
        Open a session to the device, retrying transient network
        failures. retry_count is read as the TOTAL number of attempts,
        so the stock value of 3 means three tries, not four.

        on_attempt(attempt, attempts) is optional and called before each
        try, so a caller can show which retry is running. A stock failure
        takes ~96s here; without it the UI cannot tell a slow first
        attempt from a hung job.
        """

        timeout = cint(
            frappe.db.get_single_value(
                "TimeBridge Settings",
                "connection_timeout"
            )
        ) or DEFAULT_CONNECTION_TIMEOUT

        attempts = cint(
            frappe.db.get_single_value(
                "TimeBridge Settings",
                "retry_count"
            )
        ) or DEFAULT_RETRY_COUNT

        attempts = max(attempts, 1)

        ZK, ZKErrorResponse = _pyzk()

        last_error = None

        for attempt in range(1, attempts + 1):

            if on_attempt:
                on_attempt(attempt, attempts)

            # A fresh ZK per attempt: pyzk opens its socket inside
            # connect() and leaves session state behind on failure,
            # so reusing the object would carry that into the retry.
            zk = ZK(
                device.ip_address,
                port=device.port,
                timeout=timeout,
                password=device.communication_password or 0,
                force_udp=bool(cint(getattr(device, "force_udp", 0))),
            )

            try:

                conn = zk.connect()

                conn.disable_device()

                return conn


            except ZKErrorResponse as e:

                # The device answered and rejected us. A bad comm key
                # will be rejected identically every time, so retrying
                # only burns the timeout.
                self.discard(zk)

                if "unauth" in str(e).lower():
                    raise

                last_error = e


            except Exception as e:

                self.discard(zk)

                last_error = e


            if attempt < attempts:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)


        raise last_error

    def discard(self, zk):
        """
        Best-effort teardown of a half-open attempt. pyzk's disconnect()
        talks to the device, so on a dead link it raises too — that is
        expected here and must not mask the original failure.
        """

        try:
            zk.disconnect()

        except Exception:
            pass

    def disconnect(self, conn):

        if conn:
            conn.enable_device()
            conn.disconnect()

    def get_device_info(self, conn):

        device_time = conn.get_time()

        info = {
            "serial_number": conn.get_serialnumber(),
            "firmware_version": conn.get_firmware_version(),
            "platform": conn.get_platform(),
            "device_name": conn.get_device_name(),
            "mac_address": conn.get_mac(),
            "device_time": (
                device_time.strftime("%Y-%m-%d %H:%M:%S")
                if device_time else None
            )
        }

        # read_sizes() fills the counters on the connection object itself.
        # Some firmwares refuse the command, so a failure here must not
        # throw away the identity fields read above. The counters keep
        # their ZK.__init__ defaults of 0 in that case.
        try:
            conn.read_sizes()

        except Exception:

            frappe.log_error(
                frappe.get_traceback(),
                "TimeBridge: read_sizes failed"
            )

        info.update({
            "user_count": conn.users,
            "record_count": conn.records,
            "finger_count": conn.fingers,
            "face_count": conn.faces,
            "user_capacity": conn.users_cap,
            "record_capacity": conn.rec_cap
        })

        return info

    def get_users(self, conn):
        """
        Everyone enrolled on the device, shaped for logger.save_users.

        A device will happily hold a user with no name, but user_name is
        mandatory on TimeBridge Machine User. Such a record is labelled by its id instead
        of being dropped: without the mapping every punch that person ever
        makes would stay unattached to an employee.
        """

        users = []

        for user in conn.get_users():

            # user_id is the number keyed at the terminal and the only thing
            # punches carry. uid is the device's internal row number and is
            # not interchangeable, so it is a last resort rather than a
            # fallback of equal standing.
            user_id = str(user.user_id or "").strip() or str(user.uid or "").strip()

            if not user_id:
                continue

            user_name = (user.name or "").strip()
            card = getattr(user, "card", None)

            users.append({
                "user_id": user_id,
                "user_name": user_name or f"User {user_id}",
                "card_number": str(card) if card else None,

                # pyzk reports 0 for an ordinary user and 14 for an
                # administrator; the DocType only distinguishes the two.
                "privilege": "Admin" if cint(user.privilege) else "User",
            })

        return users

    def get_attendance(self, conn):
        """
        Every punch the device is still holding, shaped for logger.save_punches.

        The whole log is returned, not a date range — the protocol offers no
        server-side filter. Trimming to a window is the caller's job, and
        punch_key makes re-reading the same records harmless.
        """

        records = []

        for punch in conn.get_attendance():

            user_id = str(punch.user_id or "").strip()

            if not user_id or not punch.timestamp:
                continue

            status = punch.status
            state = punch.punch

            records.append({
                "device_user_id": user_id,
                "timestamp": punch.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "punch_direction": PUNCH_DIRECTION_MAP.get(cint(state), "Unknown"),
                "verify_mode": (
                    VERIFY_MODE_MAP.get(cint(status), "Other")
                    if status is not None else None
                ),

                # Kept verbatim so an unmapped code can still be identified
                # later from stored rows, without re-reading the device.
                "device_status": f"status={status} punch={state}",
                "raw": f"{user_id}\t{punch.timestamp}\t{status}\t{state}",
            })

        return records

    def get_user_photos(self, conn, users=None):
        """
        Enrolled JPEGs, if this connection can produce them.

        pyzk 0.9 has no photo command. A newer library on the same object
        sometimes grows `get_userpic`; that is used when present. Anything
        that is not a JPEG is dropped — a face *template* is biometric data,
        not a picture, and must not be stored as one.

        Returns [] rather than raising when the device cannot help, so a
        pull of users and punches is not lost to a missing photograph.
        """

        from timebridge.timebridge.adms.photos import looks_like_image

        getter = getattr(conn, "get_userpic", None) or getattr(conn, "get_user_pic", None)

        if not getter:
            return []

        photos = []

        for user in users or []:

            user_id = str(user.get("user_id") or "").strip()

            if not user_id:
                continue

            try:
                image = getter(user_id)
            except TypeError:
                try:
                    image = getter()
                except Exception:
                    continue
            except Exception:
                continue

            if looks_like_image(image):
                photos.append({"user_id": user_id, "image_bytes": image})

        return photos

    def set_user(self, conn, user_id, name="", privilege=0, password="", card=0, uid=None):
        kwargs = {
            "name": name or "",
            "privilege": cint(privilege),
            "password": password or "",
            "user_id": str(user_id),
            "card": cint(card) if card else 0,
        }
        if uid is not None:
            kwargs["uid"] = cint(uid)
        conn.set_user(**kwargs)

    def delete_user(self, conn, user_id, uid=None):
        if uid is not None:
            conn.delete_user(uid=cint(uid), user_id=str(user_id))
        else:
            conn.delete_user(user_id=str(user_id))
