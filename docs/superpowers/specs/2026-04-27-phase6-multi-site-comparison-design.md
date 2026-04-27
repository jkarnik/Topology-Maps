# Phase 6 — Multi-Site & Template Comparison: Design Spec

**Date:** 2026-04-27
**Status:** Draft
**Depends on:** Phase 1 (config collection), Phase 2 (diff engine)

---

## Goal

Make "how does Store 42 differ from Store 7?" a first-class question. Let operators save known-good network configs as templates, score their entire fleet against those templates, and see at a glance which networks are missing which config areas.

---

## Scope

Four features, all read-only (no writes to Meraki):

1. **Side-by-side network comparison** — pick any two networks, see field-level diffs grouped by config area
2. **Coverage dashboard** — see which config areas are present across networks and devices
3. **Template extraction** — promote any network's current config as a named, reusable template
4. **Template scoring** — rank every network by deviation from a chosen template

---

## Key Decisions

| Decision | Choice | Reason |
|---|---|---|
| UI home | New "Compare" tab in ConfigBrowser alongside Overview / History | Keeps all config tooling in one place |
| Sub-navigation | Pill segmented control: Compare Networks · Coverage · Templates | Compact, no extra sidebar |
| Network picker | Two dropdowns + Compare button | Simple and explicit |
| Template scope | Bundle of multiple config areas | One template captures a full network config profile |
| Template creation | Promote a network (one-click snapshot) | Simplest flow; avoids manual curation |
| Coverage drill-down | Network level + device level | Operators need both granularities |
| Architecture | Copy-by-reference (blob hash), on-demand scoring | Templates durable; scoring fast enough at current scale |
| Compare results layout | Collapsible sections per config area with diff count badge | Scannable for large orgs |
| Coverage layout | Master/detail (area list left, detail panel right) | More horizontal room for the missing-networks list |
| Templates layout | Template list left + scoring panel right | Mirrors Coverage layout for consistency |

---

## Data Model

Two new SQLite tables, added to the existing schema in `server/config_collector/store.py`.

### `config_templates`

One row per saved template.

```sql
CREATE TABLE config_templates (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id               TEXT NOT NULL,
    name                 TEXT NOT NULL,
    source_network_id    TEXT NOT NULL,
    source_network_name  TEXT,
    created_at           TEXT NOT NULL
);
```

### `config_template_areas`

One row per config area captured in the template. References the existing `config_blobs` table by hash — no content duplication.

```sql
CREATE TABLE config_template_areas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id  INTEGER NOT NULL REFERENCES config_templates(id) ON DELETE CASCADE,
    config_area  TEXT NOT NULL,
    sub_key      TEXT,
    blob_hash    TEXT NOT NULL REFERENCES config_blobs(hash_hex)
);
```

**How promotion works:** When a network is promoted, the server reads all current `config_observations` for that network, grabs each `blob_hash`, and writes rows into `config_template_areas`. The blobs already exist in `config_blobs` — nothing is duplicated. Promoting the same network twice creates two independent snapshots; changing or deleting one does not affect the other.

---

## Backend API

All endpoints are added to the existing router in `server/routes/config.py`. Store functions go into `server/config_collector/store.py` following existing patterns.

### Templates CRUD

```
GET  /api/config/templates?org_id={org_id}
```
Returns all templates for the org. Each item includes `id`, `name`, `source_network_id`, `source_network_name`, `created_at`, and `areas` (list of `{config_area, sub_key}`).

```
POST /api/config/templates
Body: { org_id, name, network_id }
```
Promotes a network. Reads all latest `config_observations` for `network_id`, writes a `config_templates` row and one `config_template_areas` row per config area. Returns the created template.

```
DELETE /api/config/templates/{template_id}
```
Deletes the template and its areas (cascade). Does not touch `config_blobs`.

### Network Comparison

```
GET /api/config/compare/networks
    ?org_id={org_id}&network_a={id}&network_b={id}
```
Fetches the latest observation for every config area in both networks. For each config area present in either network, calls `compute_diff(blob_a, blob_b)` from the existing `diff_engine`. Returns:
```json
{
  "network_a": { "id": "...", "name": "..." },
  "network_b": { "id": "...", "name": "..." },
  "areas": [
    {
      "config_area": "wireless.ssids",
      "sub_key": null,
      "status": "differs",
      "diff": { ...DiffResult... }
    }
  ],
  "total_areas": 12,
  "differing_areas": 3,
  "total_changes": 8
}
```
`status` is one of `"differs"`, `"identical"`, `"only_in_a"`, `"only_in_b"`.

### Coverage

```
GET /api/config/coverage?org_id={org_id}
```
Queries `config_observations` grouped by `config_area`. Returns:
```json
{
  "areas": [
    {
      "config_area": "wireless.ssids",
      "network_count": 45,
      "network_total": 50,
      "missing_networks": [{ "id": "...", "name": "..." }],
      "device_breakdown": {
        "{network_id}": {
          "present_devices": [...],
          "missing_devices": [...]
        }
      }
    }
  ]
}
```
`network_total` is the count of distinct network IDs observed in `config_observations` for the org. `device_breakdown` is only populated for config areas that exist at the device level (i.e. `entity_type = "device"`).

### Template Scoring

