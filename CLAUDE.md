# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

TimeBridge is a Frappe custom app that connects biometric attendance devices (ZKTeco, eSSL, Matrix, etc.) to Frappe ERP. It pulls punch logs from physical devices over TCP/IP and syncs them as attendance records.

### Target devices

Two paths, in priority order:

1. **ZKTeco / Fabrixcel — TCP pull via `pyzk`.** The primary path and the only one implemented. Frappe reaches out to the device on port 4370.
2. **eSSL AIFace Mars — ADMS push.** The device posts to us instead. Needed eventually, not yet; this is what the empty `adms/` subpackage is for.

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
  api.py             ← Empty. Reserved for app-level endpoints; nothing lives here
  hooks.py           ← Frappe hooks: scheduler events, doc_events, etc.
  timebridge/        ← Module folder (matches modules.txt: "TimeBridge")
    api.py           ← The real whitelisted API. All endpoints live here
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

`sdk_type` on Biometric Machine is a Select: `PyZK` / `ADMS` / `Matrix` / `Custom`, defaulting to `PyZK`. The string must match exactly — `get_connector` compares against the literal `"PyZK"`. It is deliberately separate from `device_brand`: brand is catalog metadata, `sdk_type` picks the driver. A Fabrixcel unit is brand `Other` but `sdk_type` `PyZK`.

`communication_password` (the ZK comm key) is deliberately an **Int**, not a `Password` fieldtype. Frappe stores `Password` fields in `__Auth` and plain attribute access returns a masked placeholder, which would be handed to `ZK()` as the key. Int also matches pyzk, which does `int(key)` in `make_commkey`. Do not "upgrade" it to `Password`.

Note the import path for connectors is `timebridge.timebridge.sdk_connectors.…` — doubled. `timebridge.sdk_connectors` does not exist.

Each connector must implement: `connect(device)` / `disconnect(conn)` / `get_device_info(conn)`. `PyZKConnector.connect()` calls `conn.disable_device()` on connect and `conn.enable_device()` on disconnect — this is required by the ZK protocol to safely read data.

**`disable_device()` takes a live terminal offline.** Never open a connection casually against production hardware, and never let two jobs connect to the same device concurrently — see the deduplication note below.

`PyZKConnector.connect()` retries transient failures: `retry_count` **total** attempts (3 = three tries, not four) with `2s × attempt` backoff, both read from TimeBridge Settings. Auth failures (`ZKErrorResponse` containing "unauth") fail fast, since a bad comm key is rejected identically every time. Each attempt builds a fresh `ZK` object, because pyzk opens its socket inside `connect()` and leaves session state behind on failure.

### Key API call flow

The "Test Connection" button on the Biometric Machine form calls
`timebridge.timebridge.api.get_device_info` — the **full dotted path**. The top-level `timebridge.api` namespace is empty; a shorter path will not resolve.

That endpoint is asynchronous. It only queues work and returns `{"status": "queued", "job_id": ...}`:

```
api.get_device_info          (whitelisted, returns immediately)
  → enqueue_device_info      (frappe.enqueue, deduplicated per machine)
    → run_device_info_job    (background worker)
      → fetch_device_info    (synchronous — call this directly from scheduler/console)
```

The result reaches the browser on the realtime event `timebridge_device_info`, published `after_commit=True` so the client's `frm.reload_doc()` cannot race the job's writes. The event name is a shared constant: `DEVICE_INFO_EVENT` in `services/device_info.py` and in `biometric_machine.js` — change both together.

Jobs are deduplicated on `timebridge_device_info::<machine_id>`, so a double-clicked button cannot open two sessions to one device. `frappe.enqueue` returns `None` when it suppresses a duplicate.

**Background workers must be running** (`bench start`, not a bare `bench serve`) or the job queues silently and the event never fires.

`fetch_device_info` also mirrors what the device reports back onto the record: `serial_number`, `device_model` (from the device name, falling back to platform), and `status`.

`timebridge.timebridge.api.test_connection` still exists — a plain socket ping that sets `status`. Nothing calls it since the button was rewired.

### TimeBridge Settings (Single DocType)

Global defaults for all machines: `default_port` (4370), `connection_timeout` (30s), `retry_count` (3), `sync_interval` (5 min), `duplicate_punch_window` (30s), `log_retention_days` (90).

**Gotcha: this Single has never been saved.** There is no row for it in `tabSingles` on `mysite.localhost`, so every one of those fields reads back as `0`/`None` — *not* the values above. Those are **form** defaults from the JSON: they populate the field when someone opens the doc in the UI, and only reach the database on save.

So any code reading these must supply its own fallback, e.g. `cint(get_single_value(...)) or DEFAULT_CONNECTION_TIMEOUT`. `pyzk_connector.py` and `services/device_info.py` both do this. Saving the doc once in the UI fixes it at the data level, but keep the code fallbacks for fresh installs.

## DocType Naming Conventions

- Biometric Machine: `BM-#####`
- Machine User: `MU-#####`
- Employee: `EMP-#####`
- Organization: `ORG-#####`
- Shift: `SH-#####`

## What's Not Yet Implemented

- `adms/` subpackage (parser, logger, commands, api) — all empty stubs. This is the eSSL AIFace Mars push path
- `services/attendance_sync.py`, `scheduler.py`, `user_sync.py` — empty stubs
- `essl_connector.py`, `matrix_connector.py`, `custom_connector.py` — empty stubs
- `PyZKConnector.get_users` / `get_attendance` — still commented out
- Scheduler hooks in `hooks.py` are commented out — no background sync runs yet

`services/device_info.py` **is** implemented (device metadata read + writeback).

### Verification status

The device-info path has never run against real hardware. `192.168.88.44` (BM-104988, "fabrixcel") is unreachable from WSL2 — it refuses every TCP port including 4370 and 80, and ICMP is intermittent. Everything below the socket is verified; `connect()` succeeding and `get_device_info()` parsing a real response are not.
