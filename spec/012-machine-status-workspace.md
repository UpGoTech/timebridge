# Spec 012 — Machine Status on workspace homepage

| Field | Value |
|-------|-------|
| **Spec ID** | `012` |
| **Branch** | `feat/machine-status-workspace` |
| **Status** | **In progress** |
| **Authority** | Builds on [005-workspace-dashboard.md](005-workspace-dashboard.md); ADMS contact in [009-adms-onboarding.md](009-adms-onboarding.md) |
| **Created** | 2026-09-06 |
| **Programme tracker** | [spec/README.md](./README.md) |

---

## 1. Why?

Operators opening the TimeBridge workspace see punch-health widgets (active users, today's punches, unmapped) but not whether each biometric terminal is online, when it last spoke, or what that contact was (heartbeat vs attendance upload). That forces opening each Machine form or digging ADMS Log.

Spec 005 deliberately dropped Connected/Registered machine number cards in favour of punch health. Number cards still cannot show one row per machine with sync type. The gap is a **live machine board on the homepage**.

---

## 2. What?

1. **Persist last contact kind** on TimeBridge Machine (`last_contact_kind`), written with `last_contact_at` whenever the device contacts us (or we successfully pull).
2. **Richer ADMS kinds** — stop recording generic `upload`; use Attendance / Users / Photos / Options from the table.
3. **Board API** — `get_machine_status_board` returns every machine with live Connected/Disconnected (push: 5-minute silence), last contact time, and contact kind label.
4. **Custom HTML Block** — `TimeBridge Machine Status` embedded full-width on the TimeBridge workspace **after** the three punch number cards and **before** Devices/Data/Reports/Logs. Table: Machine · Status · Last sync · Sync type. Auto-refresh while visible.
5. **PyZK** — successful device-info / pull also stamps contact with Device Info / Pull Sync so dialable machines appear on the board.

### Sync type labels (last device contact)

| Source | Label |
|--------|-------|
| `/iclock/getrequest` poll | Heartbeat |
| Handshake (`cdata` GET) | Handshake |
| ATTLOG | Attendance |
| OPERLOG / USERINFO / querydata user | Users |
| Photo tables / fdata | Photos |
| OPTIONS | Options |
| `/iclock/ping` | Ping |
| `/iclock/devicecmd` | Commands |
| PyZK device info | Device Info |
| PyZK pull sync | Pull Sync |

---

## 3. Locked decisions

| # | Decision |
|---|----------|
| D1 | Embed on workspace via **Custom HTML Block** — not a separate Desk Page. |
| D2 | Sync type = **last device contact**, not TimeBridge Sync Log rows. |
| D3 | Do not restore the Connected Machines number card; the table replaces it. |
| D4 | Board uses `last_contact_at` (not the unused `last_sync` watermark field). |
| D5 | Store **display labels** in `last_contact_kind` so the board needs no second map. |
| D6 | Push status on the board is computed live from contact age (same 5-minute rule as `push_device_status`), not only the cron-refreshed `status` field. |
| D7 | Custom HTML Block is upserted by helper + patch/`after_install` (Desk DocType has no app `is_standard` module export). |

---

## 4. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[ ]` |
| 2 | `last_contact_kind` + `record_contact` + ADMS/PyZK writers | `[ ]` |
| 3 | `get_machine_status_board` + unit tests | `[ ]` |
| 4 | Custom HTML Block + sync helper + install/uninstall | `[ ]` |
| 5 | Workspace JSON + post_model_sync patch | `[ ]` |
| 6 | Migrate + automated tests green | `[ ]` |

---

## 5. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. Open **TimeBridge** workspace — Machine Status table sits under the three punch cards.
2. Registered ADMS machine that is polling shows **Connected**, recent Last sync, Sync type **Heartbeat** (or Attendance after a punch upload).
3. Quiet machine (>5 min) shows **Disconnected**.
4. Click a machine name → opens TimeBridge Machine form.
5. After a successful PyZK Test Connection / Fetch, that machine appears with Device Info or Pull Sync.

---

## 6. Out of scope

- Restoring Connected Machines / Registered Machines number cards.
- Separate Desk Page for machine status.
- Extending Sync Log types to Heartbeat/Handshake.
- Writing or relying on `last_sync` for this board.
