# NCM Phase 2 — Diff Engine & Change Timeline

**Status:** Design approved  
**Depends on:** Phase 1 (shipped 2026-04-22)  
**Roadmap doc:** [network-config-management-phases.md](network-config-management-phases.md)

---

## Goal

Make Phase 1's collected config data actionable: let users see *what changed* across their org, *when*, and *by whom* — at any scope from org-wide down to a single device config area.

---

## Cross-cutting constraints (inherited from roadmap)

- Observability only — no writes to Meraki APIs.
- Change-log-driven where possible; full polling only for baseline and anti-drift sweeps.
- Content-addressed storage (SHA-256). Phase 2 only reads blobs, never writes new ones.
- Secret redaction: `*_hash` companion fields emit a "Secret changed" marker, never a value diff.

---

## Phase 1 prerequisite change

The existing `ConfigTree.tsx` shows Networks at the root with Devices nested beneath them. Phase 2 requires the tree to be restructured as:

```
Acme Corp (org)
  └─ HQ Network (network)
       ├─ MX84
       └─ MS220
  └─ Retail-East (network)
       ├─ MX84
       └─ MR46
```

This eliminates the need for a separate "Org Changes" tab. Clicking any level scopes the diff to that level and all its children. This tree restructure is a Phase 2 prerequisite and should be the first task in the implementation plan.

---

## Architecture

### 1. DiffEngine — `server/config_collector/diff_engine.py`

A single Python module with one public function:

```python
def compute_diff(blob_a: dict, blob_b: dict) -> DiffResult
```

**Payload shape detection:**
- If the top-level value is a `list` → array diff mode
- If the top-level value is a `dict` → object diff mode

**Object diff mode:**
- Walk all keys in the union of both objects
- Emit only changed, added, or removed keys
- Recurse into nested dicts
- Skip keys whose values are identical (SHA-256 equality check before deep compare)
- For `*_hash` fields: if value differs, emit `secret_changed` marker instead of before/after values

**Array diff mode:**
- Match rows across snapshots using a configurable identity key registry:

  | config_area | identity key |
  |---|---|
  | appliance_vlans | `id` |
  | appliance_firewall_l3 | array position (rules are order-sensitive) |
  | wireless_ssids | `number` |
  | switch_device_ports | `portId` |
  | Any unregistered area | first field ending in `Id`, `id`, or `number`; fallback to position |

- Emit rows as `row_added`, `row_removed`, or `row_changed` (with inline field-level changes)
- Unchanged rows are counted but not included in output

**DiffResult shape:**
```python
@dataclass
class DiffResult:
    shape: Literal["object", "array"]
    changes: list[DiffChange]      # only changed items
    unchanged_count: int           # hidden items count, for UI note
```

```python
DiffChange = Union[
    FieldChanged(key, before, after),
    FieldAdded(key, value),
    FieldRemoved(key, value),
    SecretChanged(key),            # *_hash field differed
    RowAdded(identity, row),
    RowRemoved(identity, row),
    RowChanged(identity, field_changes: list[DiffChange]),
]
```

**Reuse across phases:** This module is the shared diff primitive for Phase 4 (drift vs golden baseline), Phase 5 (compliance field-level evaluation), and Phase 6 (multi-site comparison). It has no dependencies on HTTP or SQLite — pure data transformation.

---

### 2. Org Diff Endpoint — `GET /api/config/diff/org`

**Parameters:** `org_id`, `from_ts` (ISO-8601), `to_ts` (ISO-8601, default now)

**Behaviour:**
1. For each `(entity_type, entity_id, config_area, sub_key)` in the org, fetch the latest observation before `from_ts` and the latest observation before `to_ts`.
2. If both observations exist and their hashes differ, run `compute_diff(blob_a, blob_b)`.
3. If only `to_ts` observation exists (entity was created in the window), treat as fully added.
4. If only `from_ts` observation exists (entity removed in window), treat as fully removed.
5. Return results grouped by `(network_id, entity_type, entity_id, config_area)`.

