# Spec 005 — Workspace dashboard and Add Machine relocation

| Field | Value |
|-------|-------|
| **Spec ID** | `005` |
| **Branch** | `feat/005-workspace-dashboard` |
| **Status** | **Implemented** |
| **Authority** | This doc; follows [003-device-io.md](003-device-io.md) Add Machine wizard |
| **Created** | 2026-08-31 |
| **Programme tracker** | [spec/README.md](README.md) |

---

## 1. Why?

The Add Machine wizard (spec 003) lived on the TimeBridge workspace as a shortcut and sidebar link, while the TimeBridge Machine list still offered a blank **New** form. Operators had two entry points and could bypass the wizard via `/app/timebridge-machine/new`.

The workspace dashboard showed only three number cards (connected machines, punches today, unmapped punches). Operators need at-a-glance counts for registered machines, enrolled users (active vs archived), and punch-log volume stored on the server.

---

## 2. What?

1. **Add Machine only from TimeBridge Machine list** — list **Add Machine** button, empty-list **Create New**, and direct `/new` URL all route to the `add-machine` wizard.
2. **Remove Add Machine from workspace** — no shortcut or sidebar link; workspace is dashboard + navigation cards only.
3. **Seven number cards** on the TimeBridge workspace:

| Card | DocType | Filter |
|------|---------|--------|
| Registered Machines | TimeBridge Machine | (total) |
| Connected Machines | TimeBridge Machine | `status = Connected` |
| Active Users | TimeBridge Machine User | `is_active = 1` |
| Archived Users | TimeBridge Machine User | `is_active = 0` |
| Total Punch Logs | TimeBridge Punch Log | (total on server) |
| Punches Today | TimeBridge Punch Log | `timestamp >= today` |
| Unmapped Punches | TimeBridge Punch Log | `machine_user` not set |

4. **Wizard breadcrumbs** — `TimeBridge` → `TimeBridge Machine` → `Add Machine`.

---

## 3. Progress tracker

| # | Item | Status |
|---|------|--------|
| 1 | Spec + programme index | `[x]` |
| 2 | Number Card fixtures (4 new) | `[x]` |
| 3 | Workspace layout + remove Add Machine | `[x]` |
| 4 | List `primary_action` → wizard | `[x]` |
| 5 | Form `onload` redirect for `/new` | `[x]` |
| 6 | Wizard breadcrumb update | `[x]` |

---

## 4. How to verify

```bash
bench --site saral.localhost migrate
bench --site saral.localhost clear-cache
bench --site saral.localhost run-tests --app timebridge
```

Manual:

1. **TimeBridge Machine** list → **Add Machine** opens wizard.
2. Empty list → **Create New** opens wizard.
3. `/app/timebridge-machine/new` redirects to wizard.
4. **TimeBridge** workspace shows seven number cards; no Add Machine shortcut.
5. Wizard breadcrumbs: TimeBridge → TimeBridge Machine → Add Machine.

---

## 5. Locked decisions

| # | Decision |
|---|----------|
| Q1 | Do not revoke DocType `create` permission — redirect on form `onload` instead |
| Q2 | Archived users = `is_active = 0` on TimeBridge Machine User |
| Q3 | Timelog counts = total + today + unmapped punch logs on server |
| Q4 | Add Machine removed from workspace entirely; list is the single entry point |
