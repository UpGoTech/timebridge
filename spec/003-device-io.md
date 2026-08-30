# Spec 003 — Device I/O reset

| Field | Value |
|-------|-------|
| **Spec ID** | `003` |
| **Branch** | `feat/003-device-io` |
| **Status** | **In progress** |
| **Authority** | [`ZKteco Push SDK.pdf`](./ZKteco%20Push%20SDK.pdf) for ADMS; [pyzk](https://github.com/fananimi/pyzk) for pull; this doc for product behaviour |
| **Created** | 2026-08-30 |
| **Last updated** | 2026-08-30 |
| **Programme tracker** | [spec/README.md](./README.md) |

---

## 1. Why?

TimeBridge’s job is to talk to biometric terminals and hold what they know: enrolled PINs, punches, and JPEGs when firmware can send them. The current app also owns a parallel HRIS (Organization, Employee, Leave, Attendance with hours/late/half-day) and Device Mirror (template vault, restore). That is the wrong product.

This version **discontinues HR and Mirror** and ships a greenfield device I/O cut. Existing TimeBridge sites are not a compatibility target.

### What the device actually stores (locked)

**User slot:** PIN (`user_id`), internal UID, name, privilege, keypad password, RFID card, group; fingerprint/face **templates** (binary, not displayable); optional JPEG (`USERPIC` / `BIOPHOTO`) on some facial firmware. pyzk 0.9 cannot read photos.

**ATTLOG:** PIN + timestamp, plus status / verify mode / workcode. Many units send `status=255` — In/Out from the device is not fact.

**Push vs pull cannot be auto-detected.** Pull: we dial 4370. Push: the device dials `/iclock`. The wizard asks the operator.

Same PIN on two machines is two people unless the operator copies it.

---

## 2. What? (goal)

1. **Add Machine wizard** — operator chooses Pull or Push on step 1; remaining steps follow that transport.
2. **Ingest** users and punches (pull fetch + ADMS push). JPEG harvest only.
3. **Desk-owned users** — create / edit / delete PIN+name (and card/privilege/password) on selected machines. Biometrics still enrol at the terminal.
4. **Diagnostic roll sheet** — for each PIN on a machine, did they punch in the date range? Yes / No. Not HR attendance.
5. **Strip** Employee, org tree, Shift, Leave, Holiday, Attendance engine, HR reports, Device Mirror / templates / restore.

Out of scope: ERPNext Employee mapping, writing photos/templates onto the device, auto-polling pull machines, Matrix/Suprema drivers.

---

## 3. Progress tracker

Legend: `[x]` done · `[~]` partial · `[ ]` not started

### Phase A — Spec & cut list

| # | Item | Status | Notes |
|---|------|--------|-------|
| A1 | This spec + programme index | `[x]` | |
| A2 | Mark spec 002 discontinued | `[x]` | Restore/templates not in this version |
| A3 | README / AGENTS.md product statement | `[ ]` | Device I/O, not attendance HR |

### Phase B — Strip HRIS and Mirror

| # | Item | Status | Notes |
|---|------|--------|-------|
| B1 | Delete Employee, Organization, Branch, Department, Shift, Leave, Leave Type, Holiday, Attendance | `[ ]` | Plus tests/controllers |
| B2 | Delete Device Mirror page, Snapshot, Biometric Template, Mirror Machine | `[ ]` | |
| B3 | Delete Attendance Report, Punch Register, Employee Attendance Detail, Employee Working Hours | `[ ]` | Punch Log list remains the ledger |
| B4 | Delete timebridge-setup page; employee/attendance charts | `[ ]` | |
| B5 | Slim Machine / Machine User / Punch Log / Settings JSON | `[ ]` | Drop employee, processed, mirror, weekly-off |
| B6 | Slim APIs, hooks scheduler, logger, photos, pull_sync, ADMS handlers | `[ ]` | Keep punch ingest + JPEG harvest |
| B7 | Patch to drop discontinued DocTypes/pages/reports on migrate | `[ ]` | Greenfield; force-delete |
| B8 | Rebuild TimeBridge workspace | `[ ]` | Machines, users, punches, roll, add-machine |

### Phase C — Add Machine wizard

| # | Item | Status | Notes |
|---|------|--------|-------|
| C1 | Desk page `add-machine` (desk-page-ui) | `[ ]` | Operator picks Pull or Push |
| C2 | Pull: IP/port/comm key → probe 4370 → save PyZK machine → fetch users/punches | `[ ]` | Failure ≠ “must be push” |
| C3 | Push: show `/iclock` URL; pending SN table (spec 001); register ADMS machine | `[ ]` | Fold Device Registration into this page |
| C4 | Optional JPEG request after push register | `[ ]` | Existing photo fetch |
| C5 | Workspace shortcut | `[ ]` | Replaces timebridge-setup |

### Phase D — Desk-owned user write

| # | Item | Status | Notes |
|---|------|--------|-------|
| D1 | Durable `TimeBridge Device Command` queue (not Redis-only) | `[ ]` | Push writes survive restart |
| D2 | ADMS `DATA UPDATE USERINFO` / `DATA DELETE USERINFO` | `[ ]` | Push SDK |
| D3 | pyzk `set_user` / `delete_user` | `[ ]` | Immediate on pull session |
| D4 | Create dialog: PIN, name, optional card/privilege/password, pick machines | `[ ]` | N Machine User rows; PIN clash skips that machine |
| D5 | Edit/delete: this row; optional apply to other machines with same PIN | `[ ]` | No Person doctype |
| D6 | Inbound USERINFO creates new PINs; does **not** overwrite Desk name/card/privilege | `[ ]` | Finger/face flags may update |

### Phase E — Device Roll

| # | Item | Status | Notes |
|---|------|--------|-------|
| E1 | Script Report: machine + from/to date | `[ ]` | Rows = Machine Users |
| E2 | Punched? Yes/No; optional last punch timestamp | `[ ]` | No hours, weekly-off, leave |

### Phase F — Tests, docs, verify

| # | Item | Status | Notes |
|---|------|--------|-------|
| F1 | Unit: USERINFO command payload | `[ ]` | |
| F2 | Unit: inbound upsert does not overwrite Desk fields | `[ ]` | |
| F3 | Unit: roll-sheet Yes/No | `[ ]` | |
| F4 | Integration: fan-out PIN clash skip | `[ ]` | |
| F5 | Migrate + run-tests on site | `[ ]` | |

---

## 4. How it works

```
Add Machine
  ├─ Pull → probe 4370 → TimeBridge Machine (PyZK) → pull_sync users+punches
  └─ Push → wait /iclock SN → TimeBridge Machine (ADMS) → device POSTs ATTLOG/USERINFO

Desk Machine User ──write──► Pull: pyzk set_user
                 └─queue──► Push: TimeBridge Device Command → /iclock/getrequest

Device USERINFO ──upsert──► new PIN = insert; existing = flags only (Desk owns names)

Punch Log (machine + PIN + timestamp, unique punch_key)

Device Roll = Machine User ⨯ Punch Log in range → Yes/No
```

### Kept DocTypes

TimeBridge Machine, Machine User, Punch Log, Pending Device Signal, Sync Log, Settings (slim), **Device Command** (new).

### Person model

One **Machine User** per `(machine, PIN)`. Fan-out at create is N inserts. Later lockstep is opt-in per action.

---

## 5. How to verify (manual)

1. `bench --site saral.localhost migrate` and clear cache.
2. Workspace: Add Machine, Machines, Machine Users, Punch Log, Device Roll, Settings. No Employee/Leave/Mirror.
3. **Pull wizard:** enter a reachable ZK IP → probe shows serial/model → save → users and punches appear.
4. **Push wizard:** curl `/iclock/cdata?SN=TEST-003` → row appears → Register → further uploads store for that machine.
5. **Create user** on one or more machines; pull device shows the PIN; push device collects `DATA UPDATE USERINFO`.
6. **Device Roll:** pick machine and dates; PINs with punches = Yes.
7. Edit a Machine User name; inbound USERINFO from the device must not revert it.

```bash
bench --site saral.localhost run-tests --app timebridge
```

---

## 6. Locked decisions (grilling)

| # | Decision |
|---|----------|
| Q1 | Product is device I/O. Attendance as HR lives elsewhere. |
| Q2 | Roll sheet is diagnostic punched Yes/No, not working-day Absent. |
| Q3 | Kill HR masters, Attendance DocType, HR reports, Device Mirror/templates. Keep JPEG harvest. |
| Q4 | Wizard: operator chooses Push or Pull. |
| Q5 | Desk owns users; device enrolments sync as flags; device-created PINs become Machine Users. |
| Q6 | Fan-out: pick machines; later apply-to-same-PIN is optional. |
| Q7 | Photos: harvest only. |
| Q8 | Greenfield branch; no compatibility migrate for old HR data beyond deleting DocTypes. |

---

## 7. Explicit non-goals

- Mapping to ERPNext HR Employee.
- Storing or pushing fingerprint/face templates.
- Uploading JPEGs onto the terminal.
- Deriving In/Out, hours, late, half-day, weekly-off.
- Auto-polling pull devices.
- Restoring a person onto a backup machine.

---

## 8. Review checklist

- [x] Problem matches grilling (device I/O + wizard + roll + user write)
- [x] Spec 002 discontinued in the programme index
- [ ] Implementation phases B–F complete
- [ ] Tests green on saral.localhost
