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
001 ADMS Device Discovery     ████████████████████░  ~96%   Merged (PR #3) — B7 e2e deferred
002 Device Mirror             ░░░░░░░░░░░░░░░░░░░░    —    Discontinued (see 003)
003 Device I/O reset          █████████████████████  100%   Merged (PR #7)
004 Machine diagnostic log    █████████████████████  100%   Merged (PR #8)
005 Workspace dashboard       █████████████████████  100%   Merged (PR #10 + #11)
006 Daily Punch Summary       █████████████████████  100%   Merged (PR #11)
007 Employee Monthly Punch    █████████████████████  100%   Merged (PR #12)
```

| Spec | Title | Branch | Status | Progress | Next action |
|------|-------|--------|--------|----------|-------------|
| [**001**](001-adms-device-discovery.md) | ADMS Device Discovery & Registration | — (merged) | **Merged** PR #3 | **25 / 26** · B7 deferred | Folded into 003 wizard (push inbox) |
| [**002**](002-device-mirror.md) | Device Mirror | — | **Discontinued** | — | Not shipping; templates/restore out of product |
| [**003**](003-device-io.md) | Device I/O reset | — (merged) | **Merged** PR #7 | Phases A–F | — |
| [**004**](004-machine-log.md) | Machine diagnostic log | — (merged) | **Merged** PR #8 | Phase 1–5 | — |
| [**005**](005-workspace-dashboard.md) | Workspace dashboard & Add Machine | — (merged) | **Merged** PR #10 + #11 | Phase 1–8 | v2 dashboard shipped in PR #11 |
| [**006**](006-daily-punch-summary.md) | Daily Punch Summary report | — (merged) | **Merged** PR #11 | Phase 1–6 | — |
| [**007**](007-employee-monthly-punch-summary.md) | Employee Monthly Punch Summary | — (merged) | **Merged** PR #12 | Phase 1–5 | — |

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

Do not implement remaining 002 phases. Code shipped on `feat/device-mirror` was removed in 003.

---

## Spec 003 — Device I/O reset

| Field | Value |
|-------|-------|
| **Doc** | [003-device-io.md](003-device-io.md) |
| **One-liner** | Strip HRIS + Mirror; Add Machine wizard; Desk-owned user write; diagnostic punched Yes/No |
| **Status** | **Merged** — PR #7 (2026-08-31) |

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
| **Status** | **Merged** — PR #8 (2026-08-31) |

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
| **One-liner** | Slim dashboard (active users chart + 3 cards); Devices/Data/Reports/Logs sidebar; Add Machine from list only |
| **Status** | **Merged** — PR #10 (v1 wizard + cards), PR #11 (v2 slim dashboard) |

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Dashboard service + chart | `[x]` |
| 3 | Number cards + workspace JSON | `[x]` |
| 4 | Patch + tests | `[x]` |
| 5 | List + form wizard routing (v1) | `[x]` |
| 6 | Wizard breadcrumbs (v1) | `[x]` |
| 7 | Dashboard v2 chart + three cards | `[x]` |
| 8 | Sidebar Devices / Data / Reports / Logs | `[x]` |

---

## Spec 006 — Daily Punch Summary report

| Field | Value |
|-------|-------|
| **Doc** | [006-daily-punch-summary.md](006-daily-punch-summary.md) |
| **One-liner** | Date-based punch list; Today's Punch Summary card; Desk Page + CSV export |
| **Status** | **Merged** — PR #11 (2026-08-31) |

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Generalize dashboard punch summary | `[x]` |
| 3 | Daily Punch Summary Script Report + Desk Page | `[x]` |
| 4 | Rename number card + remove desk JS | `[x]` |
| 5 | Workspace link + migration patch | `[x]` |
| 6 | Tests | `[x]` |

---

## Spec 007 — Employee Monthly Punch Summary report

| Field | Value |
|-------|-------|
| **Doc** | [007-employee-monthly-punch-summary.md](007-employee-monthly-punch-summary.md) |
| **One-liner** | Person-based punch list for a whole month; Desk Page + CSV export |
| **Status** | **Merged** — PR #12 (2026-08-31) |

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Monthly punch summary in dashboard.py | `[x]` |
| 3 | Script Report + Desk Page | `[x]` |
| 4 | Workspace link + migration patch | `[x]` |
| 5 | Tests | `[x]` |

---

## Cross-spec dependencies

| Dependent | Depends on | Notes |
|-----------|------------|-------|
| 003 push wizard | 001 pending signals | Reuse Pending Device Signal + register |
| 003 user write (push) | ADMS `/iclock/getrequest` | Durable command queue |
| 004 machine log | 003 device I/O | Sync Log stays ingest-only |
| 006 daily summary | 005 dashboard | Today's Punch Summary card |
| 007 monthly summary | 006 daily summary | Same in/out/hrs rules |
| 002 | — | Discontinued |

---

## Suggested programme order

| Order | Spec | Rationale |
|-------|------|-----------|
| 1 | **001** ✓ merged | ADMS discovery |
| 2 | **003** ✓ merged | Product reset |
| 3 | **004** ✓ merged | Machine diagnostic log |
| 4 | **005** ✓ merged | Workspace dashboard |
| 5 | **006** ✓ merged | Daily Punch Summary report |
| 6 | **007** ✓ merged | Employee Monthly Punch Summary |
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
| 2026-08-31 | Reconcile index: 005/006 merged; 007 PR pending |
| 2026-08-31 | 007 merged (PR #12); programme complete at 100% (001 B7 e2e still deferred) |
