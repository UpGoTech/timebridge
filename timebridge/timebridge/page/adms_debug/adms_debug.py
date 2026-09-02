# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""Desk page helpers for ADMS Command Lab."""

from timebridge.timebridge.iclock.debug_feed import (
	normalize_raw_command,
	queue_raw_command,
	return_label,
)

__all__ = ["normalize_raw_command", "queue_raw_command", "return_label"]