**Response envelope:**
```json
{
  "from_ts": "2026-04-15T00:00:00Z",
  "to_ts": "2026-04-23T00:00:00Z",
  "total_entities_checked": 47,
  "changed_count": 8,
  "results": [
    {
      "network_id": "N_abc",
      "network_name": "Retail-East",
      "entity_type": "network",
      "entity_id": "N_abc",
      "config_area": "appliance_vlans",
      "observed_at": "2026-04-19T09:14:00Z",
      "admin_email": "bob@acme.com",
      "diff": { "shape": "array", "changes": [...], "unchanged_count": 5 }
    }
  ]
}
```

**Performance:** For a 30-network org with ~47 entities, this query touches ~47 pairs of blob lookups plus `compute_diff` calls. Estimated wall-clock: 3–12 seconds depending on payload sizes. The endpoint streams a progress hint in the response headers (`X-Estimated-Seconds`) so the UI can display an accurate countdown.

---

### 2a. Store helper — `get_observations_in_window()`

Added to `server/config_collector/store.py`. Given `(org_id, from_ts, to_ts)`, returns for every `(entity_type, entity_id, config_area, sub_key)` in the org the two observation rows needed for the diff: the latest observation with `observed_at <= from_ts` and the latest with `observed_at <= to_ts`. Returns only pairs where at least one observation exists. This is a single SQL query using window functions to avoid N+1 blob fetches at the route layer.

---

### 3. Entity Timeline Endpoint — `GET /api/config/entities/{type}/{id}/timeline`

Returns a chronological list of change events for a single entity, merging two signals:

- **Observation-detected changes** — from `config_observations` where `source_event IN ('change_log', 'anti_drift_discrepancy', 'manual_refresh')` and hash differs from prior observation
- **Meraki audit events** — from `config_change_events` joined on `change_event_id`

Each entry indicates whether a structural diff is available (i.e., we have a linked observation pair). Entries without a linked observation show admin name and timestamp but no diff.

This endpoint is used by the History tab when scoped to a single device (optional optimisation over re-filtering the org diff result).

---

## UI Changes

### Phase 1 tree restructure (prerequisite)

- `ConfigTree.tsx`: add org as the root node; networks become first-level children; devices remain second-level children.
- The "Devices / Org Changes" toggle in `CollectionStatusBar.tsx` is removed.

### Global time range selector

Added to `CollectionStatusBar.tsx`, replaces the per-node range picker:

- Two selectors: **From** (list of baseline timestamps + "Last 7 days / 30 days") and **To** (default: Now)
- A **Compare** button fires `GET /api/config/diff/org`
- While loading: animated progress bar + countdown timer (seeded from `X-Estimated-Seconds` header)
- Result is cached in React state; tree navigation filters client-side, no re-fetch

### ConfigTree updates (post-diff load)

After a diff result loads:
- Tree collapses to show only entities with at least one change in the selected window
- Each node shows a change count badge
- A footer note: "N networks · M devices with no changes hidden"
- Unchanged entities are not removed from the data model — a "Show all" text link at the bottom of the sidebar restores the full tree

### New component: `DiffViewer.tsx`

Renders a `DiffResult` inline within a tile. Two modes driven by `shape`:

**Object mode (key-value diff):**
- Three-column grid: field name | before value | after value
- Added fields: green row, no "before"
- Removed fields: red row, no "after"
- Secret changed: purple italic marker, no values
- Footer: "N fields unchanged · hidden"

**Array mode (table diff):**
- `row_added`: full green row showing key fields
- `row_removed`: full red row
- `row_changed`: amber row, expands inline to show field-level changes
- Footer: "N rows unchanged · hidden"

### History tab behaviour

