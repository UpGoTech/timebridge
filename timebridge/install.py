# Copyright (c) 2026, UPGO and contributors
# For license information, please see license.txt

"""
App install hooks.

PyZK pull devices need the `pyzk` package (`import zk`). It is declared in
pyproject.toml and normally arrives via `bench setup requirements` or
`pip install -e apps/timebridge`, but those steps are easy to skip when an
app is copied in manually. before_install closes that gap.
"""

import importlib.util
import subprocess
import sys

PYZK_SPEC = "pyzk>=0.9"


def before_install():
	ensure_pyzk()


def after_install():
	"""Desk workspaces must match module JSON on every fresh install-app."""

	from timebridge.timebridge.services.workspace_sync import sync_app_workspaces

	sync_app_workspaces(force=True)


def ensure_pyzk():
	"""Install pyzk into the bench virtualenv when it is missing."""

	if importlib.util.find_spec("zk") is not None:
		return

	subprocess.check_call(
		[sys.executable, "-m", "pip", "install", PYZK_SPEC],
	)
