# from zk import ZK


# class PyZKConnector:

#     def connect(self, device):
#         pass

#     def disconnect(self, conn):
#         pass

#     def get_device_info(self, conn):
#         pass

#     def get_users(self, conn):
#         pass

#     def get_attendance(self, conn):
#         pass


import time

import frappe

from frappe.utils import cint
from zk import ZK
from zk.exception import ZKErrorResponse

# Used when TimeBridge Settings has never been saved and so reports
# nothing, mirroring the defaults declared in its schema.
DEFAULT_CONNECTION_TIMEOUT = 30
DEFAULT_RETRY_COUNT = 3

# Waited between attempts, multiplied by the attempt number.
RETRY_BACKOFF_SECONDS = 2


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
                password=device.communication_password or 0
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