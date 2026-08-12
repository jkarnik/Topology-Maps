# Design: Meraki as Default Source + World Map Landing View

> **Status:** Approved, pending spec review
> **Date:** 2026-08-12

## Summary

Two changes to the Topology Maps UI:

1. **Meraki Live becomes the default data source** (was Configs).
2. **A world map landing view** is added for the Meraki source: every site
   (Meraki network) is plotted at its real-world location as a circle sized
   by device count and colored by health. Clicking a site zooms in and
   fades into that site's existing device-topology view — unchanged from
   today.

This directly implements PRD §4.1 ("The landing view — a world map of
sites") from `docs/topology-prd-customer-first.md`.

## Goals

- Meraki Live is the first thing a user sees on open (was Configs).
- Opening Meraki lands on a world map of sites, not an auto-selected
  network's topology.
- Each site renders as a circle: **size = device count**, **color = health**
  on a 5-tier scale (healthy → escalating severity → unknown).
- Clicking a site circle plays a zoom transition, then fades into that
  site's existing L2/L3 topology view (unchanged).
- Sites with no resolvable location are still reachable, via a small
  "Unmapped" list alongside the map — nothing is hidden.
- The existing "jump to a site" dropdown in the TopBar stays as a shortcut
  that bypasses the map.
- Location, size, and health are computed from Meraki data the app already
  fetches (org devices, device availabilities, org networks) — no new
  Meraki API calls.

## Non-Goals

- No inter-site connections drawn on the map (out of scope per PRD §1/§4.1).
- No 3D globe / flyover animation — a flat 2D map with a CSS zoom/pan
  transition (see "Zoom & fade transition" below). Explicitly deferred: a
  WebGL 3D globe would require a new heavy dependency and meaningfully more
  implementation for a cosmetic upgrade; can be revisited later if wanted.
- No changes to the Simulated or Configs sources, or to the per-site
  topology view itself (device layout, drill-down, filtering) — all of
  that is reused as-is.
- No live map tiles / third-party map service — the world outline is a
  small bundled static asset, consistent with this app having no external
  map dependency today.

## Current State (relevant)

- `App.tsx` holds `dataSource: 'meraki' | 'simulated' | 'configs'`, default
  `'configs'`. Switching to `'meraki'` triggers a load: cached
  localStorage → committed seed/SQLite snapshot → live Meraki API, then
  **auto-selects the first network** and pulls its full L2/L3 topology.
- `useMerakiTopology.ts` owns Meraki topology state (network list, L2/L3,
  refresh, cache). It has no concept of "all sites at a glance" — only a
  currently-selected network's topology.
- `server/routes/meraki.py` exposes per-network topology endpoints
  (`/topology/l2`, `/topology/l3`, `/topology/device-details`, `/refresh`
  SSE) and org-level list endpoints (`/networks`, `/status`). Devices are
  fetched via `MerakiClient.get_org_devices`, which already returns each
  device's `lat`/`lng`/`address` when Meraki has them. Health comes from
  `get_org_device_availabilities` (`online`/`alerting`/`offline`/`dormant`
  per device).
- No mapping library exists in `ui/package.json`, and no frontend test
  infrastructure exists in the repo.

## Backend: `GET /api/meraki/sites`

One new endpoint in `server/routes/meraki.py`, following the existing
pattern (org id lookup, `MerakiClient`, `MerakiTransformer`-style
aggregation). Fetches `get_org_devices`, `get_org_device_availabilities`,
and `get_org_networks` for the org — all calls already used elsewhere in
this file — and returns one entry per network:

```json
{
  "sites": [
    {
      "network_id": "N_1",
      "name": "Dallas DC",
      "lat": 32.78, "lng": -96.80,
      "device_count": 84,
      "health_bucket": "orange",
      "unhealthy_pct": 0.34,
      "mapped": true
    },
    { "network_id": "N_2", "name": "Warehouse B", "mapped": false, "device_count": 6, "health_bucket": "unknown" }
  ]
}
```

**Location resolution** — for each network, scan its devices for the first
with non-null `lat` and `lng` (set on the device when a Meraki address is
configured). None found → `mapped: false`, `lat`/`lng` omitted.

**Device count** — total devices whose `networkId` matches, all statuses
included (size reflects footprint, not just currently-healthy devices).

**Health bucketing** — from `get_org_device_availabilities`, per network:
denominator = devices with status `online`, `alerting`, or `offline`
(`dormant` excluded — usually unprovisioned spares, would skew the ratio).
`unhealthy_pct = (alerting + offline) / denominator`. Buckets:

| unhealthy_pct        | bucket    | color   |
|----------------------|-----------|---------|
| = 0%                 | `green`   | #2ecc71 |
| > 0% and ≤ 25%       | `yellow`  | #f1c40f |
| > 25% and ≤ 60%      | `orange`  | #e67e22 |
| > 60%                | `red`     | #e74c3c |
| no data (denominator = 0) | `unknown` | gray — never show false-green |

This is a pure aggregation function (`_build_sites` or similar, colocated
with or alongside `MerakiTransformer`) so it can be unit tested without
mocking HTTP.

## Frontend: `WorldMapView` + `useMerakiSites`

**`useMerakiSites.ts`** — a small, separate hook (not folded into the
already-large `useMerakiTopology.ts`): fetches `/api/meraki/sites`,
exposes `{ sites, isLoading, error, refresh }`. Kept independent because
it has a different lifecycle (loads once on Meraki landing, not per
selected network) and a different, much lighter payload.

**`WorldMapView.tsx`** — renders:
- A bundled static world-outline SVG (continent silhouettes, equirectangular
  projection, no political borders needed) as the background.
- One circle per mapped site, positioned via `x = (lng+180)/360 * W`,
  `y = (90-lat)/180 * H` matched to that SVG's projection. Radius scaled
  (square-root, for perceptual area accuracy) from `device_count`, clamped
  to a minimum so small sites stay clickable.
- Fill color from `health_bucket`.
- Hover/tap tooltip: site name, device count, and "N alerting" if
  unhealthy_pct > 0 (per the approved hover-reveal, not always-on-labels,
  decision).
- A legend (size = device count, color scale swatches) anchored
  bottom-left.
- An "Unmapped (N)" panel (top-right) listing sites with `mapped: false`
  by name — clicking one jumps straight into its topology view, same as
  clicking a mapped circle.

**`App.tsx` changes:**
- Default `dataSource` → `'meraki'`.
- New local view state, e.g. `merakiView: 'map' | 'site'`, initialized to
  `'map'`. The Meraki-tab-entry effect now fetches sites (cheap) instead of
  eagerly auto-selecting and fully loading a network.
- When `dataSource === 'meraki' && merakiView === 'map'` → render
  `WorldMapView`. Clicking a site sets `selectedNetwork` (existing hook
  setter, unchanged) and `merakiView = 'site'`, which triggers the zoom/fade
  described below.
- TopBar gets a "◀ World Map" control, visible only in the Meraki +
  `'site'` state, that sets `merakiView = 'map'` (site data stays cached,
  so returning to a site later is instant — same cache-first behavior the
  network dropdown already relies on).
- The existing network-jump dropdown is unchanged and still available in
  both states.

## Zoom & fade transition

No new animation library. On click:

1. Compute the clicked circle's screen position.
2. Animate the map container's CSS `transform` (`scale` + `translate`
   centered on that point) up while fading `opacity` down, over ~400ms.
