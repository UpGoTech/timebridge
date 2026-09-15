"""Undo site-wide Link options rewrites left by rename_conflicting_doctypes.

That patch already ran on upgraded sites, so editing it is not enough. This
repair puts Saral HR / other-app Link options back (e.g. TimeBridge Branch ->
Branch) while leaving TimeBridge-owned DocTypes alone.
"""

import frappe

from timebridge.patches.v1_0.rename_conflicting_doctypes import (
	RENAMES,
	_foreign_option_rows,
	_restore_option_rows,
)


def execute():
	for old, new in RENAMES:
		_repair_foreign_rewrites(old, new)
	frappe.clear_cache()


def _repair_foreign_rewrites(old, new):
	# Foreign fields still pointing at the TimeBridge-prefixed name.
	rows = _foreign_option_rows(new)
	for row in rows:
		row["value"] = old
	_restore_option_rows(rows)
