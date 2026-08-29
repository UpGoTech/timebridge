# TimeBridge — Spec index & overall progress

Master tracker for all numbered specs under `spec/`. Each spec has its own detailed phase tracker; this file rolls up status so you can see the whole roadmap at a glance.

**Last updated:** 2026-08-29

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
002 Device Mirror (v1)        ███████████████████░  ~95%   Implemented on feat/device-mirror
002 Device Mirror (v2 restore) ░░░░░░░░░░░░░░░░░░░░    0%   Planned inside 002 Phase H
```

| Spec | Title | Branch | Status | v1 progress | Next action |
|------|-------|--------|--------|-------------|-------------|
| [**001**](001-adms-device-discovery.md) | ADMS Device Discovery & Registration | — (merged) | **Merged** PR #3 | **25 / 26** items · B7 deferred | Post-merge: e2e (B7) |
| [**002**](002-device-mirror.md) | Device Mirror (device ↔ server parity) | `feat/device-mirror` | **Implemented** — QA + PR pending | **~45 / 49** v1 items · Phase H separate | Manual QA §10; open PR |
| — | Device Restore (backup machine) | — | Planned as **002 Phase H** / future `003` | **0 / 6** | After 002 v1 merge |

**Programme totals (v1 scope only):** **23 / 82** checklist items complete · **0** partial · **59** not started

---

## Spec 001 — ADMS Device Discovery & Registration

| Field | Value |
|-------|-------|
| **Doc** | [001-adms-device-discovery.md](001-adms-device-discovery.md) |
| **One-liner** | Capture unknown ADMS serials; Device Registration Desk page; Register / Dismiss |
| **Status** | **Merged** — PR #3 (2026-08-29) |

### Phase rollup

| Phase | Name | Done | Partial | Open | Rollup |
|-------|------|------|---------|------|--------|
| A | Capture unknown signals | 6 | 0 | 0 | `[x]` |
| B | Device Registration page | 6 | 0 | 1 | `[~]` |
| C | Lifecycle & links | 4 | 0 | 0 | `[x]` |
| D | Supporting fixes (pyzk, web port) | 5 | 0 | 0 | `[x]` |
| E | Spec / docs / merge | 4 | 0 | 0 | `[x]` |

### Still open (001)

| # | Item | Owner |
|---|------|-------|
| B7 | Playwright e2e | Dev (deferred post-merge) |

---

## Spec 002 — Device Mirror (device ↔ server parity)

| Field | Value |
|-------|-------|
| **Doc** | [002-device-mirror.md](002-device-mirror.md) |
| **One-liner** | Compare device vs server inventory; store biometric templates; Verify + manual Fetch; 45-day punch window |
| **Status** | **Implemented** on `feat/device-mirror` — manual QA pending |

### Locked decisions (summary)

- Punch compare: **45-day window** (not global totals)
- v1: **count parity + template storage** on server
- v2: **restore to backup device** (Phase H)
- Fetch on drift: **manual only**
- Scheduled reverification: **optional** in TimeBridge Settings

### Phase rollup (v1 — excludes Phase H)

| Phase | Name | Done | Open | Rollup |
|-------|------|------|------|--------|
| A | Spec & data model | 1 | 6 | `[ ]` |
| B | Template vault (ingest & store) | 0 | 9 | `[ ]` |
| C | Mirror verify engine | 0 | 12 | `[ ]` |
| D | Device Mirror Desk page | 0 | 10 | `[ ]` |
| E | Machine list integration | 0 | 3 | `[ ]` |
| F | Scheduled reverification | 0 | 4 | `[ ]` |
| G | Tests, docs, merge | 0 | 5 | `[ ]` |

**v1 subtotal:** 1 / 49 complete (A1 spec file only)

### Phase H — v2 Restore to device (future)

| Phase | Name | Done | Open | Rollup |
|-------|------|------|------|--------|
| H | Restore to backup / addition machine | 0 | 6 | `[ ]` |

### Still open (002)

| # | Item | Owner |
|---|------|-------|
| A2 | Product review checklist (§12) + open questions (§11) | Product |
| A3–G5 | Implementation (after approval) | Dev |
| H1–H6 | Restore feature (after v1 merge) | Dev |

### Recommended implementation order (002)

1. Commit spec → branch `feat/device-mirror`
2. **B** Template vault
3. **C** Verify engine + APIs
4. **D** Desk page
5. **E** List integration
6. **F** Scheduler
7. **G** Tests + PR
8. **H** Restore (v2)

---

## Cross-spec dependencies

| Dependent | Depends on | Notes |
|-----------|------------|-------|
| 002 ADMS verify | 001 (optional) | Mirror works on registered machines; 001 not blocking |
| 002 template ingest | ADMS `/iclock` handlers | Extends existing `adms/api.py` |
| 002 list UX | TimeBridge Machine list | Same DocType as 001 Register target |
| 002 Phase H restore | 002 Phase B | Templates must be stored before push-to-device |

---

## Suggested programme order

| Order | Spec | Rationale |
|-------|------|-----------|
| 1 | **001** ✓ merged | ADMS onboarding shipped (PR #3) |
| 2 | **002 v1** | Core “trust the copy” story; templates + Mirror page |
| 3 | **002 Phase H** (or **003**) | Backup / addition machine restore |

---

## Review queue (you are here)

| Spec | Section | Waiting for |
|------|---------|-------------|
| 001 | §6 Open questions | ✓ Shipped as recommended |
| 001 | §9 Review checklist | ✓ Merged PR #3 |
| 002 | §11 Open questions | Q1–Q6 or “ship with recommendations” |
| 002 | §12 Review checklist | Sign-off to start implementation |

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
