# Spec 001 — ADMS Device Discovery & Registration

| Field | Value |
|-------|-------|
| **Spec ID** | `001` |
| **Branch** | `feat/adms-device-discovery` |
| **Status** | **Merged** — PR #3 into `develop` (2026-08-29) |
| **Authority** | [`ZKteco Push SDK.pdf`](./ZKteco%20Push%20SDK.pdf) for protocol; this doc for product behaviour |
| **Created** | 2026-08-27 |
| **Last updated** | 2026-08-29 |
| **Programme tracker** | [spec/README.md](./README.md) — overall progress across all specs |

---

## 1. Why?

ADMS / PUSH devices never accept inbound connections. The server only learns a device exists when the device dials out — handshake (`GET /iclock/cdata`), heartbeat (`GET /iclock/getrequest`), upload, ping, etc.

Before this work, unknown serials were mostly invisible:

| Inbound call | Previous behaviour |
|--------------|--------------------|
| Handshake / heartbeat / ping | Answered `OK`, **no durable trace** |
| POST upload / photo from unknown SN | Error Log only |

Operators had no Desk surface to answer: *“Is any unregistered device talking to us right now?”* Registration required creating a **TimeBridge Machine** with the serial already known.

---

## 2. What? (goal of this tracer bullet)

1. Capture **every** inbound `/iclock/…` request whose `SN` does not match a registered machine.
2. Show those signals live on a **Device Registration** Desk page.
3. Allow **Register** (create ADMS machine) or **Dismiss** from that page.
4. Keep supporting fixes that unblocked testing (pyzk install, portable web port, machine delete vs pending link).

Out of scope for this tracer (see §7): realtime WebSocket push, roles beyond System Manager, auto-expiry policies, e2e Playwright, production hardening of unauthenticated ADMS.

---

## 3. Progress tracker

Legend: `[x]` done · `[~]` partial / needs review · `[ ]` not started

### Phase A — Capture unknown signals

| # | Item | Status | Notes |
|---|------|--------|-------|
| A1 | Record unknown SN in ADMS renderer (before handler) | `[x]` | `adms/renderer.py` → `pending.record_signal` |
| A2 | Upsert by serial (hit_count, last_seen, signal_type) | `[x]` | `adms/pending.py` |
| A3 | Classify Handshake / Heartbeat / Upload / Ping / Photo / Command Result | `[x]` | |
| A4 | Capture remote IP (incl. `X-Forwarded-For`) | `[x]` | Best-effort; may be NAT |
| A5 | Do not store punches/users for unknown SN (unchanged) | `[x]` | Still refuse data; only discover |
| A6 | Unit tests for pending recorder | `[x]` | `adms/test_pending.py` |

### Phase B — Desk: Device Registration page

| # | Item | Status | Notes |
|---|------|--------|-------|
| B1 | Page `device-registration` + whitelist APIs | `[x]` | list / dismiss / register |
| B2 | Live table (serial, signal, IP, first/last seen, hits) | `[x]` | Auto-refresh 10s |
| B3 | Register dialog → TimeBridge Machine (`sdk_type=ADMS`) | `[x]` | Pre-fills serial + suggested IP |
| B4 | Dismiss → status Dismissed; reopens on new contact | `[x]` | |
| B5 | Workspace link + shortcut | `[x]` | `patches/v1_0/add_device_registration_workspace_link.py` |
| B6 | Desk-page-ui polish (breadcrumbs, no full-bleed, mobile) | `[x]` | Core patterns applied; full checklist deferred |
| B7 | Playwright e2e | `[ ]` | Deferred until product sign-off |

### Phase C — Lifecycle & links

| # | Item | Status | Notes |
|---|------|--------|-------|
| C1 | Pending row → Registered after machine create | `[x]` | Sets `registered_machine` |
| C2 | Deleting machine unlinks pending row / reopens Pending | `[x]` | `on_trash` + `unlink_machine` |
| C3 | `ignore_links_on_delete` for Pending Device Signal | `[x]` | Avoids LinkExistsError |
| C4 | Auto-close pending when serial later matches a machine | `[x]` | `_mark_registered_if_pending` |

### Phase D — Supporting fixes (same branch)

| # | Item | Status | Notes |
|---|------|--------|-------|
| D1 | Lazy-import `zk` so ADMS APIs load without pyzk crash | `[x]` | `pyzk_connector` / `connection` / `api` |
| D2 | Ensure `pyzk` on app install (`before_install` + pyproject) | `[x]` | `install.py`, README |
| D3 | Remove hardcoded port `8000` health probe | `[x]` | `adms/server.web_port()` from bench config / Host |
| D4 | Health UI advice portable across WSL / Ubuntu / Docker | `[x]` | Shows configured ADMS server port |
| D5 | Unit test for `web_port` | `[x]` | `adms/test_server.py` (asserts current site port) |

### Phase E — Spec / docs / merge

| # | Item | Status | Notes |
|---|------|--------|-------|
| E1 | Numbered spec in `spec/` with tracker | `[x]` | This file |
| E2 | Product review of open questions (§6) | `[x]` | Shipped with spec recommendations |
| E3 | Commit phases + PR to `develop` | `[x]` | PR #3 |
| E4 | CI green + merge | `[x]` | Merged 2026-08-29 |

