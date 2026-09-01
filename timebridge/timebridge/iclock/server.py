# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS / iclock server addressing and the global enable switch.

TimeBridge Settings is often unsaved, so missing/0 must mean Off.
"""

import frappe
from frappe.utils import cint

CACHE_KEY = "timebridge_adms_server_enabled"


def adms_server_enabled():
	cached = frappe.cache().get_value(CACHE_KEY)
	if cached is not None:
		return cint(cached) == 1

	enabled = cint(
		frappe.db.get_single_value("TimeBridge Settings", "adms_server_enabled")
	)
	frappe.cache().set_value(CACHE_KEY, enabled, expires_in_sec=60)
	return enabled == 1


def clear_server_enabled_cache():
	frappe.cache().delete_value(CACHE_KEY)


def web_port():
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
