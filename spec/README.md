# TimeBridge — Spec index & overall progress

Master tracker for all numbered specs under `spec/`. Each spec has its own detailed phase tracker; this file rolls up status so you can see the whole roadmap at a glance.

**Last updated:** 2026-08-30

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
003 Device I/O reset          ██░░░░░░░░░░░░░░░░░░   ~8%   Spec written; build on feat/003-device-io
```

| Spec | Title | Branch | Status | v1 progress | Next action |
|------|-------|--------|--------|-------------|-------------|
| [**001**](001-adms-device-discovery.md) | ADMS Device Discovery & Registration | — (merged) | **Merged** PR #3 | **25 / 26** · B7 deferred | Folded into 003 wizard (push inbox) |
| [**002**](002-device-mirror.md) | Device Mirror | — | **Discontinued** | — | Not shipping; templates/restore out of product |
| [**003**](003-device-io.md) | Device I/O reset | `feat/003-device-io` | **In progress** | Spec A1–A2 | Strip HR/Mirror, wizard, user write, roll |

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
| **Status** | **In progress** on `feat/003-device-io` |

### Locked decisions (summary)

- TimeBridge is device I/O. Attendance as HR lives elsewhere.
- Person = Machine User per (machine, PIN).
- Roll sheet = punched Yes/No in a date range (not working-day Absent).
- Wizard: operator picks Pull or Push.
- Desk owns create/edit/delete of PIN+name; harvest JPEGs only; no templates.
- Greenfield: no compatibility with old Employee/Attendance data.

### Phase rollup

| Phase | Name | Rollup |
|-------|------|--------|
| A | Spec & cut list | `[~]` |
| B | Strip HRIS and Mirror | `[ ]` |
| C | Add Machine wizard | `[ ]` |
| D | Desk-owned user write | `[ ]` |
| E | Device Roll | `[ ]` |
| F | Tests, docs, verify | `[ ]` |

---

## Cross-spec dependencies

| Dependent | Depends on | Notes |
|-----------|------------|-------|
| 003 push wizard | 001 pending signals | Reuse Pending Device Signal + register |
| 003 user write (push) | ADMS `/iclock/getrequest` | Durable command queue |
| 002 | — | Discontinued |

---

## Suggested programme order

| Order | Spec | Rationale |
|-------|------|-----------|
| 1 | **001** ✓ merged | ADMS discovery |
| 2 | **003** | Product reset (this version) |
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
