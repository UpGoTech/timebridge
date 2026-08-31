# Spec 002 — Device Mirror (device ↔ server parity)

| Field | Value |
|-------|-------|
| **Spec ID** | `002` |
| **Branch** | `feat/device-mirror` |
| **Status** | **Implemented** — v1 on branch; manual QA pending (§10) |
| **Authority** | [`ZKteco Attendance PUSH Communication Protocol.pdf`](./ZKteco%20Attendance%20PUSH%20Communication%20Protocol.pdf); [ADMS-PROTOCOL.md](./ADMS-PROTOCOL.md) |
| **Created** | 2026-08-28 |
| **Last updated** | 2026-08-29 |
| **Programme tracker** | [spec/README.md](./README.md) |

---

## 1. Why?

TimeBridge’s job is to **duplicate device data onto the server** so downstream HR processing can trust what it reads. Device Mirror answers: *is everything on the device also on the server?* — with a **45-day punch window**, **template vault**, and **manual fetch** on drift.

---

## 2. What? (scope)

### v1 (this branch)

- Device Mirror Desk page (`/app/device-mirror?machine=…`)
- Count parity: users, punches (window), photos, fingerprint/face templates
- Verify now (PyZK job or ADMS command sequence)
- TimeBridge Device Snapshot + TimeBridge Biometric Template DocTypes
- Machine list → Mirror; `mirror_status` badge
- Optional scheduled reverification in TimeBridge Settings
- Manual fetch per asset (existing APIs + template query)

### v2 (Phase H — not in this branch)

- Restore stored users/templates/photos to a backup device

---

## 3. Progress tracker

Legend: `[x]` done · `[~]` partial · `[ ]` not started

**Overall:** `[~]` v1 implemented — manual QA + PR pending.

### Phase A — Spec & data model

| # | Item | Status |
|---|------|--------|
| A1 | Spec file | `[x]` |
| A2 | Product review | `[~]` | Shipped with recommendations |
| A3 | Branch `feat/device-mirror` | `[x]` |
| A4 | TimeBridge Device Snapshot | `[x]` |
| A5 | TimeBridge Biometric Template | `[x]` |
| A6 | Settings mirror fields | `[x]` |
| A7 | Machine `mirror_status` | `[x]` |

### Phase B — Template vault

| # | Item | Status |
|---|------|--------|
| B1–B5 | ADMS ingest (options, templates, count) | `[x]` |
| B6 | PyZK template pull | `[~]` | Count from read_sizes only |
| B7–B9 | Upsert + flags + tests | `[x]` |

### Phase C — Verify engine

| # | Item | Status |
|---|------|--------|
| C1–C12 | Service, APIs, probes, snapshot, tests | `[x]` |

### Phase D — Desk page

| # | Item | Status |
|---|------|--------|
| D1–D10 | Page, UI, verify, fetch, history, workspace | `[x]` |

### Phase E — Machine list

| # | Item | Status |
|---|------|--------|
| E1–E2 | Row → Mirror, badge formatter | `[x]` |
| E3 | Bulk verify | `[ ]` | Deferred |

### Phase F — Scheduler

| # | Item | Status |
|---|------|--------|
| F1–F4 | Settings + cron + notify | `[x]` |

### Phase G — Tests & merge

| # | Item | Status |
|---|------|--------|
| G1 | Unit tests | `[x]` |
| G2 | Manual QA | `[ ]` |
| G3 | Playwright e2e | `[ ]` | Deferred |
| G4–G5 | PR + CI | `[ ]` |

### Phase H — Restore (v2)

| # | Item | Status |
|---|------|--------|
| H1–H6 | Restore to device | `[ ]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

1. Open `/app/device-mirror?machine=<BM-…>` or click a machine row in the list.
2. **Verify now** → progress → snapshot written.
3. ADMS: confirm OPTIONS / DATA COUNT / ATTLOG window query during verify.
4. **Fetch templates** queues biodata/templatev10 queries; rows land in TimeBridge Biometric Template.

---

## 5. Key paths

| Path | Role |
|------|------|
| `services/device_mirror.py` | Verify orchestration |
| `services/biometric_templates.py` | Template vault |
| `adms/api.py` | Options, templates, querydata, mirror hooks |
| `adms/commands.py` | Mirror verify command queue |
| `adms/parser.py` | Options + template parsers |
| `page/device_mirror/` | Desk page |
| `doctype/timebridge_device_snapshot/` | Snapshots |
| `doctype/timebridge_biometric_template/` | Templates |

Full wireframe, data model, and Phase H restore notes are in git history / programme discussion (2026-08-28).
