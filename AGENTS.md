## What This App Does

TimeBridge is a Frappe custom app that connects biometric attendance devices (ZKTeco, eSSL, and similar) to Frappe. It is **device I/O**: machines, enrolled PINs, punch logs, and JPEG harvest when firmware allows. It is not an HRIS. Attendance as HR lives elsewhere.

Current product cut: [spec/003-device-io.md](spec/003-device-io.md).

### Target devices

Two transports, both implemented:

1. **TCP pull via `pyzk`.** Frappe dials the device on port 4370. Refer to https://github.com/fananimi/pyzk
2. **ADMS push.** The device dials out and POSTs to `/iclock/…`; we never connect to it. Refer to `spec/ZKteco Push SDK.pdf`



## IMPORTANT

Always load and use frappe-app-dev skills.

When adding or changing **Desk Workspace** links, shortcuts, or cards (DocType / Page / Report on the app workspace), also load and follow **frappe-workspace** (`.agents/skills/frappe-workspace/SKILL.md`). Editing workspace JSON alone does not update existing sites — sync via patch + `after_install`.

When creating or fixing **Desk Pages** (filters, Link autocomplete, breadcrumbs, double-click handlers, mobile layout), also load and follow **desk-page-ui** (`.agents/skills/desk-page-ui/SKILL.md`).

## Development Details

Unless mentioned, the site is saral.localhost with administrator/admin credentials.

## Planning / Spec-ing

Use Tracer bullets comes from the Pragmatic Programmer. When building systems, you want to write code that gets you feedback as quickly as possible. Tracer bullets are small slices of functionality that go through all layers of the system, allowing you to test and validate your approach early. This helps in identifying potential issues and ensures that the overall architecture is sound before investing significant time in development.

## Implementation Guidelines

* Create a new branch before working on a new feature/spec (branch name patterns: feat/, fix/, just like conventional commit pre-fixes)
* Never commit directly to `develop` — open a PR against `develop`
* Reconcile the spec and log the progress after each phase of development
* Commit after each meaningful phase
* Commit the spec before the development commits
* Use comments only when necessary to explain "why?" not "how?", how must be clear from the code itself

## Frontend / Backend Sync

* Whenever a new field is added to a backend DocType that is surfaced in the frontend (e.g. settings panels), it must also be handled in the corresponding frontend component so the two stay in sync. This is a convention/reminder only — there is no automatic syncing mechanism; the frontend enumerates fields explicitly.

## Regression tests

* When we fix a bug, add at the very least a Unit test, and verify before/after by temp revert of fix to make sure the test tests what is intended
* For bigger features/workflows, e2e playwright tests are a must.
* Local: `bench --site saral.localhost run-tests --app saral_hr` (prefer a dedicated test site when available)
* CI: GitHub Actions workflow `.github/workflows/ci.yml` runs on every PR to `develop`

## Pull Requests

* Raise PR always against the develop branch
* Wait for CI (`CI / Success`) to pass before merging
* Keep pull request descriptions stupid simple
* Some formats:
    1. h2 Problem (1-2 sentences), h2 Solution: good for bugs, etc.
    2. h2 Why? h2 What? h2 How?: good for new features and enhancements

## Branch protection

* `develop` is protected: PRs required, CI must pass, no direct pushes
* Use `feat/` or `fix/` branches for all work