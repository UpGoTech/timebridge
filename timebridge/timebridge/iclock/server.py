# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
ADMS / iclock server addressing, enable switch, and log category toggles.

TimeBridge Settings is often unsaved — missing values use code fallbacks.
"""

import frappe
from frappe.utils import cint

CACHE_KEY = "timebridge_adms_server_enabled"
LOG_CACHE_KEY = "timebridge_adms_log_settings"

CATEGORY_FIELDS = {
	"Handshake": "log_adms_handshake",
	"Heartbeat": "log_adms_heartbeat",
	"Ping": "log_adms_ping",
	"Attendance": "log_adms_attendance",
	"Users": "log_adms_users",
	"Photos": "log_adms_photos",
	"Commands": "log_adms_commands",
	"Options": "log_adms_options",
	"Upload": "log_adms_upload",
	"Other": "log_adms_other",
}

LOG_DEFAULTS = {
	"Handshake": 1,
	"Heartbeat": 0,
	"Ping": 0,
	"Attendance": 1,
	"Users": 1,
	"Photos": 1,
	"Commands": 1,
	"Options": 1,
	"Upload": 1,
	"Other": 1,
}


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
	frappe.cache().delete_value(LOG_CACHE_KEY)


def _load_log_settings():
	cached = frappe.cache().get_value(LOG_CACHE_KEY)
	if cached is not None:
		return cached

	settings = {}
	for category, fieldname in CATEGORY_FIELDS.items():
		val = frappe.db.get_single_value("TimeBridge Settings", fieldname)
		if val is None:
			settings[category] = LOG_DEFAULTS.get(category, 1)
		else:
			settings[category] = cint(val)
	frappe.cache().set_value(LOG_CACHE_KEY, settings, expires_in_sec=60)
	return settings


def log_category_enabled(category):
	settings = _load_log_settings()
	if category not in settings:
		return LOG_DEFAULTS.get(category, 1)
	return cint(settings[category]) == 1


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
