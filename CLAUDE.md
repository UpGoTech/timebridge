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
bench --site <site-name> run-tests --module timebridge.timebridge.doctype.timebridge_machine.test_timebridge_machine

# Apply migrations after changing DocType JSON
bench --site <site-name> migrate

# Clear cache after Python/JS changes
bench --site <site-name> clear-cache

# Export a DocType schema to JSON (after editing via UI)
bench --site <site-name> export-doc "TimeBridge Machine"
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
TimeBridge Organization → TimeBridge Branch → TimeBridge Department
                      → TimeBridge Shift
                      → TimeBridge Employee → TimeBridge Machine User (links to TimeBridge Machine)
TimeBridge Machine  ←──────────────┘
TimeBridge Settings  (single DocType — global config)
```

### SDK connector pattern

`services/connection.py::get_connector(device)` inspects `device.sdk_type` and returns the appropriate connector: `PyZKConnector` (using the `zk` Python library) for devices we dial, `ADMSConnector` (in `essl_connector.py`) for devices that dial us. `matrix_connector.py` and `custom_connector.py` are empty stubs, and `get_connector` names them as unbuilt rather than throwing "Unsupported SDK Type". `is_push_device(device)` is the test every caller uses before assuming a device can be connected to.

`sdk_type` on TimeBridge Machine is a Select: `PyZK` / `ADMS` / `Matrix` / `Custom`, defaulting to `PyZK`. The string must match exactly — `get_connector` compares against the literal `"PyZK"`. It is deliberately separate from `device_brand`: brand is catalog metadata, `sdk_type` picks the driver. A Fabrixcel unit is brand `Other` but `sdk_type` `PyZK`.

`communication_password` (the ZK comm key) is deliberately an **Int**, not a `Password` fieldtype. Frappe stores `Password` fields in `__Auth` and plain attribute access returns a masked placeholder, which would be handed to `ZK()` as the key. Int also matches pyzk, which does `int(key)` in `make_commkey`. Do not "upgrade" it to `Password`.

Note the import path for connectors is `timebridge.timebridge.sdk_connectors.…` — doubled. `timebridge.sdk_connectors` does not exist.

Each connector must implement: `connect(device)` / `disconnect(conn)` / `get_device_info(conn)`. A connector for a device that can be dialled also implements `get_users(conn)` and `get_attendance(conn)`, which return dicts already shaped for `adms/logger.py`'s `save_users` / `save_punches` — that is what lets push and pull share one set of tables. `PyZKConnector.connect()` calls `conn.disable_device()` on connect and `conn.enable_device()` on disconnect — this is required by the ZK protocol to safely read data.

**`disable_device()` takes a live terminal offline.** Never open a connection casually against production hardware, and never let two jobs connect to the same device concurrently — see the deduplication note below.

`PyZKConnector.connect()` retries transient failures: `retry_count` **total** attempts (3 = three tries, not four) with `2s × attempt` backoff, both read from TimeBridge Settings. Auth failures (`ZKErrorResponse` containing "unauth") fail fast, since a bad comm key is rejected identically every time. Each attempt builds a fresh `ZK` object, because pyzk opens its socket inside `connect()` and leaves session state behind on failure.

### Key API call flow

The "Test Connection" button on the TimeBridge Machine form calls
`timebridge.timebridge.api.get_device_info` — the **full dotted path**. The top-level `timebridge.api` namespace is empty; a shorter path will not resolve.

That endpoint is asynchronous. It only queues work and returns `{"status": "queued", "job_id": ...}`:

```
api.get_device_info          (whitelisted, returns immediately)
  → enqueue_device_info      (frappe.enqueue, deduplicated per machine)
    → run_device_info_job    (background worker)
      → fetch_device_info    (synchronous — call this directly from scheduler/console)
```

The result reaches the browser on the realtime event `timebridge_device_info`, published `after_commit=True` so the client's `frm.reload_doc()` cannot race the job's writes. The event name is a shared constant: `DEVICE_INFO_EVENT` in `services/device_info.py` and in `timebridge_machine.js` — change both together.

Jobs are deduplicated on `timebridge_device_info::<machine_id>`, so a double-clicked button cannot open two sessions to one device. `frappe.enqueue` returns `None` when it suppresses a duplicate.

**Background workers must be running** (`bench start`, not a bare `bench serve`) or the job queues silently and the event never fires.

`fetch_device_info` also mirrors what the device reports back onto the record: `serial_number`, `device_model` (from the device name, falling back to platform), and `status`.

`timebridge.timebridge.api.test_connection` still exists — a plain socket ping that sets `status`. Nothing calls it since the button was rewired.

### Pull sync — "Fetch All Data"

One button, two entirely different mechanisms, chosen by transport in `api.request_all_data`:

```
api.request_all_data (whitelisted)
  ├─ dialable device → enqueue_pull_sync    → run_pull_sync_job → pull_all_data
  └─ push device     → adms.commands.queue_command (device collects it later)
