# Spec 005 — Workspace dashboard and Add Machine relocation

| Field | Value |
|-------|-------|
| **Spec ID** | `005` |
| **Branch** | — (merged) |
| **Status** | **Merged** — PR #10 (v1 wizard + cards), PR #11 (v2 slim dashboard) |
| **Authority** | This doc; follows [003-device-io.md](003-device-io.md) Add Machine wizard |
| **Created** | 2026-08-31 |
| **Programme tracker** | [spec/README.md](README.md) |

---

## 1. Why?

The Add Machine wizard (spec 003) lived on the TimeBridge workspace as a shortcut and sidebar link, while the TimeBridge Machine list still offered a blank **New** form. Operators had two entry points and could bypass the wizard via `/app/timebridge-machine/new`.

The v1 dashboard (seven number cards + Punches Per Day chart) showed machine counts and punch volume. Operators need enrolled-user health and **who punched** — distinct people per day, not raw punch rows — plus a clearer sidebar grouped as Devices / Data / Reports / Logs.

---

## 2. What?

### Add Machine (v1 — unchanged)

1. **Add Machine only from TimeBridge Machine list** — list **Add Machine** button, empty-list **Create New**, and direct `/new` URL all route to the `add-machine` wizard.
2. **Remove Add Machine from workspace** — no shortcut or sidebar link.
3. **Wizard breadcrumbs** — `TimeBridge` → `TimeBridge Machine` → `Add Machine`.

### Dashboard v2

**Layout:** chart on top, three number cards below.

| Widget label | Type | Logic |
|--------------|------|--------|
| **Active Users Per Day** | Custom Dashboard Chart | Daily `COUNT(DISTINCT CONCAT(machine, '::', device_user_id))` grouped by `DATE(timestamp)`. Line chart, Last Week, Daily interval. X-axis labels: `30-Aug-26 (Sun)`. |
| **Registered Active Users** | Document Type Number Card | `TimeBridge Machine User` where `is_active = 1`. |
| **Users Punched Today** | Custom Number Card | Distinct `(machine, device_user_id)` pairs with a punch today. Click opens a dialog listing User Name, Punched In, Punched Out, and Punches (sortable columns; default sort Punched In descending). |
| **Unmapped Punches** | Document Type Number Card | `TimeBridge Punch Log` where `machine_user` is not set. |

Removed from workspace: Registered Machines, Connected Machines, Archived Users, Total Punch Logs, Punches Today (row count), Punches Per Day chart.

### Sidebar link cards (v2)

| Card | Links |
|------|-------|
| **Devices** | TimeBridge Machine, TimeBridge Settings |
| **Data** | TimeBridge Machine User |
| **Reports** | Device Roll, Daily Punch Summary, Employee Monthly Punch Summary |
| **Logs** | TimeBridge Sync Log, TimeBridge Machine Log |

Removed: Setup card, TimeBridge Punch Log from sidebar (still reachable via list / card routes).

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | `services/dashboard.py` + tests | `[x]` |
| 3 | Custom chart source + chart fixture | `[x]` |
| 4 | Number card fixtures (Registered Active Users, Users Punched Today) | `[x]` |
| 5 | Workspace JSON (layout + link cards + label fix) | `[x]` |
| 6 | Patch + workspace sync tests | `[x]` |
| 7 | List + form wizard routing (v1) | `[x]` |
| 8 | Wizard breadcrumbs (v1) | `[x]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. **TimeBridge** workspace — **Active Users Per Day** chart at top; three number cards below.
2. Cards: Registered Active Users, Users Punched Today, Unmapped Punches. No machine count cards.
3. Sidebar: Devices (2), Data (1), Reports (3), Logs (2). No Setup card.
4. Hard refresh — all widgets render (`content` uses workspace row **labels**, not fixture doc names).
5. **TimeBridge Machine** list → **Add Machine** opens wizard; `/app/timebridge-machine/new` redirects.

---

## 5. Locked decisions

| # | Decision |
|---|----------|
| Q1 | Do not revoke DocType `create` permission — redirect on form `onload` instead |
| Q2 | **Active user** for chart and Users Punched Today = distinct `(machine, device_user_id)` per calendar day (device PINs are per-machine) |
| Q3 | Registered Active Users = `is_active = 1` on TimeBridge Machine User |
| Q4 | Add Machine removed from workspace entirely; list is the single entry point |
| Q5 | Workspace `content` block values must match child-row labels (not Number Card / Chart doc names) |
