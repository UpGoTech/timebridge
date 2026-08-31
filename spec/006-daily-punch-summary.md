# Spec 006 — Daily Punch Summary report

| Field | Value |
|-------|-------|
| **Spec ID** | `006` |
| **Branch** | `feat/006-daily-punch-summary` |
| **Status** | **Ready for review** (modal UI) |
| **Authority** | This doc; follows [005-workspace-dashboard.md](005-workspace-dashboard.md) |
| **Created** | 2026-08-31 |
| **Programme tracker** | [spec/README.md](README.md) |

---

## 1. Why?

Operators need a **date-based punch list** — who punched on a given day, with in/out times and punch count — not just a headcount on the dashboard.

The **Users Punched Today** number card opened a custom dialog (`timebridge_desk.js`) that never worked reliably. One report with a date filter, search, and CSV export replaces that popup.

---

## 2. What?

### Daily Punch Summary (modal + Desk Page)

Delivered as a **JavaScript modal** (Opening Headcount style) — not a Script Report grid.

| Entry point | Behaviour |
|-------------|-----------|
| **Today's Punch Summary** card | Opens modal with today's date |
| **Reports → Daily Punch Summary** | Desk Page with the same panel inline |
| **API** | `get_daily_punch_summary_list(date, machine?)` |

| Filter | Required | Default |
|--------|----------|---------|
| Date | yes | today |
| Machine | no | all machines |

| Column | Notes |
|--------|-------|
| Machine | Shown only when no machine filter (all machines) |
| User Name | From TimeBridge Machine User, else device PIN |
| Punched In | Earliest In punch, else first punch of the day |
| Punched Out | Latest Out punch, else blank |
| Punches | Row count for that user on that day |

- Default sort: **Punched In** descending; click column headers to re-sort
- Search bar in toolbar; footer shows user count + **Export CSV**

Data source: `TimeBridge Punch Log` only (no HR attendance table).

### Today's Punch Summary (number card rename)

| Before | After |
|--------|-------|
| Users Punched Today | **Today's Punch Summary** |

Click behaviour: opens the **Daily Punch Summary modal** with `date` = today (card click handler in `timebridge_desk.js`).

### Removed

- Script Report client UI (`daily_punch_summary.js` query report)
- Broken earlier popup (`frappe.ui.Dialog` variant)

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Generalize `dashboard.py` punch summary | `[x]` |
| 3 | Daily Punch Summary Script Report | `[x]` |
| 4 | Rename number card + remove desk JS | `[x]` |
| 5 | Workspace link + migration patch | `[x]` |
| 6 | Tests | `[x]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. **TimeBridge** workspace → click **Today's Punch Summary** → **Daily Punch Summary** opens with today's date
2. Reports → **Daily Punch Summary** — change date, optional machine filter
3. Search filters rows; footer count updates
4. Export CSV downloads visible rows
5. Column headers re-sort the table

---

## 5. Locked decisions

| # | Decision |
|---|----------|
| Q1 | Report name: **Daily Punch Summary** |
| Q2 | Card label: **Today's Punch Summary** |
| Q3 | Machine filter optional; Machine column when viewing all machines |
| Q4 | Active user = distinct `(machine, device_user_id)` per calendar day |
| Q5 | Card click opens modal; Reports sidebar opens Desk Page with same panel |
