# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS server addressing — port and host hints for device configuration.

Devices must dial the same TCP port Frappe's web process listens on. That
varies by bench (8000 locally, 80 in Docker, custom in production) so nothing
here assumes a fixed number.
"""

import frappe
from frappe.utils import cint


def web_port():
    """
    Port push devices should use in Cloud Server / ADMS settings.

    Resolution order:
    1. bench site config (http_port / webserver_port)
    2. Host header on the current request (Desk is open → we know the port)
    3. 443 for https, 80 for http
    """

    port = cint(frappe.conf.http_port or frappe.conf.webserver_port)

    if port:
        return port

    request = getattr(frappe.local, "request", None)

    if not request:
        return None

    host = request.host or ""

    if ":" in host:
        try:
            return int(host.rsplit(":", 1)[-1])
        except ValueError:
            pass

    if getattr(request, "scheme", "http") == "https":
        return 443

    return 80