- Scoped to whatever node is selected in the tree (org / network / device)
- Entries grouped by entity, then config area, sorted newest-first
- Each tile: area name + change summary in header, `DiffViewer` inline below
- Entities/areas with zero changes do not appear
- Admin email and timestamp shown on each tile when available from linked Meraki audit event

---

## Edge cases

**SSID-enabled edge case:** When `enabled` flips from `false` to `true`, Phase 1 reactively pulls sub-endpoints for the first time. The diff engine treats this as the full SSID config being added (all fields new), displayed as a `row_added` entry. No synthetic empty baseline is created. The tile header reads "SSID N — first config captured (enabled)".

**No prior observation:** If `from_ts` is before the baseline was taken, some entities have no `from_ts` observation. These are shown as "First captured" entries with no before-state, not as diffs.

**Large orgs:** The org diff endpoint processes entities sequentially to stay within Meraki's 5 req/sec rate limit on blob fetches. For orgs >200 entities, the loading indicator will reflect a longer estimated time (up to ~45 seconds).

**Meraki change event without matching observation:** Shown in the timeline with admin name and timestamp but a "no snapshot captured" note instead of a diff link. This happens when a change occurred between collection windows.

---

## Design decisions made during spec

**General diff engine replaces "rich renderers":** The original roadmap called for purpose-built renderers for VLANs, firewall rules, SSIDs, and switch ports. During design it was recognised that 98 of 104 collected config areas are flat objects and the remaining ~6 array areas share the same table-diff pattern. A single general-purpose DiffEngine covers all 104 areas without per-area code. The identity key registry handles the array cases. The four originally named areas are not special-cased — they fall naturally out of the general engine.

**Entry points are co-primary:** Both the org-level history view (clicking the org root) and the device-level history view (clicking a device in the tree) are first-class entry points. The org-level view is considered slightly more primary since it gives the broadest picture and is the natural landing state after a diff loads.

**Default state on first Compare:** After a diff result loads, the org root node is auto-selected, showing all changes across the org grouped by network and device. The user can then drill down by clicking any network or device node.

**Default time range:** On first load (before the user has run a Compare), the From selector defaults to the most recent baseline timestamp. If no baseline exists, it defaults to "Last 30 days."

**Empty state:** If the selected time range produces zero changes, the tree shows only the org root node with a "No changes in this window" message in the right panel. The time range selectors remain active so the user can widen the range.

**Overview tab:** The existing Overview tab on each entity (showing config area cards with JSON payloads, introduced in Phase 1) is unchanged. History is a new second tab added alongside it.

---

## What is NOT in Phase 2

- Pinning golden baselines (Phase 4)
- Compliance rules (Phase 5)
- Multi-site comparison (Phase 6)
- Export/revert bundles (Phase 7)
- Topology change markers (Phase 3)
- The DiffEngine identity key registry covers the most common array areas; additions for new areas are a one-line registry update, not a new renderer

---

## Files to create / modify

| File | Action |
|---|---|
| `server/config_collector/diff_engine.py` | Create — DiffEngine + DiffResult types |
| `server/routes/config.py` | Modify — add `/diff/org` and `/entities/{type}/{id}/timeline` endpoints |
| `server/config_collector/store.py` | Modify — add `get_observations_in_window()` helper |
| `ui/src/components/ConfigBrowser/ConfigTree.tsx` | Modify — restructure to Org → Networks → Devices |
| `ui/src/components/ConfigBrowser/CollectionStatusBar.tsx` | Modify — add global time range selector, remove toggle |
| `ui/src/components/ConfigBrowser/DiffViewer.tsx` | Create — renders DiffResult |
| `ui/src/components/ConfigBrowser/OrgDiffPanel.tsx` | Create — manages org diff fetch, loading state, caching |
| `ui/src/api/config.ts` | Modify — add `fetchOrgDiff()` and `fetchEntityTimeline()` |
| `ui/src/hooks/useOrgDiff.ts` | Create — wraps fetch, loading state, caching |