**Overall:** Tracer bullet **shipped** — branch closed.

---

## 4. How it works (as built)

```
Device ──HTTP──► /iclock/{cdata|getrequest|…}?SN=…
                      │
                      ▼
              ADMSRenderer.render
                      │
          SN matches TimeBridge Machine?
               │                │
              Yes              No
               │                │
               ▼                ▼
         existing ADMS    pending.record_signal
         handlers         (upsert Pending Device Signal)
               │                │
               └────── OK / handshake text ──► Device

Desk: /app/device-registration
  → list Pending rows
  → Register → insert TimeBridge Machine (ADMS) + mark Registered
  → Dismiss → status Dismissed (reactivates if device talks again)
```

### Data model — `TimeBridge Pending Device Signal`

| Field | Role |
|-------|------|
| `serial_number` | Unique name key (device `SN`) |
| `status` | `Pending` / `Registered` / `Dismissed` |
| `signal_type` | Handshake, Heartbeat, Upload, … |
| `endpoint` / `method` | Last `/iclock/…` contact |
| `remote_ip` | Last client IP |
| `first_seen` / `last_seen` / `hit_count` | Activity |
| `query_args` | Last query string (truncated JSON) |
| `registered_machine` | Link after Register |

### Key paths

| Path | Role |
|------|------|
| `timebridge/timebridge/adms/renderer.py` | Capture hook |
| `timebridge/timebridge/adms/pending.py` | Upsert / list / register / dismiss / unlink |
| `timebridge/timebridge/adms/server.py` | Portable web port for device config / health |
| `timebridge/timebridge/doctype/timebridge_pending_device_signal/` | DocType |
| `timebridge/timebridge/page/device_registration/` | Desk page + APIs |
| `timebridge/install.py` | Ensure `pyzk` on install |
| `timebridge/hooks.py` | `before_install`, `ignore_links_on_delete` |

---

## 5. How to verify (manual)

1. Migrate / clear cache; open `/app/device-registration`.
2. Simulate unregistered device (adjust host/port to your bench):

```bash
curl "http://<host>:<port>/iclock/cdata?SN=TEST-DEVICE-001&options=all"
curl "http://<host>:<port>/iclock/getrequest?SN=TEST-DEVICE-001"
```

3. Page should show serial with Handshake then Heartbeat; hit count increases.
4. **Register** → Machine form opens with `sdk_type=ADMS` and that serial.
5. Further curls for that SN no longer appear as Pending.
6. Delete the machine → pending row unlinks / returns to Pending (or can be recreated on next contact).
7. Machine form connection health must **not** claim “not listening on 8000”; it should show this bench’s `web_port`.

Unit tests:

```bash
bench --site saral.localhost run-tests --app timebridge --module timebridge.timebridge.adms.test_pending
bench --site saral.localhost run-tests --app timebridge --module timebridge.timebridge.adms.test_server
bench --site saral.localhost run-tests --app timebridge --module timebridge.timebridge.test_install
```

---

## 6. Open questions (need your call)

| # | Question | Decision |
|---|---|----------|
| Q1 | **IP on Register** | Default from captured `remote_ip`, editable (implemented) |
| Q2 | **Dismissed / stale signals** | Reopen on contact; no auto-expiry in v1 |
| Q3 | **Realtime** | Keep 10s poll |
| Q4 | **Permissions** | System Manager only |
| Q5 | **Pending DocType visibility** | Page primary; DocType list for support |
| Q6 | **Merge packaging** | One PR (discovery + pyzk/port fixes) |

---

## 7. Suggested further course

After you review this spec:

1. **Decide Q1–Q6** (annotate or reply in chat).
2. **Apply any agreed tweaks** (small code/spec updates).
3. **Commit in phases** (per AGENTS.md):
   - Commit 1: this spec (`spec/001-…`)
   - Commit 2: pending DocType + capture + page
   - Commit 3: supporting fixes (pyzk, web_port, unlink)
4. **Open PR → `develop`**; wait for CI.
5. **Post-merge follow-ups** (new specs if needed):
   - `002` — Device Registration UX polish / roles / expiry
   - Playwright e2e for register flow
   - Optional realtime updates

---

## 8. Explicit non-goals (this branch)

- Changing PUSH protocol semantics (still governed by Push SDK PDF).
- Auto-creating machines without operator confirmation.
- Storing ATTLOG/USERINFO for unknown serials.
- Replacing manual PyZK machine setup (pull path unchanged except pyzk install reliability).

---

## 9. Review checklist (for you)

- [x] Problem statement matches what you wanted
- [x] Tracer scope is enough to ship as v1 discovery
- [x] Answers to Q1–Q6 (shipped as recommended)
- [x] OK to proceed with commits + PR as in §7
- [x] Any rename / field / copy changes before merge

**Shipped** — merged via PR #3. Post-merge follow-ups: Playwright e2e (B7), optional realtime.
