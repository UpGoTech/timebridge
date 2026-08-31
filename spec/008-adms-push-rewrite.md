# Spec 008 — ADMS Attendance PUSH rewrite

| Field | Value |
|-------|-------|
| **Spec ID** | `008` |
| **Branch** | `feat/008-adms-push-rewrite` |
| **Status** | **Implemented** — branch `feat/008-adms-push-rewrite` |
| **Authority** | [`ZKteco Attendance PUSH Communication Protocol.pdf`](./ZKteco%20Attendance%20PUSH%20Communication%20Protocol.pdf); [ADMS-PROTOCOL.md](./ADMS-PROTOCOL.md) |
| **Created** | 2026-08-31 |
| **Programme tracker** | [spec/README.md](./README.md) |

---

## 1. Why?

The ADMS receiver grew as patches on a single `api.py`. Photo save is broken (`save_photo` missing). Operators cannot choose which wire traffic to keep. First registration does not automatically harvest users / recent ATTLOG / photos. Server→device name sync only happens when Desk buttons call `user_write`, not on ordinary Machine User field edits.

This spec rebuilds the push path against Attendance PUSH SDK §5–§13, keeps proven protocol rules (ack, TransFlag, stamps), and adds operator-controlled Request Log + bootstrap + name push.

**Out of scope:** PyZK pull rewrite; Security PUSH (`rtlog` / registry); uploading photos/templates onto the device.

---

## 2. What?

1. Layered `adms/` package: ingress → protocol → upload → commands → sync → persist.
2. **TimeBridge ADMS Request Log** — wire audit of inbound `/iclock/*`.
3. **Per-machine Check fields** on TimeBridge Machine (ADMS) controlling which categories are logged.
4. **Bootstrap** after register: queue USERINFO + ATTLOG (`default_fetch_days`) + photo fetch.
5. Fix photo ingest; Desk Machine User edits queue `DATA UPDATE USERINFO`.

### Locked decisions

| # | Decision |
|---|----------|
| Q1 | Attendance PUSH PDF only (not Security PUSH) |
| Q2 | Request Log gated by Machine form ticks (not always-on; not Settings `enable_debug_log`) |
| Q3 | Unknown SN always written to Request Log (discovery) |
| Q4 | Bootstrap ATTLOG window = `TimeBridge Settings.default_fetch_days` |
| Q5 | Do not set stamps to `0` on register (avoids re-send loops) |
| Q6 | Inbound USERINFO must not overwrite Desk-owned name/card/privilege |

### Machine ADMS Request Log ticks

| Field | Default | Category |
|-------|---------|----------|
| `log_adms_handshake` | 0 | GET cdata handshake |
| `log_adms_heartbeat` | 0 | getrequest poll |
| `log_adms_ping` | 0 | ping |
| `log_adms_attendance` | 1 | ATTLOG |
| `log_adms_users` | 1 | USER / OPERLOG |
| `log_adms_photos` | 1 | photos / fdata |
| `log_adms_commands` | 1 | command out + devicecmd |
| `log_adms_bodies` | 0 | request/response body previews |

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | TimeBridge ADMS Request Log DocType | `[x]` |
| 3 | Machine ADMS log Check fields + form section | `[x]` |
| 4 | ingress audit (gated) + layered router | `[x]` |
| 5 | Protocol handshake / ack / stamps (parity) | `[x]` |
| 6 | Upload ATTLOG / USER / photos (`save_photo` fixed) | `[x]` |
| 7 | Commands queue + bootstrap on register | `[x]` |
| 8 | Machine User `on_update` → DATA UPDATE USERINFO | `[x]` |
| 9 | Workspace link + patch | `[x]` |
| 10 | Unit tests | `[x]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost run-tests --app timebridge --module timebridge.timebridge.adms
```

Manual:

1. Machine form → ADMS Request Log section → toggle Heartbeat on → device poll → Request Log row.
2. Toggle Heartbeat off → no new Heartbeat rows.
3. Register pending SN → Device Commands for USERINFO + ATTLOG + photo fetch appear.
4. Edit Machine User name on ADMS machine → Device Command `DATA UPDATE USERINFO`.
5. Photo POST with PIN+Content → Machine User.photo set.

---

## 5. Review checklist

- [ ] `OK: <count>` for ATTLOG / OPERLOG user batches
- [ ] TransFlag Attendance digit order
- [ ] OPERLOGStamp advances with empty USER bodies
- [ ] Request Log respects Machine ticks
- [ ] Unknown SN still Pending + Request Log
- [ ] Photo `save_photo` works (regression test)
