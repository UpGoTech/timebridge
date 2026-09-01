# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
Connector for devices that push to us instead of answering us (ADMS).

There is deliberately no socket code here. An ADMS device accepts no incoming
connection at all — it dials out to /iclock/... on its own timer and posts its
records. So "connecting" to one is not a slow operation, it is an impossible
one, and this class says so plainly rather than opening a socket that is
certain to fail.

What it does instead is report the only thing that actually indicates health
for a push device: when it last spoke to us, and how much it has sent.
"""

import frappe

from frappe.utils import cint, now_datetime, time_diff_in_seconds

# The handshake tells the device Delay=30, so it should check in every 30s.
# Beyond this it is genuinely quiet rather than simply between polls.
SILENCE_MINUTES = 5


class ADMSConnector:
	"""
	Push devices cannot be dialled. Every pull-shaped method refuses clearly
	instead of failing obscurely somewhere deep in a socket timeout.
	"""

	# Lets callers explain the situation rather than retry a doomed connection.
	is_push = True

	def connect(self, device, on_attempt=None):

		frappe.throw(
			f"{device.machine_name or device.name} is a push device (SDK Type: ADMS). "
			"It cannot be connected to — it sends its data to us on its own. "
			"Use Fetch All Data to ask it for history, or simply wait: new punches "
			"arrive by themselves."
		)

	def disconnect(self, conn):
		pass

	def get_device_info(self, conn):

		frappe.throw("Device info cannot be read from a push device.")

	def health(self, device):
		"""
		The push equivalent of a connection test: has it spoken to us lately?

		Returns the same shape the pull path returns, so the form can report on
		a push device without a special case at every call site.
		"""

		from timebridge.timebridge.iclock import commands

		contact = commands.last_contact(device.name) or {}

		punches = frappe.db.count("TimeBridge Punch Log", {"machine": device.name})

		if not contact.get("at"):

			return {
				"status": "failed",
				"is_push": True,
				"machine_status": "Disconnected",
				"message": (
					"This device has never contacted us. Check that its Cloud Server "
					"address points at this PC, with Enable Domain Name and Enable "
					"Proxy Server both off."
				),
				"punches": punches,
			}

		minutes = int(time_diff_in_seconds(now_datetime(), contact["at"]) / 60)

		if minutes > SILENCE_MINUTES:

			return {
				"status": "failed",
				"is_push": True,
				"machine_status": "Disconnected",
				"message": (
					f"Last heard from this device {minutes} minutes ago. It normally "
					f"checks in every 30 seconds — the network forwarding has most "
					f"likely broken since the PC restarted."
				),
				"last_contact": contact["at"],
				"punches": punches,
			}

		return {
			"status": "success",
			"is_push": True,
			"machine_status": "Connected",
			"message": (
				f"Device is sending normally — last heard {minutes} minute(s) ago. "
				f"{punches} punches stored."
			),
			"last_contact": contact["at"],
			"punches": punches,
		}


def push_device_status(machine_name):
	"""
	The status a push device should currently show, from its own activity.

	Kept out of the connector so the scheduler can refresh every push device
	without constructing one per machine.
	"""

	from timebridge.timebridge.iclock import commands

	contact = commands.last_contact(machine_name) or {}

	if not contact.get("at"):
		return "Disconnected"

	minutes = time_diff_in_seconds(now_datetime(), contact["at"]) / 60

	return "Connected" if cint(minutes) <= SILENCE_MINUTES else "Disconnected"
