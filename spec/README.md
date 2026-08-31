# TimeBridge — Spec index & overall progress

Master tracker for all numbered specs under `spec/`. Each spec has its own detailed phase tracker; this file rolls up status so you can see the whole roadmap at a glance.

**Last updated:** 2026-08-31

---

## How to read this

| Symbol | Meaning |
|--------|---------|
| `[x]` | Done |
| `[~]` | Partial / needs review |
| `[ ]` | Not started |
| **Blocked** | Waiting on product decision or upstream spec |

Update this file whenever a spec’s status or phase completion changes (same PR as the work, or a dedicated “reconcile spec” commit).

---

## Overall roadmap

```
001 ADMS Device Discovery     ████████████████████░  ~96%   Merged (PR #3) — B7 deferred
002 Device Mirror             ░░░░░░░░░░░░░░░░░░░░    —    Discontinued (see 003)
003 Device I/O reset          ████████████████████░  ~95%   Merged to develop
004 Machine diagnostic log    ████████████████████░  ~95%   Merged to develop
005 Workspace dashboard     ████████████████████░  ~95%   v2 on feat/005-workspace-dashboard-v2
006 Daily Punch Summary     ░░░░░░░░░░░░░░░░░░░░    —    feat/006-daily-punch-summary
```

| Spec | Title | Branch | Status | v1 progress | Next action |
|------|-------|--------|--------|-------------|-------------|
| [**001**](001-adms-device-discovery.md) | ADMS Device Discovery & Registration | — (merged) | **Merged** PR #3 | **25 / 26** · B7 deferred | Folded into 003 wizard (push inbox) |
| [**002**](002-device-mirror.md) | Device Mirror | — | **Discontinued** | — | Not shipping; templates/restore out of product |
| [**003**](003-device-io.md) | Device I/O reset | — (merged) | **Merged** | Phases A–F | — |
| [**004**](004-machine-log.md) | Machine diagnostic log | — (merged) | **Merged** | Phase 1–5 | — |
| [**005**](005-workspace-dashboard.md) | Workspace dashboard & Add Machine | `feat/005-workspace-dashboard-v2` | **In progress** | Phase 1–8 | PR to develop |
| [**006**](006-daily-punch-summary.md) | Daily Punch Summary report | `feat/006-daily-punch-summary` | **In progress** | Phase 1–6 | Build + review |

---

## Spec 001 — ADMS Device Discovery & Registration

| Field | Value |
|-------|-------|
| **Doc** | [001-adms-device-discovery.md](001-adms-device-discovery.md) |
| **One-liner** | Capture unknown ADMS serials; Device Registration Desk page; Register / Dismiss |
| **Status** | **Merged** — PR #3 (2026-08-29). Push inbox reused by 003 Add Machine wizard. |

Still open: Playwright e2e (B7), deferred.

---

## Spec 002 — Device Mirror — DISCONTINUED

| Field | Value |
|-------|-------|
| **Doc** | [002-device-mirror.md](002-device-mirror.md) |
| **One-liner** | Device vs server parity; template vault; restore to backup unit |
| **Status** | **Discontinued** 2026-08-30 — product is device I/O without template storage or restore (spec 003) |

Do not implement remaining 002 phases. Code shipped on `feat/device-mirror` is removed in 003.

---

## Spec 003 — Device I/O reset

| Field | Value |
|-------|-------|
| **Doc** | [003-device-io.md](003-device-io.md) |
| **One-liner** | Strip HRIS + Mirror; Add Machine wizard; Desk-owned user write; diagnostic punched Yes/No |
| **Status** | **Merged** to develop |

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| A | Spec & cut list | `[x]` |
| B | Strip HRIS and Mirror | `[x]` |
| C | Add Machine wizard | `[x]` |
| D | Desk-owned user write | `[x]` |
| E | Device Roll | `[x]` |
| F | Tests, docs, verify | `[x]` |

---

## Spec 004 — Machine diagnostic log

| Field | Value |
|-------|-------|
| **Doc** | [004-machine-log.md](004-machine-log.md) |
| **One-liner** | Per-machine log for connect/ADMS/pull errors and warnings |
| **Status** | **Merged** to develop |

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| 1 | Spec + DocType | `[x]` |
| 2 | Helper + retention | `[x]` |
| 3 | Instrument code paths | `[x]` |
| 4 | Tests | `[x]` |

---

## Spec 005 — Workspace dashboard and Add Machine relocation

| Field | Value |
|-------|-------|
| **Doc** | [005-workspace-dashboard.md](005-workspace-dashboard.md) |
| **One-liner** | Slim dashboard (active users chart + 3 cards); Devices/Data/Logs/Reports sidebar; Add Machine from list only |
| **Status** | **In progress** on `feat/005-workspace-dashboard-v2` |

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Dashboard service + chart | `[x]` |
| 3 | Number cards + workspace JSON | `[x]` |
| 4 | Patch + tests | `[x]` |
| 5 | List + form wizard routing (v1) | `[x]` |
| 6 | Wizard breadcrumbs (v1) | `[x]` |

---

## Cross-spec dependencies

| Dependent | Depends on | Notes |
|-----------|------------|-------|
| 003 push wizard | 001 pending signals | Reuse Pending Device Signal + register |
| 003 user write (push) | ADMS `/iclock/getrequest` | Durable command queue |
| 004 machine log | 003 device I/O | Sync Log stays ingest-only |
| 002 | — | Discontinued |

---

## Suggested programme order

| Order | Spec | Rationale |
|-------|------|-----------|
| 1 | **001** ✓ merged | ADMS discovery |
| 2 | **003** ✓ merged | Product reset |
| 3 | **004** ✓ merged | Machine diagnostic log |
| 4 | **005** | Workspace dashboard |
| 5 | **006** | Daily Punch Summary report |
| — | **002** | Abandoned |

---

## Adding a new spec

1. Create `spec/NNN-short-name.md` (next number in sequence).
2. Include: Why / What / Progress tracker / How to verify / Review checklist.
3. Add a row to **Overall roadmap** and a full section in this file.
4. Link back here from the new spec header.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-08-28 | Initial index: 001 + 002 rollup |
| 2026-08-29 | 001 merged (PR #3); reconcile tracker |
| 2026-08-30 | 003 Device I/O reset; 002 discontinued |
| 2026-08-31 | 004 Machine diagnostic log |
| 2026-08-31 | 005 Workspace dashboard and Add Machine relocation |
| 2026-08-31 | 006 Daily Punch Summary report |
