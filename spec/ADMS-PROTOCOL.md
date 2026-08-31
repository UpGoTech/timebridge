# ADMS / iclock — which ZKTeco protocol document?

TimeBridge push devices (`sdk_type: ADMS`, `table=ATTLOG`, `/iclock/cdata`) implement **Attendance PUSH**, not Security PUSH. The repo holds two different PDFs; using the wrong one caused production bugs on Fabrixcel Gate (`NCD8251400238`).

| Document | File | Device type | Paths | Upload ack |
|----------|------|-------------|-------|------------|
| **Attendance PUSH** | [`ZKteco Attendance PUSH Communication Protocol.pdf`](./ZKteco%20Attendance%20PUSH%20Communication%20Protocol.pdf) | Terminals, gates (`DeviceType=att`, `pushver=2.4.x`) | `/iclock/cdata`, `/iclock/getrequest` | **`OK: <count>`** for ATTLOG / OPERLOG |
| **Security PUSH** | [`ZKteco Security PUSH Communication Protocol.pdf`](./ZKteco%20Security%20PUSH%20Communication%20Protocol.pdf) | Access control (`table=rtlog`, `/iclock/registry`) | `/iclock/querydata`, registry tokens | bare **`OK`** or `registry=ok` |

## Bugs caused by reading Security PUSH instead of Attendance PUSH

1. **Bare `OK` on data POST** — Attendance §11.2–11.5 requires `OK: <records processed>`. A bare `OK` is treated as failure; firmware keeps the batch and re-sends every cycle. On production this produced 220 identical 128-record ATTLOG batches (~37k records received, ~9k new).

2. **`TransFlag` digit order** — Attendance order: `1 AttLog, 2 OpLog, 3 AttPhoto, 4 EnrollFP, 5 EnrollUser, 6 FPImage, 7 ChgUser, …`. Security puts EnrollUser at 4 and ChgUser at 5. Using `1111000000` from Security switched off user enrolment flags while requesting fingerprints.

3. **Wrong handshake keys** — Attendance names are `ATTLOGStamp`, `OPERLOGStamp`, `ATTPHOTOStamp`. Invented keys (`OpStamp`, `AttLogStamp`) are ignored. Handshake must also include `TransTimes`, `TransInterval`, and `TimeZone` (minutes for half-hour zones — IST = `330`).

4. **OPERLOG stamp only on USER rows** — Most OPERLOG POSTs are `OPLOG …` audit lines with no `PIN=`. Stamp must advance on every accepted OPERLOG, not only when `parse_userinfo` finds people. Empty POSTs with `Stamp=9999` fall back to server time so `OPERLOGStamp` is never stuck at `9999`.

5. **OpLog TransFlag left off** — Position 2 (`OpLog`) gates the audit channel that Fabrixcel floods with empty POSTs. `USER` rows on `table=OPERLOG` are gated by `EnrollUser` (5), not `OpLog` (2). Handshake uses `1010101000` / `1010101011`.

## Fixes (merged to `develop`)

- PR #18 — `OK: <count>` ack, `parse_oplog`, OPERLOG stamp outside `if records`, correct `TransFlag`, handshake fields
- PR #17 — stamp persistence and format options when device sends `Stamp=9999`

## Authority for implementation

All ADMS attendance-terminal behaviour: **Attendance PUSH PDF** above. Security PUSH applies only if the device posts `table=rtlog` or uses `/iclock/registry`.