```
GET /api/config/templates/{template_id}/scores?org_id={org_id}
```
For each network in the org: fetches its latest observations, diffs each config area against the corresponding template area blob using `compute_diff`. Returns:
```json
{
  "template": { "id": 1, "name": "Standard Retail", "area_count": 4 },
  "scores": [
    {
      "network_id": "...",
      "network_name": "Store 7",
      "score_pct": 98,
      "change_count": 1,
      "total_fields": 48,
      "missing_areas": [],
      "area_scores": [{ "config_area": "...", "score_pct": 100, "change_count": 0 }]
    }
  ]
}
```
**Scoring formula:** `score_pct = round((total_fields − change_count) / total_fields * 100)`. If `total_fields` is 0 (empty blob), that area scores 100%. A network missing a config area that exists in the template contributes 0% for that area and the area is listed in `missing_areas`.

---

## Frontend

### New files

| File | Purpose |
|---|---|
| `ui/src/components/ConfigBrowser/CompareTab.tsx` | Top-level Compare tab shell — renders the pill segmented control and routes to sub-views |
| `ui/src/components/ConfigBrowser/CompareNetworksView.tsx` | Sub-view 1: two-dropdown network picker + collapsible diff results |
| `ui/src/components/ConfigBrowser/CoverageView.tsx` | Sub-view 2: master/detail coverage dashboard |
| `ui/src/components/ConfigBrowser/TemplatesView.tsx` | Sub-view 3: template list + scoring panel |
| `ui/src/hooks/useNetworkCompare.ts` | Fetches `/api/config/compare/networks` |
| `ui/src/hooks/useCoverage.ts` | Fetches `/api/config/coverage` |
| `ui/src/hooks/useTemplates.ts` | Fetches, creates, and deletes templates |
| `ui/src/hooks/useTemplateScores.ts` | Fetches `/api/config/templates/{id}/scores` |
| `ui/src/api/compare.ts` | API call wrappers for all Phase 6 endpoints |

New types added to `ui/src/types/config.ts`.

### Modified files

| File | Change |
|---|---|
| `ui/src/components/ConfigBrowser/ConfigBrowser.tsx` | Add "Compare" tab to the existing tab bar; render `<CompareTab>` when active |

### CompareTab layout

```
[ Overview ] [ History ] [ Compare ]   ← existing tab bar

Inside Compare tab:
┌─────────────────────────────────────────────┐
│  ● Compare Networks  ○ Coverage  ○ Templates │  ← pill segmented control
├─────────────────────────────────────────────┤
│  <active sub-view content>                  │
└─────────────────────────────────────────────┘
```

### Sub-view 1 — Compare Networks

- Two `<select>` dropdowns populated from the existing org tree (all networks for the selected org)
- "Compare" button triggers fetch; spinner shown while loading
- Results: one collapsible section per config area, sorted by diff count descending
- Each section header shows area name + diff count badge (red if > 0, green if identical)
- Expanded section shows a two-column field diff using the existing `<DiffViewer>` component
- `status = "only_in_a"` or `"only_in_b"` renders as "Only in [Network Name]" with no diff columns

### Sub-view 2 — Coverage

- Left panel: list of config areas with two counts each (networks, devices where applicable). Color-coded: green = 100%, amber = partial, red = missing entirely for some networks.
- Right panel: appears when an area is selected. Lists missing networks. For device-level areas, each network row is expandable to show missing devices.
- Both panels share the selected org's data from a single `useCoverage` fetch on tab load.

### Sub-view 3 — Templates

- Left panel: list of saved templates (name, source network, area count, created date). "+ Promote a network" button at the bottom.
- Promote flow: modal with a network `<select>` dropdown and a name text input. On submit, calls `POST /api/config/templates` and refreshes the list.
- Right panel: appears when a template is selected. Shows all networks scored against that template, sorted by `score_pct` ascending (worst first). Each row has a colored progress bar (green ≥ 90%, amber ≥ 60%, red < 60%). Clicking a network row expands it to show per-area scores and field-level diffs.
- Delete button on each template card (with confirmation prompt).

---

## Edge Cases & Empty States

| Scenario | Behaviour |
|---|---|
| Two networks are identical | Compare Networks shows "No differences found — these networks have identical config across all areas." |
| One network has config areas the other lacks | Those areas show `status = "only_in_a"` or `"only_in_b"` with no diff columns, just a label. |
| No templates saved yet | Templates sub-view shows "No templates yet — promote a network to get started." with a prominent promote button. |
| Network has no observations at all | Comparison and scoring treat it as having 0 areas; shown as 0% match with all template areas in `missing_areas`. |
| Template area blob deleted (future GC) | Not a concern yet — there is no blob GC. If introduced later, template areas must be excluded from GC. |
| Same network selected in both dropdowns | Compare button is disabled; inline note "Select two different networks." |
| Promote network modal — no name entered | Save button disabled until a non-empty name is provided. |
| Org has no networks | Dropdowns and coverage are empty with "No networks collected yet — run a baseline first." |

---

## Constraints

- Templates are stored in our local SQLite DB only. They are **never** pushed to Meraki's template system. This is an observability tool — it never writes to vendor APIs.
- Scoring is computed on-demand per request. No background pre-computation or cache tables in Phase 6.
- The `<DiffViewer>` component from Phase 2 is reused as-is for field-level diff rendering inside both Compare Networks and Template Scoring expanded rows.