3. Swap in the existing topology view underneath, fading `opacity` in over
   ~300ms.
4. Reverse (fade out topology, fade/scale the map back in) when "◀ World
   Map" is clicked.

Pure CSS transitions driven by React state (`merakiView` plus a transient
"transitioning" flag) — same toolkit already used elsewhere in this UI
(inline styles, no animation dependency).

## Caching

Reuses the existing mechanism rather than inventing a second one:

- `merakiCache.ts`'s schema gains a `sites` field (bump `SCHEMA_VERSION`).
  `useMerakiSites` checks localStorage cache, then the server-side
  `/api/meraki/cache/load` snapshot, before hitting `/api/meraki/sites`
  live — mirroring `loadSeedFile()`'s resolution order in
  `useMerakiTopology`.
- "Save Snapshot" (`saveSnapshot()`) is extended to include the current
  `sites` payload, so a committed seed file paints the world map instantly
  on a fresh clone, same as it does for per-site topology today.

## Error Handling & Edge Cases

- **No `MERAKI_API_KEY` configured** — `WorldMapView` shows the same
  "not configured" messaging pattern `useMerakiTopology` already surfaces
  for this case, just rendered in the map's place.
- **Zero networks** — empty state: "No sites found."
- **All sites unmapped** — map renders with no circles; the "Unmapped"
  panel lists everything. Degenerate but functional; no special-casing
  needed beyond what's already planned.
- **Availability fetch fails/partial** — sites default to `unknown`
  (gray), never falsely green.
- **A site's only device with coordinates goes offline/is removed** — next
  refresh simply re-resolves location from whichever device currently has
  it; no persistence of "last known" location (matches this app's
  freshness-over-continuity stance elsewhere).

## Testing Plan

- **Backend:** new `server/tests/test_meraki_sites.py`, following the
  existing `test_meraki_*` table-driven style — covers location resolution
  (device with coords / no devices with coords / multiple candidates),
  health bucketing at each threshold boundary, dormant-exclusion from the
  denominator, and the zero-devices/zero-networks edge cases. Runs under
  `python3 -m pytest`, no Docker required, consistent with the rest of the
  suite.
- **Frontend:** no test infrastructure exists in this repo today; this
  design doesn't introduce one. Verified manually via `npm run dev`:
  landing on the world map as the default, hover tooltips, clicking a
  mapped site through to its topology and back, the unmapped-sites panel,
  and the not-configured/empty states.

## Summary of Decisions (from brainstorming)

- Health color: **escalating gradient** (4 severity tiers + unknown), not
  binary.
- Site labels: **hover/click tooltip**, not always-on (scales to many
  sites).
- Unmapped sites: **shown in a side list**, not hidden.
- Network-jump dropdown: **kept** as a shortcut alongside the map.
- Map style: **flat 2D + CSS zoom/pan transition**, not a 3D globe
  fly-in — explicitly deferred as a possible future polish pass.
