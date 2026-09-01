# Spec 009 — ADMS iclock server and onboarding rewrite

| Field | Value |
|-------|-------|
| **Spec ID** | `009` |
| **Branch** | `feat/009-adms-onboarding` |
| **Status** | **In progress** |
| **Authority** | [`ZKteco Attendance PUSH Communication Protocol.pdf`](./ZKteco%20Attendance%20PUSH%20Communication%20Protocol.pdf) §5–§13; [ADMS-PROTOCOL.md](./ADMS-PROTOCOL.md) |
| **Created** | 2026-09-01 |
| **Programme tracker** | [spec/README.md](./README.md) |
| **Supersedes** | [008-adms-push-rewrite.md](008-adms-push-rewrite.md) |

---

## 1. Why?

ADMS onboarding grew as patches: Pending Device Signal, Device Registration, Add Machine inbox, Request Log ticks, and auto bootstrap on register. Operators could not turn the receiver off. Register immediately queued USERINFO / ATTLOG / photos. Handshake was sent to unknown serials, so firmware started uploading before anyone accepted the device.

This spec treats `/iclock` as a **server** the device dials, rebuilds the receiver from Attendance PUSH (not the old `adms/` package), and makes ingest manual except realtime punches after the operator ticks AttLog.

## 2. What?

1. Global **ADMS Server** switch on TimeBridge Settings (default Off).
2. Off: renderer does not claim `/iclock/*` → Frappe website 404. No log, no Pending machine, no handshake.
3. On: every GET/POST logged to **TimeBridge ADMS Log** per Settings log toggles (Heartbeat/Ping off by default). Operator adds Pending machine in Add Machine → Push. Device init updates that row by serial; unknown serials get `OK` only. See [010-adms-server-console.md](010-adms-server-console.md) for the Settings roster and recovery commands.
4. Register on the Machine form completes handshake (Format II TransFlag with no types). No QUERY on register.
5. Custom Desk form: stats from getrequest INFO / INFO command; Receive ticks; Download queues `DATA QUERY` for ticked types only.
6. Delete old onboarding DocTypes, Device Registration page, and the `adms/` package.

**Out of scope:** PyZK pull rewrite; Security PUSH; Vue/frappe-ui SPA; encryption (`Encrypt=0`).

### Locked decisions (grilling)

| # | Decision |
|---|----------|
| Q1 | Realtime Punch Log only after AttLog Receive is ticked. No QUERY on register. |
| Q2 | Delete entire `adms/` package. New `iclock/` package. Protocol semantics from the PDF (`OK: n`, stamp names, Attendance TransFlag order, HTTP 200 while On). |
| Q3 | Desk TimeBridge Machine form — not a Vue SPA. |
| Q4 | Unknown SN: no `GET OPTION FROM`. Discovery is the init GET. |
| Q5 | Add Machine → Push lists devices that sent **Handshake** or **Heartbeat** only. Operator adopts from that list — never types a serial manually. Device init updates the Pending row by serial; unknown serials get `OK` only (peer row only). |
| Q6 | First handshake: all TransFlag types off. Download only for ticked Receive types. |
| Q7 | Global Settings **ADMS Server Enabled**. Off = do not claim `/iclock` (404). On = spec replies + log every request. Log ticks on Machine are gone. |
| Q8 | Receive ticks control TransFlag only. ATTLOG POST is stored only when AttLog Receive is on. |

## 3. Protocol (PDF)

**Init (device):** `GET /iclock/cdata?SN=&options=all&pushver=&language=&pushcommkey=`

**Handshake after Register:** `GET OPTION FROM: {SN}` plus `ATTLOGStamp` / `OPERLOGStamp` / `ATTPHOTOStamp` / `BIODATAStamp` / `IDCARDStamp` / `ERRORLOGStamp`, `ErrorDelay`, `Delay`, `TransTimes`, `TransInterval`, `TimeZone` (IST = 330), `Realtime`, `Encrypt=0`, `ServerVer`, `PushProtVer`, `PushOptionsFlag`, `PushOptions`. GMT `Date` header.

**TransFlag Format II only.** `TransFlag=TransData AttLog …`. Format I `0000000000` still auto-uploads attendance photos. Empty type list = no auto-upload.

**Ack:** `OK: <n>` for ATTLOG / OPERLOG user batches. HTTP 200 while server On. Never HTTP 500. Never stamp `0`.

**Stats:** getrequest `INFO=` (§9) plus command `INFO` (§12.4.3). Photo count via INFO keys / `DATA COUNT`.

**Download:** `DATA QUERY ATTLOG StartTime=… EndTime=…`, `DATA QUERY USERINFO`, photo queries. TransFlag changes apply on the next init.

## 4. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Remove `adms/`, Pending Device Signal, Device Registration, ADMS Request Log | `[x]` |
| 3 | Settings `adms_server_enabled`; `can_render` False when Off | `[x]` |
| 4 | `iclock/` handshake, stamps, ack, discovery → Pending Machine | `[x]` |
| 5 | Upload persist, INFO/stats, Device Command QUERY, ADMS Log | `[x]` |
| 6 | Machine form + Add Machine inbox + workspace | `[x]` |
| 7 | Tests + migrate | `[x]` |

## 5. Related

- [010-adms-server-console.md](010-adms-server-console.md) — Settings roster, log toggles, peer REBOOT recovery.

## 6. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost run-tests --app timebridge --module timebridge.timebridge.iclock
```

Manual:

1. Settings → ADMS Server off. `curl /iclock/cdata?SN=TEST&options=all` → 404. No Machine, no Log.
2. Enable ADMS Server. Reboot or wait for device heartbeat/handshake. Add Machine → Push lists the serial. Register on the Machine form. Unknown serial → `OK`, peer row only, no Machine row.
3. Open the machine → Register. Next curl → `GET OPTION FROM` with empty TransData.
4. Tick AttLog Receive. Download a date range. Device collects QUERY on getrequest. New punches land in Punch Log.
5. Disable server → further `/iclock` is 404, no new Log rows.

## 7. Review checklist

- [ ] Server Off → 404, no writes
- [ ] Server On → requests in ADMS Log per category toggles
- [ ] Pending init is not `GET OPTION FROM`
- [ ] Format II TransFlag; never Format I zeros
- [ ] No bootstrap QUERY on Register
- [ ] AttLog Receive off → ACK, no Punch Log row
