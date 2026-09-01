# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Claim /iclock/* only while the ADMS server is enabled."""

from email.utils import formatdate

import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer

from timebridge.timebridge.iclock import audit, discovery, handlers
from timebridge.timebridge.iclock.server import adms_server_enabled

ADMS_PREFIX = "iclock"

HANDLERS = {
	"cdata": handlers.handle_cdata,
	"getrequest": handlers.handle_getrequest,
	"devicecmd": handlers.handle_devicecmd,
	"ping": handlers.handle_ping,
	"querydata": handlers.handle_querydata,
	"fdata": handlers.handle_fdata,
}


class IclockRenderer(BaseRenderer):

	def can_render(self):
		parts = self.path.split("/")
		if not (
			len(parts) >= 2
			and parts[0].lower() == ADMS_PREFIX
			and self._endpoint(parts) in HANDLERS
		):
			return False
		return adms_server_enabled()

	def render(self):
		parts = self.path.split("/")
		endpoint = self._endpoint(parts)
		handler = HANDLERS[endpoint]
		request = frappe.local.request
		args = {k: v for k, v in (request.args or {}).items()}
		serial = args.get("SN") or args.get("sn")
		body = ""
		raw = b""

		if request.method == "POST":
			try:
				raw = request.get_data() or b""
				body = raw.decode("utf-8", errors="replace")
			except Exception:
				frappe.log_error(
					title="TimeBridge iclock: could not read request body",
					message=frappe.get_traceback(),
				)

		try:
			text = handler(serial, args, body, request.method, raw=raw)
		except Exception:
			frappe.log_error(
				title=f"TimeBridge iclock: handler {endpoint} crashed",
				message=frappe.get_traceback(),
			)
			text = "Error: internal failure"

		try:
			from timebridge.timebridge.iclock import peers

			peers.record_contact(serial, endpoint, request.method, args)
			row = discovery.machine_row(serial)
			audit.write_log(
				serial=serial,
				endpoint=endpoint,
				method=request.method,
				args=args,
				body=body or None,
				response=text,
				machine=row.name if row else None,
				remote=discovery.remote_ip(),
			)
		except Exception:
			frappe.logger().error("TimeBridge: iclock log write failed", exc_info=True)

		try:
			frappe.db.commit()
		except Exception:
			pass

		headers = {
			"Content-Type": "text/plain; charset=utf-8",
			"Date": formatdate(usegmt=True),
		}
		return self.build_response(text, http_status_code=200, headers=headers)

	@staticmethod
	def _endpoint(parts):
		return parts[1].split(".")[0].lower()
