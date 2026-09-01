# Spec 010 — ADMS Server Console

| Field | Value |
|-------|-------|
| **Spec ID** | `010` |
| **Branch** | `feat/009-adms-onboarding` |
| **Status** | **Ready for review** |
| **Authority** | Builds on [009-adms-onboarding.md](009-adms-onboarding.md); Attendance PUSH §12.7.1 (`REBOOT`) |
| **Created** | 2026-09-01 |
| **Programme tracker** | [spec/README.md](./README.md) |

---

## 1. Why?

Operators need one place to see every device talking to `/iclock`, control which request types fill **TimeBridge ADMS Log**, and recover devices after a server wipe — when firmware keeps heartbeating but never re-inits.

Spec 009 removed auto-created machines and per-machine log ticks. This spec adds a **Settings console** without bringing back auto Machine creation.

## 2. What?

1. **TimeBridge ADMS Peer** — upsert on every `/iclock` request by serial (observability only).
2. **TimeBridge Settings → ADMS Server** — live roster (10s poll + Refresh), per-category log toggles (Heartbeat/Ping off by default).
3. **Commands** — `REBOOT` via peer queue for Unknown/Pending; `REBOOT`/`INFO` via Device Command for Registered.
4. **Recovery** — after DB wipe, operator Reboots Unknown peer → next `getrequest` delivers `C:id:REBOOT` → device inits → Add push machine → Register.

## 3. Locked decisions

| # | Decision |
|---|----------|
| G1 | `TimeBridge ADMS Peer` DocType; does not create `TimeBridge Machine`. |
| G2 | Log defaults: all categories on except **Heartbeat** and **Ping**. |
| G3 | `INFO`/QUERY Registered-only; `REBOOT` also on Unknown/Pending peer queue. |
| G4 | Roster auto-refresh 10s + manual Refresh on Settings tab. |
| G5 | Registration still via Add Machine → Push + Machine form Register. |

## 4. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | `TimeBridge ADMS Peer` + `iclock/peers.py` | `[x]` |
| 3 | Settings log toggles + `audit.should_log` | `[x]` |
| 4 | Peer REBOOT queue + `handle_getrequest` | `[x]` |
| 5 | Settings console UI | `[x]` |
| 6 | Tests + migrate | `[x]` |

## 5. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost run-tests --module timebridge.timebridge.iclock.test_iclock
```

Manual:

1. Enable ADMS Server; Heartbeat/Ping log toggles off by default.
2. Device polls → roster shows Unknown; no Heartbeat ADMS Log rows unless enabled.
3. ⋮ Reboot on Unknown → next getrequest returns `C:…:REBOOT`.
4. After init → Add push machine → Register → ⋮ INFO works.
