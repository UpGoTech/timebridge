# TimeBridge

Frappe app that connects biometric attendance devices (ZKTeco, eSSL, and similar) to Frappe. It is **device I/O**: machines, enrolled PINs, punch logs, and JPEG harvest when the firmware allows. Attendance as HR lives elsewhere.

See [spec/003-device-io.md](spec/003-device-io.md) for the current product cut.

## What it does

- Add machines through a wizard (operator picks **pull** or **push**)
- Ingest enrolled users as **Machine Users** (one row per machine + PIN)
- Ingest punch logs; optional JPEG harvest from facial firmware
- Create / edit / delete PINs on selected devices from Desk
- Diagnostic **Device Roll**: did this PIN punch in the selected period?

## Supported transports

| Transport | How it works | Typical devices |
|-----------|--------------|-----------------|
| **PyZK pull** | Frappe dials the device (default port **4370**) via [`pyzk`](https://github.com/fananimi/pyzk) | ZKTeco / Fabrixcel and other dialable ZK units |
| **ADMS push** | Device POSTs to `/iclock/…`; the app never opens a connection to the terminal | eSSL AIFace Mars and other HTTP push firmwares |

`sdk_type` on **Biometric Machine** selects the driver (`PyZK`, `ADMS`, …). Brand is metadata only.

Push devices that reject ZK pull (e.g. some AIFace units) must use ADMS — pull will not work against them.

## Data model

```
TimeBridge Machine  →  Machine User (PIN + name + optional photo)
                    →  Punch Log (PIN + timestamp)
                    →  Device Command (durable ADMS outbound queue)
TimeBridge Settings     (connection / photo harvest / ADMS Server)
TimeBridge ADMS Log      (every /iclock GET/POST while the server is On)
```

Same PIN on two machines is two Machine Users unless the operator copies it.

## Main workflows

1. **Add Machine** — Pull: probe 4370, save, fetch. Push: enable ADMS Server, wait for `/iclock` serial (Pending machine), Register.
2. **Test Connection / Fetch All Data** — pull readout or ADMS re-query.
3. **Create user** — PIN + name on one or more machines; biometrics enrol at the terminal.
4. **Device Roll** — Yes/No punched in a date range per PIN.

## Architecture (high level)

```
timebridge/
  api.py                 # whitelisted Desk APIs
  doctype/               # machines, users, punches, commands, …
  sdk_connectors/        # PyZKConnector, ADMSConnector
  services/              # device info, pull sync, user write, shared persist
  iclock/                # ADMS push receiver (renderer, handshake, handlers)
  page/add_machine/      # wizard
```

ADMS is registered via a `page_renderer` hook so firmware-hardcoded paths like `/iclock/cdata` can return raw `text/plain` responses. While the server is On, handlers always return HTTP 200 and ACK ATTLOG with `OK: n` so the device does not drop its batch.

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
