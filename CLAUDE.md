# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

TimeBridge is a Frappe custom app that connects biometric attendance devices (ZKTeco, eSSL, Matrix, etc.) to Frappe ERP. It pulls punch logs from physical devices over TCP/IP and syncs them as attendance records.

## Common Commands

All commands run from the bench root (`~/myapp`), not from within this app directory.

```bash
# Start bench (dev server on port 8000)
bench start

# Run tests for this app
bench --site <site-name> run-tests --app timebridge

# Run a single test
bench --site <site-name> run-tests --module timebridge.timebridge.doctype.biometric_machine.test_biometric_machine

# Apply migrations after changing DocType JSON
bench --site <site-name> migrate

# Clear cache after Python/JS changes
bench --site <site-name> clear-cache

# Export a DocType schema to JSON (after editing via UI)
bench --site <site-name> export-doc "Biometric Machine"
```

## Architecture

### Module layout

The app has a nested structure due to Frappe conventions:

```
timebridge/           ← Python package (app root)
  api.py             ← Top-level whitelisted API (currently a stub)
  hooks.py           ← Frappe hooks: scheduler events, doc_events, etc.
  timebridge/        ← Module folder (matches modules.txt: "TimeBridge")
    api.py           ← Active whitelisted API (test_connection used by frontend)
    doctype/         ← All DocTypes live here
    sdk_connectors/  ← One class per device SDK
    services/        ← Business logic called by scheduler / API
    adms/            ← ADMS protocol support (stub — not yet implemented)
```

### DocType data model

```
Organization → Branch → Department
                      → Shift
                      → Employee → Machine User (links to Biometric Machine)
Biometric Machine  ←──────────────┘
TimeBridge Settings  (single DocType — global config)
```

### SDK connector pattern

`services/connection.py::get_connector(device)` inspects `device.sdk_type` and returns the appropriate connector. Currently only `PyZKConnector` (using the `zk` Python library) is implemented. `matrix_connector.py`, `essl_connector.py`, and `custom_connector.py` are empty stubs.

Each connector must implement: `connect(device)` / `disconnect(conn)`. `PyZKConnector.connect()` calls `conn.disable_device()` on connect and `conn.enable_device()` on disconnect — this is required by the ZK protocol to safely read data.

### Key API call flow

The "Test Connection" button on the Biometric Machine form calls:
`timebridge.timebridge.api.test_connection` (not the top-level `timebridge.api`)

The front-end JS (`biometric_machine.js`) calls `timebridge.api.test_connection`, which resolves to `timebridge/api.py` — currently a working socket ping that updates the `status` field directly via `frappe.db.set_value`.

### TimeBridge Settings (Single DocType)

Global defaults for all machines: `default_port` (4370), `connection_timeout` (30s), `retry_count` (3), `sync_interval` (5 min), `duplicate_punch_window` (30s), `log_retention_days` (90).

## DocType Naming Conventions

- Biometric Machine: `BM-#####`
- Machine User: `MU-#####`
- Employee: `EMP-#####`
- Organization: `ORG-#####`
- Shift: `SH-#####`

## What's Not Yet Implemented

- `adms/` subpackage (parser, logger, commands, api) — all empty stubs
- `services/attendance_sync.py`, `scheduler.py`, `user_sync.py`, `device_info.py` — empty stubs
- `essl_connector.py`, `matrix_connector.py`, `custom_connector.py` — empty stubs
- Scheduler hooks in `hooks.py` are commented out — no background sync runs yet
