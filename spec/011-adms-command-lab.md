# Spec 011 — ADMS Command Lab

| Field | Value |
|-------|-------|
| **Spec ID** | `011` |
| **Branch** | `feat/adms-command-lab` |
| **Status** | **In progress** |
| **Authority** | Builds on [009-adms-onboarding.md](009-adms-onboarding.md), [010-adms-server-console.md](010-adms-server-console.md) |
| **Created** | 2026-09-02 |
| **Programme tracker** | [spec/README.md](./README.md) |

---

## 1. Why?

Production user download on ADMS devices (`BM-83649`) fails with protocol dialect mismatches: bare `DATA QUERY USERINFO` yields `BIODATA` face templates; Security PUSH bulk query `tablename=user,fielddesc=*,filter=*` returns `Return=-1004`. Each hypothesis today needs a code change, deploy, and log spelunking.

Operators need one **Desk page** to pick a registered machine, type or pick a command, queue it, and watch every related `/iclock` request and response in real time — without redeploying for each experiment.

## 2. What?

1. **Desk page `adms-debug`** (“ADMS Command Lab”) — System Manager only.
2. **APIs** — `queue_raw_command` (arbitrary payload after `C:id:`) and `poll_debug_feed` (ADMS Log + Device Command timeline).
3. **Presets** — static chips for the seven dialects under investigation.
4. **Navigation** — TimeBridge workspace Logs card link; optional shortcut from TimeBridge Machine form.

## 3. Locked decisions

| # | Decision |
|---|----------|
| D1 | Registered ADMS machines only — same guard as `queue_device_command`. |
| D2 | Operator types payload only; server wraps via `commands.queue_command`. |
| D3 | No download session — debug queue does not call `start_download_session`. |
| D4 | Feed from existing `TimeBridge ADMS Log` + `TimeBridge Device Command` tables. |
| D5 | System Manager only — page role + API check. |
| D6 | Presets are static chips, not persisted per site. |
| D7 | Follow desk-page-ui — no full-bleed, breadcrumbs, 32px controls, Link wrap. |
| D8 | **Scrap mode** — Command Lab requires explicit **Start session** / **Stop session**. While active, device traffic is acked but not written to ADMS Log or any ingest DocType; feed reads from session cache only. Stop clears pending lab commands and queues `REBOOT` so the device returns to normal. |

## 4. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | `queue_raw_command` + `poll_debug_feed` APIs | `[x]` |
| 3 | Desk page UI + live poll | `[x]` |
| 4 | Workspace link + migrate patch | `[x]` |
| 5 | Machine form shortcut | `[x]` |
| 6 | Unit tests | `[x]` |

## 5. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost run-tests --module timebridge.timebridge.iclock.test_iclock
```

Manual:

1. Open **ADMS Command Lab** from TimeBridge workspace → Logs.
2. Pick a registered ADMS machine (e.g. one that is polling).
3. Click **INFO** preset → **Send** → feed shows command status and ADMS Log rows within ~30s (device poll interval).
4. Try **DATA QUERY USERINFO PIN=1** and observe `cdata` / `devicecmd` / `querydata` endpoint and body shape.
5. Confirm Machine Users count updates only when a winning dialect ingests users (not automatic in v1).

## 6. Out of scope (v1)

- Queuing on unknown peers / pre-registration.
- Auto-ingesting BIODATA as users.
- Editing TransFlag / handshake from this page.
- Persisting custom preset library.
