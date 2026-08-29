# TimeBridge

Frappe app that connects biometric attendance devices (ZKTeco, eSSL, and similar) to Frappe ERP. It syncs punch logs from physical terminals into attendance records.

## What it does

- Register biometric machines and pull or receive punch data
- Upsert enrolled users as **Machine Users**, then link them to **Employees**
- Rebuild daily attendance from linked punches
- Report attendance (register, punch times, per-employee detail)

## Supported transports

| Transport | How it works | Typical devices |
|-----------|--------------|-----------------|
| **PyZK pull** | Frappe dials the device (default port **4370**) via [`pyzk`](https://github.com/fananimi/pyzk) | ZKTeco / Fabrixcel and other dialable ZK units |
| **ADMS push** | Device POSTs to `/iclock/…`; the app never opens a connection to the terminal | eSSL AIFace Mars and other HTTP push firmwares |

`sdk_type` on **Biometric Machine** selects the driver (`PyZK`, `ADMS`, …). Brand is metadata only.

Push devices that reject ZK pull (e.g. some AIFace units) must use ADMS — pull will not work against them.

## Data model

```
Organization → Branch → Department
                      → Shift
                      → Employee → Machine User → Biometric Machine
TimeBridge Settings (Single — global defaults)
```

Punches land in **TimeBridge Punch Log**. Attendance is built only for punches whose Machine User is linked to an Employee.

## Main workflows

1. **Test Connection / Device Info** — queues a background job; result arrives on a realtime event (workers must be running: `bench start`).
2. **Fetch All Data** — pull devices: full user + punch readout, then batch insert. Push devices: queues an ADMS command for the next device poll.
3. **Create & Link Employees** — preview then confirm; no silent auto-match (names alone are too ambiguous).
4. **Rebuild Attendance** — builds day records from linked punches for a date range.
5. **Reports** — Attendance Report, Punch Register, Employee Attendance Detail, Employee Working Hours.

## Architecture (high level)

```
timebridge/
  api.py                 # whitelisted Desk APIs
  doctype/               # machines, users, employees, punches, …
  sdk_connectors/        # PyZKConnector, ADMSConnector, …
  services/              # device info, pull sync, employee link, attendance
  adms/                  # ADMS push receiver (parser, logger, commands, renderer)
```

ADMS is registered via a `page_renderer` hook so firmware-hardcoded paths like `/iclock/cdata` can return raw `text/plain` responses. Handlers acknowledge with `OK` even on soft failures so the device does not drop its batch.

## Install

From your bench root:

```bash
bench get-app /path/to/timebridge   # or clone URL
bench setup requirements --python   # installs pyzk and other pyproject deps
bench --site <site> install-app timebridge
bench --site <site> migrate
```

`pyzk` (import name `zk`) is required for **PyZK pull** devices and is declared in
`pyproject.toml`. `bench setup requirements` installs it; `install-app` also runs a
`before_install` check so a missing package is pip-installed automatically.

Requires a running Frappe site. Background workers are required for queued device jobs (`bench start`).

## Development

```bash
# from bench root
bench start
bench --site <site> run-tests --app timebridge
bench --site <site> clear-cache
```

PRs go to `develop` on `feat/` or `fix/` branches. Deeper agent/dev notes live in `AGENTS.md` / `CLAUDE.md`.

## License

MIT
