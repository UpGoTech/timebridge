---
name: frappe-workspace
description: >-
  Keeps Frappe Desk Workspaces in sync with app module JSON on install, migrate,
  and uninstall. Use whenever adding or changing workspace links, shortcuts,
  number cards, charts, or card breaks; when a new DocType/Page/Report does not
  appear on the workspace after migrate; or when shipping Desk navigation for a
  Frappe app. Load alongside frappe-app-dev.
---

# Frappe Workspace Sync

## The mistake to avoid

Editing `{app}/{module}/workspace/{name}/{name}.json` is **not enough** for sites that already have the workspace in the database. Frappe re-imports workspace JSON on `bench migrate` only when the file hash or timestamp beats the DB row. Existing sites keep the old links.

**JSON alone works on a brand-new `bench install-app`.** Every other site needs an explicit sync.

## Source of truth

| Artifact | Path (TimeBridge example) |
|----------|---------------------------|
| Workspace JSON | `timebridge/timebridge/workspace/timebridge/timebridge.json` |
| Sync helper | `timebridge/timebridge/services/workspace_sync.py` |

The JSON defines the **full** public workspace: `links`, `shortcuts`, `number_cards`, `charts`, `content`, `link_count` on Card Break rows.

## Checklist — do all of these

Copy and complete whenever Desk navigation changes:

```
Workspace change:
- [ ] Edit workspace JSON (links, link_count on Card Break, shortcuts, etc.)
- [ ] Bump JSON `modified` to a new timestamp
- [ ] Add post_model_sync patch → sync_app_workspaces(force=True)
      OR ensure_workspace_link() for a single additive link
- [ ] Wire after_install → sync_app_workspaces(force=True)  (fresh install-app)
- [ ] before_uninstall removes app workspaces (or rely on Frappe module delete)
- [ ] bench --site <site> migrate
- [ ] Verify link in DB: workspace_link_exists("TimeBridge", "<DocType>")
- [ ] Hard-refresh Desk → open workspace → link visible
```

## Implementation patterns (TimeBridge)

### Fresh install

`hooks.py`:

```python
after_install = "timebridge.install.after_install"
```

`install.py`:

```python
def after_install():
    from timebridge.timebridge.services.workspace_sync import sync_app_workspaces
    sync_app_workspaces(force=True)
```

### Existing sites (patch)

`patches.txt` → `[post_model_sync]`:

```
timebridge.patches.v1_0.sync_timebridge_workspace
```

```python
from timebridge.timebridge.services.workspace_sync import sync_app_workspaces

def execute():
    sync_app_workspaces(force=True)
```

Prefer **full JSON reimport** (`sync_app_workspaces`) when several links or counts change. Use `ensure_workspace_link()` only for a single additive link.

### Uninstall

Frappe `remove_app` deletes `Workspace` rows whose `module` matches the app's Module Def. TimeBridge also lists public workspaces in `uninstall.before_uninstall` so the Desk sidebar matches a site with no app installed.

Do **not** leave orphan workspace links to DocTypes that only exist in this app.

## Card Break `link_count`

Each Card Break row has `link_count` = number of Link rows **immediately following** it before the next Card Break. When adding a link to the Data card, increment that card's `link_count` in JSON **and** keep link order matching the UI.

Example (Data card, four links):

```json
{ "label": "Data", "link_count": 4, "type": "Card Break" }
```

## Verify

```bash
bench --site <site> migrate
bench --site <site> run-tests --app timebridge
```

Console check:

```python
from timebridge.timebridge.services.workspace_sync import workspace_link_exists
workspace_link_exists("TimeBridge", "TimeBridge Machine Log")  # True
```

Desk: Workspace → TimeBridge → link under the expected card.

## When to load this skill

- New DocType, Page, Report, or workspace shortcut
- User says "not on workspace" / "missing from sidebar"
- Any PR that touches `workspace/**/*.json`

Always load **frappe-app-dev** as well.
