# Spec 013 — Punch Summary enhancements

| Field | Value |
|-------|-------|
| **Spec ID** | `013` |
| **Branch** | `feat/013-punch-summary-enhancements` |
| **Status** | **In progress** |
| **Authority** | This doc; extends [006](006-daily-punch-summary.md) and [007](007-employee-monthly-punch-summary.md) |
| **Created** | 2026-09-06 |
| **Programme tracker** | [spec/README.md](README.md) |

---

## 1. Why?

Operators need In/Out from the day's first and last punch (not direction codes), per-user expected hours for short-day highlighting, a punch-detail popup when there are more than two punches, and A4 Print/PDF for both Daily and Employee Monthly Punch Summary.

---

## 2. What?

### In / Out rule (both reports)

| Case | Punched In | Punched Out | Working Hrs |
|------|------------|-------------|-------------|
| 0 punches | blank | blank | blank |
| 1 punch | that punch | blank | blank |
| 2+ punches | earliest timestamp | latest timestamp | last − first |

`punch_direction` is ignored for summary In/Out. Direction is still shown in the punch-detail popup.

### Expected hours

| Source | Field |
|--------|-------|
| TimeBridge Machine User | `expected_working_hours` (optional Float) |
| TimeBridge Settings | `default_expected_working_hours` (Float, installed default **9**) |

Resolve: Machine User if set → else Settings → else code fallback `9.0`.

- Monthly: threshold from the **selected** Machine User, then Settings.
- Daily: threshold per row from that row's linked Machine User, then Settings.

### Row status / highlight

| Status | When | Screen | Print | PDF |
|--------|------|--------|-------|-----|
| `absent` | no punches | normal | normal | normal |
| `ok` | hrs ≥ expected | normal | normal | normal |
| `short` | hrs not None and hrs **&lt;** expected | whole-row colour | colour | grayscale |
| `no_out` | has In, no Out | third whole-row style | colour | grayscale |

### Punch-count popup

- Clickable only when punches **&gt; 2**.
- Read-only list: `time · direction`.
- No In/Out override storage (report stays read-only).

### Print / PDF

- **Print:** browser print with A4 portrait print CSS.
- **PDF:** separate download; same layout; short/no_out styles in grayscale.
- Both Daily and Employee Monthly pages.
- Content: title, identity (user+month or date+machine), table, legend for three styles.

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Expected hours fields + seed 9 | `[ ]` |
| 3 | First/last summarize + row_status + punch_details | `[ ]` |
| 4 | Desk Page highlight + popup | `[ ]` |
| 5 | Print + PDF (both reports) | `[ ]` |
| 6 | Tests | `[ ]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. Set expected hours on a Machine User (e.g. 8); leave another blank (uses Settings 9).
2. Open Employee Monthly Punch Summary — first/last In/Out; short and no-out rows highlighted.
3. Day with &gt;2 punches — Punches link opens time · direction list.
4. Print and PDF — A4 portrait, legend, grayscale short/no_out on PDF.
5. Same checks on Daily Punch Summary.

---

## 5. Locked decisions

| # | Decision |
|---|----------|
| Q1 | First punch = In, last = Out; one punch → Out/Hrs blank |
| Q2 | Both Daily and Monthly |
| Q3 | Strict `&lt;` expected; no Out = third style; whole row |
| Q4 | MU field + Settings fallback (default 9, stored on install) |
| Q5 | Popup read-only, punches &gt; 2, time + direction; no override storage |
| Q6 | Browser Print + PDF download; legend; PDF grayscale; A4 portrait; both reports |
