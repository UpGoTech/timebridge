# Spec 007 — Employee Monthly Punch Summary report

| Field | Value |
|-------|-------|
| **Spec ID** | `007` |
| **Branch** | `feat/007-employee-monthly-punch-summary` |
| **Status** | **Ready for review** |
| **Authority** | This doc; follows [006-daily-punch-summary.md](006-daily-punch-summary.md) |
| **Created** | 2026-08-31 |
| **Programme tracker** | [spec/README.md](README.md) |

---

## 1. Why?

Operators need a **person-based punch list** for a whole month — in/out times and punch count per day — complementing Daily Punch Summary (all users for one day).

---

## 2. What?

### Employee Monthly Punch Summary (Desk Page)

Delivered as a **Desk Page** with inline table UI — not a Script Report grid (same pattern as spec 006).

| Entry point | Behaviour |
|-------------|-----------|
| **Reports → Employee Monthly Punch Summary** | Desk Page with filter sidebar |
| **API** | `get_employee_monthly_punch_summary_list(machine_user, month)` |

**Report name:** **Employee Monthly Punch Summary** (operator label). There is no Employee DocType (removed in spec 003). The filter is **TimeBridge Machine User**; `user_id` is globally unique across machines.

| Filter | Required | Default |
|--------|----------|---------|
| User | yes | — |
| Month | yes | current month (Year + Month dropdowns) |

| Column | Notes |
|--------|-------|
| Date | Calendar day (`05-Aug-2026 (Wed)`) |
| Punched In | Earliest In punch, else first punch of the day |
| Punched Out | Latest Out punch, else blank |
| Working Hrs | Duration from Punched In to Punched Out (`H:MM`); blank when no out punch |
| Punches | Row count for that user on that day |

- One row per **calendar day** in the month (blank in/out/hrs on absent days)
- Punches for the selected user's `user_id` on **all machines** merged per day
- Default sort: **Date** ascending; click column headers to re-sort
- Headline band (replaces search): User ID + Name on the left, Month + Year on the right
- Footer shows days-with-punches count + **Export CSV**

Data source: `TimeBridge Punch Log` only.

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Monthly punch summary in `dashboard.py` | `[x]` |
| 3 | Employee Monthly Punch Summary Script Report + Desk Page | `[x]` |
| 4 | Workspace link + migration patch | `[x]` |
| 5 | Tests | `[x]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. Reports → **Employee Monthly Punch Summary** — pick User + month
2. All calendar days shown; days with punches show in/out/hrs/count
3. User who punched on two machines same day → one merged row per day
4. Export CSV downloads all rows
5. Column headers re-sort the table

---

## 5. Locked decisions

| # | Decision |
|---|----------|
| Q1 | Report name: **Employee Monthly Punch Summary** |
| Q2 | User filter = **TimeBridge Machine User** Link; backend queries by `user_id` globally |
| Q3 | No Employee DocType — display name only; `user_id` is system-wide unique |
| Q4 | All calendar days in month, blanks for absent days |
| Q5 | Same in/out/hrs/punch-count rules as Daily Punch Summary |
| Q6 | Desk Page + inline UI, same pattern as spec 006 |
