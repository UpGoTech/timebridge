# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This App Does

TimeBridge is a Frappe custom app that connects biometric attendance devices (ZKTeco, eSSL, Matrix, etc.) to Frappe ERP. It pulls punch logs from physical devices over TCP/IP and syncs them as attendance records.

### Target devices

Two transports, both implemented:

1. **ZKTeco / Fabrixcel — TCP pull via `pyzk`.** Frappe reaches out to the device on port 4370. Only device *info* is built on this path; user and attendance sync are not.
2. **eSSL AIFace Mars — ADMS push.** The device dials out and POSTs to us; we never connect to it. Implemented in `adms/` — see *ADMS push receiver* below.

**The AIFace MARS at 192.168.2.195 (`BM-104987`) cannot be pulled.** A raw ZK `CMD_CONNECT` gets reply code `6001`, which is not in pyzk's ACK set, and all eight `force_udp` × `ommit_ping` × password(`123456`/`0`) combinations fail identically — so it is not an auth or transport tuning problem. Push is the only way to get data out of it. Do not spend time re-testing pull against it.

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
    adms/            ← ADMS push receiver — parser, logger, api, renderer
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

### ADMS push receiver

The push path. The device drives everything: it dials out on its own timer and POSTs tab-delimited plain text. TimeBridge never opens a connection to it, so none of the pyzk machinery above applies.

**Routing goes through a `page_renderer` hook, not `website_route_rules`.** The firmware has `/iclock/cdata` hardcoded — it will never call `/api/method/…`, so a whitelisted method alone is unreachable. `website_route_rules` maps a path onto another *route* for template rendering; it can give back neither the raw POST body nor a bare `text/plain` response. `frappe/app.py` routes any non-`/api` GET, HEAD **or POST** through the website layer, and `page_renderer` lets an app claim arbitrary paths there. Registered in `hooks.py` as `timebridge.timebridge.adms.renderer.ADMSRenderer`.

Four endpoints are answered, all in `adms/api.py`:

| Path | Purpose |
|---|---|
| `GET /iclock/cdata?SN=…&options=all` | handshake — replies with `Delay`, `Realtime=1`, `Encrypt=0`, etc. |
| `POST /iclock/cdata?SN=…&table=ATTLOG` | punches |
| `POST /iclock/cdata?SN=…&table=OPERLOG` (or `USERINFO`) | enrolled users |
| `/iclock/getrequest`, `/iclock/devicecmd`, `/iclock/ping` | acknowledged only |

An unlisted `/iclock/*` path falls through to a normal 404 rather than being silently acknowledged.

**Every handler returns `OK`, even after a failure.** A 500 makes the firmware discard the batch it is holding, and losing punches is worse than losing one upload. Failures go to Error Log plus a `Failed` TimeBridge Sync Log row instead. Do not "fix" this by returning real HTTP error codes.

**Devices are matched on `SN` against `Biometric Machine.serial_number`, never on IP** (`logger.get_machine_by_serial`). A push whose serial matches nothing stores no records and writes an Error Log entry titled *"TimeBridge ADMS: unknown device serial"* containing the serial and the raw body — which doubles as the way to discover a new device's serial without reading it off the hardware.

`adms/parser.py` is pure functions, no DB and no request state — that is where the real tests live. Note `parse_attlog` deliberately uses `line.rstrip("\r")` and not `line.strip()`: stripping eats a leading tab, shifting every field left, so a record with an empty user id would have its timestamp read as the user id. A test caught this.

`adms/logger.py` writes into the same `TimeBridge Punch Log` / `Machine User` tables the pull path will use, so push and pull differ only in transport. Idempotency comes from `build_punch_key()` and the unique `punch_key` column — re-sending a batch cannot duplicate rows, which matters because firmwares re-send freely. `link_unmatched_punches()` exists because devices routinely upload punches *before* the users they belong to; backfilling is the normal path, not a repair job.

`adms/commands.py` is still empty, so `getrequest` always answers "nothing pending" — the receiver is receive-only, with no way to push commands back to a device.

**Network topology is where the time actually goes.** Frappe runs inside WSL2; the device is on the Windows LAN and cannot reach it directly. A `netsh interface portproxy` rule on Windows forwards `192.168.2.173:8000` (the Windows LAN IP) to the WSL2 IP, plus an inbound firewall rule for 8000. **WSL2's IP changes on every reboot**, silently breaking the proxy — several dead rules pointing at old IPs are already on that machine. Before suspecting app code when nothing arrives, compare:

```bash
ip -4 addr show eth0                                    # inside WSL
powershell.exe -NoProfile -Command "netsh interface portproxy show v4tov4"
```

Requests arrive with a raw-IP `Host:` header, which resolves because `common_site_config.json` sets `serve_default_site: true` and `default_site: mysite.localhost`. Changing either would break every push.

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

- `adms/commands.py` — empty. No commands are ever queued back to a device
- `services/attendance_sync.py`, `scheduler.py`, `user_sync.py` — empty stubs
- `essl_connector.py`, `matrix_connector.py`, `custom_connector.py` — empty stubs
- `PyZKConnector.get_users` / `get_attendance` — still commented out
- Scheduler hooks in `hooks.py` are commented out — no background sync runs yet

`services/device_info.py` **is** implemented (device metadata read + writeback), as is the whole `adms/` push path.

### Verification status

**Pull path — unverified against hardware.** The device-info path has never run against a real device. `192.168.88.44` (BM-104988, "fabrixcel") is unreachable from WSL2 — it refuses every TCP port including 4370 and 80, and ICMP is intermittent. Everything below the socket is verified; `connect()` succeeding and `get_device_info()` parsing a real response are not.

**Push path — verified end to end over HTTP, not yet by a real device.** `adms/test_parser.py` covers the parsing (11 cases). Beyond that, a full run over real HTTP against `/iclock/cdata` — same URL and payload format a device uses — created Machine Users, created linked Punch Logs with the right direction and verify mode, wrote `Success` Sync Logs, rejected a re-sent batch without duplicating, and rejected an unregistered serial without storing anything. What is still untested is a physical device's own firmware: its exact payload dialect, its timing, and how it behaves when a reply is slow.

`BM-104987` is still recorded as `device_brand: ZKTeco` / `sdk_type: PyZK`, which is untrue — it is an eSSL device on ADMS. Correcting `sdk_type` to `ADMS` would make `get_connector()` raise `Unsupported SDK Type : ADMS` and disable the pull buttons, which is the honest outcome but a behaviour change. Left as-is deliberately.
