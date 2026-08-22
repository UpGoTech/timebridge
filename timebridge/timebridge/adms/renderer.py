# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Makes the fixed /iclock/... paths reachable.

The device's firmware has these paths hardcoded — it will never call
/api/method/..., so a whitelisted method alone is not enough. Frappe routes any
non-/api GET, HEAD or POST through the website layer (see frappe/app.py, the
`request.method in ("GET", "HEAD", "POST")` branch), and the `page_renderer`
hook lets an app claim arbitrary paths there.

This is preferred over website_route_rules because those map a path onto another
*route* for template rendering, whereas the device needs a bare text/plain body
and we need the raw POST payload.
"""

import frappe

from frappe.website.page_renderers.base_renderer import BaseRenderer

from timebridge.timebridge.adms import api

ADMS_PREFIX = "iclock"

# Only these are answered. An unlisted /iclock/* path falls through to Frappe's
# normal 404 rather than being silently acknowledged.
HANDLERS = {
    "cdata": api.handle_cdata,
    "getrequest": api.handle_getrequest,
    "devicecmd": api.handle_devicecmd,
    "ping": api.handle_ping,
    # Photographs arrive here on most firmwares, as raw JPEG bytes rather than
    # the tab-delimited text everything else uses.
    "fdata": api.handle_fdata,
}


class ADMSRenderer(BaseRenderer):

    def can_render(self):

        parts = self.path.split("/")

        return (
            len(parts) >= 2
            and parts[0].lower() == ADMS_PREFIX
            and self._endpoint(parts) in HANDLERS
        )

    def render(self):

        parts = self.path.split("/")
        endpoint = self._endpoint(parts)
        handler = HANDLERS[endpoint]

        request = frappe.local.request

        args = {k: v for k, v in (request.args or {}).items()}
        serial = args.get("SN") or args.get("sn")

        # The payload is tab-delimited text, so it must be read raw. Frappe's
        # form-dict parsing would make nothing of it.
        body = ""
        raw = b""

        if request.method == "POST":
            try:
                raw = request.get_data() or b""
                body = raw.decode("utf-8", errors="replace")
            except Exception:
                frappe.log_error(
                    title="TimeBridge ADMS: could not read request body",
                    message=frappe.get_traceback(),
                )

        try:
            text = handler(serial, args, body, request.method, raw=raw)

        except Exception:
            frappe.log_error(
                title=f"TimeBridge ADMS: handler {endpoint} crashed",
                message=frappe.get_traceback(),
            )
            # Still answer OK: a 500 makes the firmware drop the batch it was
            # holding, and losing punches is worse than losing this upload.
            text = "OK"

        return self.build_response(
            text,
            http_status_code=200,
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )

    @staticmethod
    def _endpoint(parts):

        return parts[1].split(".")[0].lower()