```

`services/pull_sync.py` holds the pull half. Two things about it are deliberate and easy to undo by accident:

**The device is read out completely, released, and only then written to the database.** `connect()` disables the terminal, so nobody can punch while the session is open. Reading 46k records takes seconds; inserting them takes minutes. Storing while still connected would keep a live door offline for the whole insert.

**Punches are stored in committed batches of `INSERT_BATCH`**, so an interrupted run keeps what it wrote, and `drop_stored()` bulk-loads existing `punch_key`s first — a device hands over its entire log every time, so on the second run almost everything is already held and checking row by row would be tens of thousands of queries.

`days` trims how far back punches are kept (`0` = the device's whole log); the ZK protocol offers no server-side date filter, so the full log is always transferred regardless. Users are always taken in full.

Progress is polled from the cache via `api.pull_sync_progress`, on its own key, not shared with device-info — a connection test and a fetch can legitimately overlap.

### TimeBridge Employees and TimeBridge Machine Users

**A sync of either kind produces only TimeBridge Machine Users, and attendance is built per TimeBridge Employee.** `attendance_sync.rebuild_for_range` begins at `p.employee IS NOT NULL`, so until a TimeBridge Machine User points at a TimeBridge Employee its punches are stored and invisible — Rebuild Attendance reports success and does nothing, because it never saw them. This is the single most confusing state in the app and it looks exactly like a bug.

`services/employee_link.py` closes that gap, behind the **Create & Link TimeBridge Employees** button. `plan()` decides and writes nothing; it returns what would happen for a human to agree to, and `apply_plan()` recomputes the same plan server-side rather than trusting rows posted back from a browser. There is no automatic matching anywhere, deliberately: a name is the only evidence a device offers, and attaching the wrong one moves one person's attendance onto another silently.

Three rules in there exist because of what real device data turned out to look like on the Fabrixcel unit (172 enrolments):

**`employee_code` is unique across every machine, but each device numbers its people from 1 independently.** Six of that device's ids were already TimeBridge Employee codes belonging to *different* people from another terminal — its user `4` is not the user `4` already on file. So the bare device id is used as a code only while it is free, and collisions fall back to `<machine_id>-<user_id>` (`AIFACE002-4`). Do not "tidy" this into always-prefixed or always-bare: bare is what somebody reads off the terminal, and prefixing is what keeps it honest.

**One person can hold two enrolments.** `09` and `F09` are both Amol Bawane. Same-named users are therefore gathered onto one TimeBridge Employee by default, so their day is not split across two records. `merge_same_name=0` turns that off. Note the risk runs both ways — two genuinely different people with one name would be merged — which is why the preview flags every merged row instead of doing it quietly.

**`normalise()` does no fuzzy matching.** `SUVARNAJICHKAR` and `SUVARNA JICHKAR` stay different. A near-miss that silently resolves to somebody is worse than one the operator is asked about.

`date_of_joining`, `organization` and `branch` are mandatory on TimeBridge Employee and the device knows none of them, so they come from the dialog; `suggested_defaults()` offers the commonest existing values as a starting point. `apply_plan()` finishes by calling `logger.link_unmatched_punches()`, which is what makes the *stored history* visible rather than only punches from that moment on.

**Create & Link cannot correct the people it created**, because `plan()` only ever considers TimeBridge Machine Users with no TimeBridge Employee. Changing TimeBridge Organization or TimeBridge Shift in that dialog afterwards does nothing at all, which is why its "everything is already linked" message names the other button rather than just saying there is nothing to do.

That other button is **Update TimeBridge Organization / TimeBridge Shift** (`apply_assignment`). It is an update and only an update: no record is created, deleted or unlinked. The obvious-looking alternative — reset the links and run Create & Link again with different values — does not work and is dangerous. Re-linking matches the same TimeBridge Employees by name and never rewrites these fields, so nothing would change; and deleting the TimeBridge Employees to force a re-create would take every attendance row and every punch's `employee` with them.

Membership for that update comes from the TimeBridge Machine User links (`machine_employees()`), not `TimeBridge Employee.biometric_machine`, since the link is what attendance follows and `biometric_machine` names only one machine for somebody enrolled on two. Anyone shared with another machine is counted and shown before the change rather than moved quietly. `assignment_summary()` also exposes the current spread, which matters: on `BM-104987` the sixteen people hold three different shifts, and flattening those to one would be a silent loss.

A device photograph lands on TimeBridge Machine User first. `adms.photos.sync_employee_photo` already copies it onto TimeBridge Employee when the picture arrives *and* the person is already linked. `services/employee_photo.copy_linked_photos` is the other direction: after Create & Link, or after a pull, it copies whatever is already on the device record. It reuses that function rather than writing a second rule. pyzk 0.9 cannot read JPEGs, so a pull copies existing pictures but does not invent them from a face template.

### Reports

Three, all Script Reports on `TimeBridge Attendance`: **Attendance Report** (the register — one letter per day), **Punch Register** (the same shape with the actual In-Out times in each cell), and **TimeBridge Employee Attendance Detail** (one person, one month, downwards).

The first two share `attendance_report.get_employees()` — the only place a filter turns into a set of people, so a filter added there appears in both. Detail is not part of that: it takes a single employee and never asks the question.

**The Machine filter is the one that usually does the work.** A site typically puts every employee on the same TimeBridge Organization, TimeBridge Branch and TimeBridge Shift, so those three narrow nothing and the reports look like they cannot separate one terminal's staff from another's. Machine can: on this database it splits 185 employees into 169 and 16 exactly. It resolves through the **TimeBridge Machine User links**, not `TimeBridge Employee.biometric_machine` — same reasoning as `machine_employees()` above, and that field is also unset for anyone linked by hand.

**Punch Register builds its own Excel file** (`export_excel`, wired to the toolbar's Excel button by `download_excel` in its JS) rather than calling `report.export_report()`. Frappe's export writes the grid and nothing else — no title, no machine, no month, no legend, no frozen header — and `build_xlsx_data` divides every declared column width by ten, which is what left thirty-one time columns too narrow to hold `11:38-19:01` and spilling into each other. None of that is reachable from a column definition.

Two things in that file are load-bearing and easy to undo:

**The title rows are merged and centred across the sheet, and only the header row is frozen.** Freezing the name columns as well splits every merged title at column D, so the heading arrives cut in half. Do not put that freeze back without un-merging the titles.

**The heading only names a TimeBridge Organization it can be sure of** — the one filtered on, or the only one that exists. There are two on this site, so with no filter the line is left off entirely rather than printing whichever came back first. Note `attendance_report.day_wise_heading` still does take the first one, and can therefore print the wrong company on a printed register; it was left alone rather than changing another report's output as a side effect. Punch Register no longer shows TimeBridge Organization / TimeBridge Branch / TimeBridge Department in its filter bar — Machine is what actually splits the staff, and those three were empty noise. The register still has them.

The response is the file itself, which is why the client posts a form at the endpoint instead of using `frappe.call`.

### ADMS push receiver

The push path. The device drives everything: it dials out on its own timer and POSTs tab-delimited plain text. TimeBridge never opens a connection to it, so none of the pyzk machinery above applies.

**Routing goes through a `page_renderer` hook, not `website_route_rules`.** The firmware has `/iclock/cdata` hardcoded — it will never call `/api/method/…`, so a whitelisted method alone is unreachable. `website_route_rules` maps a path onto another *route* for template rendering; it can give back neither the raw POST body nor a bare `text/plain` response. `frappe/app.py` routes any non-`/api` GET, HEAD **or POST** through the website layer, and `page_renderer` lets an app claim arbitrary paths there. Registered in `hooks.py` as `timebridge.timebridge.adms.renderer.ADMSRenderer`.

Four endpoints are answered, all in `adms/api.py`:

| Path | Purpose |
|---|---|
| `GET /iclock/cdata?SN=…&options=all` | handshake — replies with `Delay`, `Realtime=1`, `Encrypt=0`, etc. |
| `POST /iclock/cdata?SN=…&table=ATTLOG` | punches |
| `POST /iclock/cdata?SN=…&table=OPERLOG` (or `USERINFO`) | enrolled users |
| `/iclock/getrequest`, `/iclock/devicecmd`, `/iclock/ping` | commands out / command result / probe |

An unlisted `/iclock/*` path falls through to a normal 404 rather than being silently acknowledged.

**The HTTP status is always 200, even after a failure.** A 500 makes the firmware discard the batch it is holding, and losing punches is worse than losing one upload. Failures go to Error Log plus a `Failed` TimeBridge Sync Log row instead. Do not "fix" this by returning real HTTP error codes.

**A data upload is answered `OK: <records processed>`, never a bare `OK`** (`api.ack`). This is the protocol's success entity; a bare `OK` reads as an error, so the firmware keeps the batch and re-sends it on every cycle. That is exactly what happened on `NCD8251400238`: 37,637 records arrived of which only 8,980 were new, 220 batches being the *same* 128-record chunk. The count includes duplicates — a punch already held was still processed successfully, and `OK: 0` restarts the loop. Retries are requested by replying an error *description* in a 200 body, which is what the ATTLOG/USERINFO failure paths now do.

Note the reference for all of this is the **Attendance PUSH** protocol, not `spec/ZKteco Push SDK.pdf` — that PDF is the *Security* PUSH protocol (access control, `table=rtlog`, `/iclock/registry`), where a bare `OK` genuinely is correct and where `TransFlag` has a different digit order. The device announces `pushver=2.4.1&DeviceType=att` and posts `table=ATTLOG`, so it speaks Attendance PUSH. Trusting the wrong document is what produced both the ack bug and the `TransFlag` bug below.

**`TransFlag` positions follow Attendance PUSH order:** `1 AttLog, 2 OpLog, 3 AttPhoto, 4 EnrollFP, 5 EnrollUser, 6 FPImage, 7 ChgUser, 8 ChgFP, 9 FACE, 10 UserPic`. The Security ordering puts EnrollUser at 4 and ChgUser at 5, and following it left `1111000000` requesting fingerprint enrolments while switching off the two flags that make the device report its people. Punches plus users is `1110101000`; with photos, `1110101011`.

**An OPERLOG carrying no `PIN=` rows is still acknowledged and still advances `OPERLOGStamp`.** Most OPERLOG uploads are `OPLOG <OpType>\t<OpWho>\t<OpTime>…` audit rows (`parser.parse_oplog`) which nothing here models. Leaving the stamp write inside `if records:` meant 465 of 468 OPERLOG posts left no trace at all and the device re-sent its whole operation log — 181 times inside one minute.

The handshake sends the spec's key names, `ATTLOGStamp` / `OPERLOGStamp` (plus `Stamp` as the documented ATTLOG alias). `OpStamp`, `AttLogStamp` and `OperLogStamp` were invented and the device ignored them. `TransTimes`, `TransInterval` and `TimeZone` are also required; `TimeZone` is minutes when the offset is not whole hours, so IST is `330`, not `5.5`, and it is derived from the site timezone because a wrong value shifts every punch the device reports afterwards.

**Devices are matched on `SN` against `TimeBridge Machine.serial_number`, never on IP** (`logger.get_machine_by_serial`). A push whose serial matches nothing stores no records and writes an Error Log entry titled *"TimeBridge ADMS: unknown device serial"* containing the serial and the raw body — which doubles as the way to discover a new device's serial without reading it off the hardware.

`adms/parser.py` is pure functions, no DB and no request state — that is where the real tests live. Note `parse_attlog` deliberately uses `line.rstrip("\r")` and not `line.strip()`: stripping eats a leading tab, shifting every field left, so a record with an empty user id would have its timestamp read as the user id. A test caught this.

`adms/logger.py` writes into the same `TimeBridge Punch Log` / `TimeBridge Machine User` tables the pull path will use, so push and pull differ only in transport. Idempotency comes from `build_punch_key()` and the unique `punch_key` column — re-sending a batch cannot duplicate rows, which matters because firmwares re-send freely. `link_unmatched_punches()` exists because devices routinely upload punches *before* the users they belong to; backfilling is the normal path, not a repair job.

`adms/commands.py` queues work for the next `/iclock/getrequest` poll. Attendance date-range resend is proven on this firmware; `CHECK` is not (the device collects it and sends nothing). **Fetch Photos** is the other live command path: it opens FACE/UserPic in the handshake, then tries three query dialects in sequence — tab-separated bulk `biophoto`/`userpic` (this firmware splits ATTLOG on tabs), comma form plus `DATA QUERY USERPIC`, then one `PIN=` query per enrolled user. Rounds advance only while the device is still talking and no new TimeBridge Machine User photo has appeared. Punch snapshots (`ATTPHOTO`, or `PIN=YYYYMMDDHHMMSS-<id>.jpg`) are acknowledged and dropped; they are not the enrolment Bio-Photo. OPERLOG/USERINFO harvests `PIN`+`Content` rows via `parse_photo_fields` so a mixed photo POST cannot rename people to `"User 3"`. If all three rounds return nothing, the remaining path is **Upload Photos** with files named `{user id}.jpg` — this firmware will not re-send Bio-Photo the way the other middleware's Import Bio-Photo tab reads it.

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

- TimeBridge Machine: `BM-#####`
- TimeBridge Machine User: `MU-#####`
- TimeBridge Employee: `EMP-#####`
- TimeBridge Organization: `ORG-#####`
- TimeBridge Shift: `SH-#####`

## What's Not Yet Implemented

- `services/scheduler.py`, `services/user_sync.py` — empty stubs. Nothing syncs on a timer; every fetch is a button press
- `matrix_connector.py`, `custom_connector.py` — empty stubs, and `get_connector` says so by name rather than throwing
- Scheduler hooks in `hooks.py` are commented out — no background sync runs yet
- TimeBridge Employee linking is assisted, not automatic, and that is a decision rather than an omission — see *TimeBridge Employees and TimeBridge Machine Users*. Nothing attaches a device user to a TimeBridge Employee without someone confirming it

`services/device_info.py`, `services/pull_sync.py`, `services/employee_link.py`, `services/attendance_sync.py`, `sdk_connectors/essl_connector.py` (`ADMSConnector`) and the whole `adms/` push path **are** implemented.

### Verification status

**Pull path — verified against hardware.** `BM-106762` ("Fabrixcel", `192.168.88.18`, firmware Ver 6.60, platform `ZAM180_TFT`) answers on 4370 and was read end to end: 172 users and 46,436 punches transferred, users upserted, punches stored with `source: PyZK Pull`, a re-run created 0 rows and counted 115 duplicates, and the queued job path completed in about four seconds for a three-day window.

That run also settled a question the code had been hedging on: this firmware **does** report usable punch state codes (`punch=0` / `1`), so direction comes back as real In/Out — 169 In, 99 Out, 2 Unknown on the first three days — rather than the Unknown the mapping comment feared. `verify_mode` reads `Face` (`status=15`) throughout. Codes seen on menu-access records (`punch=255`) still map to Unknown, correctly.

The employee-link path is verified the same way: a full `apply_plan()` run inside a transaction that was then rolled back created 169 TimeBridge Employees, attached 171 TimeBridge Machine Users, backfilled 3,199 punches and reported no failures, leaving the database as it started. Six codes were qualified to `AIFACE002-*` and two pairs of enrolments were folded onto one person each, exactly as the preview said.

Two cautions from that same run. A device on `192.168.88.x` is reachable from WSL2 through the Windows host even though the PC sits on `192.168.2.x` — do not assume a different subnet means unreachable; probe TCP 4370 before concluding anything. And `communication_password` matters: this unit rejected `0` with `Unauthenticated` and accepted `12345`. That failure surfaces in the UI with the port-scan panel's *"no port is open"* wording, which is wrong for an auth failure — the port was open the whole time.

`192.168.88.44` (BM-104988) remains unreachable from WSL2 — it refuses every TCP port including 4370 and 80, and ICMP is intermittent.

**Push path — verified end to end over HTTP, not yet by a real device.** `adms/test_parser.py` covers the parsing (13 cases). Beyond that, a full run over real HTTP against `/iclock/cdata` — same URL and payload format a device uses — created TimeBridge Machine Users, created linked Punch Logs with the right direction and verify mode, wrote `Success` Sync Logs, rejected a re-sent batch without duplicating, and rejected an unregistered serial without storing anything. What is still untested is a physical device's own firmware: its exact payload dialect, its timing, and how it behaves when a reply is slow. Fetch Photos has been verified to queue commands and keep the device polling; the AIFace MARS has not yet re-sent enrolment Bio-Photo over ADMS.

`BM-104987` is still recorded as `device_brand: ZKTeco` / `sdk_type: PyZK`, which is untrue — it is an eSSL device on ADMS. Correcting `sdk_type` to `ADMS` would make `get_connector()` raise `Unsupported SDK Type : ADMS` and disable the pull buttons, which is the honest outcome but a behaviour change. Left as-is deliberately.
