# Spec 004 — Machine diagnostic log

| Field | Value |
|-------|-------|
| **Spec ID** | `004` |
| **Branch** | `feat/004-machine-log` |
| **Status** | **Implemented** |
| **Authority** | This doc; complements [003-device-io.md](003-device-io.md) |
| **Created** | 2026-08-31 |
| **Programme tracker** | [spec/README.md](README.md) |

---

## 1. Why?

[TimeBridge Sync Log](003-device-io.md) records ingest runs (Users / Attendance / Device Info) with counts. Connect failures, ADMS protocol events, unknown serials, photo faults, and command results were scattered in global **Error Log** or server logs — not filterable by machine.

Operators need a per-machine diagnostic ledger for everything **except successful sync**.

---

## 2. What?

- New DocType **TimeBridge Machine Log** (append-only, code-inserted).
- Helper `write_machine_log()` in `services/machine_log.py`.
- Errors and Warnings always stored; routine ADMS handshake/heartbeat/ping Info only when **Enable Debug Log** is on in Settings.
- Daily purge using existing **Log Retention (Days)** setting.
- Workspace link + Machine form connections (Logs group with Sync Log).

Sync Log remains the honest measure of ingest success. Sync **failures** are also written to Machine Log.

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | TimeBridge Machine Log DocType | `[x]` |
| 3 | `write_machine_log` + retention job | `[x]` |
| 4 | Instrument ADMS, pull, probe, photos, user write | `[x]` |
| 5 | Unit tests | `[x]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. Workspace → **TimeBridge Machine Log** appears under Data.
2. Open a Machine → Connections → Machine Log + Sync Log.
3. Fail a pull (wrong IP) → Error row on Machine Log.
4. POST `/iclock/cdata` with unknown SN and ATTLOG body → Warning on Machine Log (not Pending for upload rejection).

---

## 5. Locked decisions

| # | Decision |
|---|----------|
| Q1 | Machine Log = diagnostics; Sync Log = ingest runs |
| Q2 | Unknown-serial heartbeats stay on Pending Device Signal only |
| Q3 | `enable_debug_log` gates routine ADMS Info noise |
| Q4 | `log_retention_days` applies to Machine Log purge |
