# History Tab Redesign

**Date:** 2026-04-29
**Status:** Approved

## Problem

The current History tab has three issues:
1. No date range filter — hardcoded `SINCE 30 days ago`
2. Entity IDs (`L_xxxx`) shown instead of human-readable names
3. No tree for filtering by entity — full flat list of all changes across the org
4. Changes shown as a table row with a "View diff" modal link — no inline before/after view

## Layout

Two-panel layout mirroring the Overview tab:

```
┌─────────────────────────────────────────────────────┐
│  Config App → History                               │
├──────────────┬──────────────────────────────────────┤
│ Date range   │  <entity name> · N changes · date range│
│  From [    ] │                                      │
│  To   [    ] │  ▼ firewall_rules  ~ 1 changed + 1 added  Apr 28 │
│  [7d][30d][90d]│  ┌──────────┬──────────┐          │
│              │  │  Before   │  After   │          │
│ Changed entities│  │  ...JSON  │  ...JSON │          │
│ ▾ Main Office│  └──────────┴──────────┘          │
│   ● MX-Firewall (3)│                              │
│   ○ AP-Lobby (1)│  ▶ vpn_settings  ~ 2 changed   Apr 27 │
│ ▾ Branch North│  ▶ switch_ports  🔒 1 secret     Apr 15 │
│   ○ SW-Floor2 (2)│                               │
└──────────────┴──────────────────────────────────────┘
```

Left panel width: 220px (same as Overview tab ConfigTree).

## Left Panel — Date Range + Changes-Only Tree

### Date Range
- From / To date inputs (HTML `<input type="date">`)
- Shortcut buttons: **7d**, **30d** (default, active on load), **90d**
- Changing the date range re-queries both the tree and the diff tiles

### Changes-Only Tree
Query (runs whenever date range changes):
```sql
SELECT count(*) FROM MerakiConfigChange
WHERE org_id = '{orgId}'
FACET entity_type, entity_id, entity_name, network_id
SINCE {from} UNTIL {to} LIMIT MAX
```

Tree structure built from results:
- Group devices/SSIDs by `network_id` → show as `▾ <network name>` parent nodes
- Show devices/SSIDs as leaf items with a `(N)` change count badge
- Sites/devices with zero changes in the range are **not shown**
- Clicking a leaf selects it; the right panel updates to show that entity's changes
- If nothing is selected, show all changes for the org across the date range

**Network parent names:** A network may not appear in the change events if only its devices changed (not the network itself). Resolve network names with a second query:
```sql
SELECT latest(entity_name) FROM MerakiConfigSnapshot
WHERE entity_type = 'network' AND org_id = '{orgId}'
FACET entity_id SINCE 30 days ago LIMIT MAX
```
Use this as a name lookup when labelling parent nodes. Fall back to the raw `network_id` if not found.

Entity leaf names come from `entity_name` on the change event. Fall back to `entity_id` if empty.

## Right Panel — Diff Tiles

### Query
```sql
SELECT config_area, change_summary, detected_at, diff_json, from_payload, to_payload
FROM MerakiConfigChange
WHERE org_id = '{orgId}' [AND entity_id = '{entityId}']
SINCE {from} UNTIL {to}
ORDER BY detected_at DESC LIMIT 100
```

### Tile Design
Each `MerakiConfigChange` event becomes one expandable tile:

**Collapsed state (header only):**
- `▶` chevron + `config_area` in monospace
- Colored badges summarising the change (e.g. `~ 2 changed`, `+ 1 added`, `🔒 1 secret rotated`)
- `detected_at` timestamp right-aligned

**Expanded state:**
- `▼` chevron, same header
- Two columns below: **Before** (left) | **After** (right)
- Each column shows syntax-highlighted JSON from `from_payload` / `to_payload`
- Changed lines highlighted with a subtle background tint (orange = changed, green = added, red = removed) — derived from `diff_json`
- `max-height: 300px` with scroll on each column independently

### Backend Change Required
`MerakiConfigChange` events currently do not include `from_payload` / `to_payload`. Add both fields to `build_change_events()` in `nr_ingest/config_ingest.py`, each truncated to 4000 chars (same limit as `config_json` on snapshots).

## Files Changed

| File | Change |
|------|--------|
| `nr_ingest/config_ingest.py` | Add `from_payload` and `to_payload` to change events |
| `nr_ingest/tests/test_config_ingest.py` | Update tests to assert new fields present |
| `nerdpack/nerdlets/config-app/components/ChangeHistory.js` | Full redesign per spec |

`index.js` unchanged — `ChangeHistory` already receives `accountId` and `orgId`; entity selection state moves inside the component.

## Out of Scope
- Compare tab changes (separate effort)
- Pagination beyond 100 results
- Highlighting specific diff lines inside the JSON (colour tinting is sufficient)
