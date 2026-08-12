# Design: World Map v2 — Real Map, Zoom/Pan, Circle Polish

> **Status:** Approved, pending spec review
> **Date:** 2026-08-12

## Summary

Four enhancements to the world-map landing view shipped in
`docs/superpowers/specs/2026-08-12-meraki-world-map-landing-design.md`:

1. Replace the hand-drawn continent silhouettes with a real, accurate world
   map (real coastline data, still a bundled static asset — no live tiles).
2. Add zoom/pan to the map itself (scroll, drag, pinch, +/− buttons).
3. Give site circles a persistent border, and keep their on-screen size
   readable at any zoom level instead of ballooning with the map.
4. Make circle fills semi-transparent so overlapping sites are visible
   through each other, and rely on real geography — not synthetic
   clustering — to separate them as the user zooms in.

## Goals

- The map background is a real, recognizable world map (actual coastlines),
  not the hand-drawn approximation from v1.
- The user can zoom and pan the map: scroll wheel, click-drag, pinch (touch),
  double-click-to-zoom, and explicit +/− buttons.
- Site circles keep a legible, roughly-constant on-screen size across the
  zoom range — they don't grow into the whole viewport at high zoom.
- Overlapping site circles are visually distinguishable (border + partial
  transparency) even before zooming in.
- Zooming in on a cluster of nearby-but-distinct sites visibly separates
  them, purely as a consequence of real geographic distance — no clustering
  algorithm, no jitter, no faked positions.
- The existing click-a-site → zoom/fade → per-site-topology transition
  (from v1) still centers correctly regardless of the map's current pan/zoom
  state.

## Non-Goals

- No live map tiles, no third-party tile service, no API key — still a
  bundled static data file, consistent with v1's self-contained approach.
- No synthetic declustering/force-layout for sites that report genuinely
  identical coordinates (e.g. multiple Meraki networks sharing one fallback
  org address) — that's a real data characteristic, not something the map
  should paper over.
- No change to the per-site topology view, the health-color scale, the
  hover tooltip's content, or the unmapped-sites panel — this is a map
  rendering/interaction upgrade only.
- No political country borders as a visual feature — the real map is
  coastline/landmass data (a recognizable backdrop), not a political atlas.

## Dependency Change (disclosed)

v1's design explicitly chose "no new frontend dependencies — no mapping
library" to keep the app self-contained. This design walks that back
deliberately: rendering an accurate world map and implementing real
zoom/pan by hand would mean either (a) hand-authoring thousands of
coastline coordinates (impractical and not meaningfully "self-contained"
anyway), or (b) reinventing zoom/pan/pinch gesture handling that a
well-tested library already solves. Instead:

- **`d3-geo`** — geographic projection math (replaces the hand-rolled
  equirectangular formula in `worldProjection.ts`).
- **`d3-zoom`** — pan/zoom/pinch interaction (scroll, drag, pinch,
  double-click, programmatic zoom for the +/− buttons).
- **`topojson-client`** — decodes the bundled map data format.
- **`world-atlas`** — the actual map data (`land-110m.json`, public domain,
  ~100KB), used only as a static asset read at build time — no runtime
  fetch, no live network dependency.

All four are small (~50KB of library code + ~100KB of data, combined),
narrowly scoped to exactly this job, and are the standard, idiomatic way to
build an interactive SVG world map without a tile server. Still no
`Leaflet`/`Mapbox`/tile provider, and still no API key.

## Projection

`worldProjection.ts`'s hand-rolled `project(lat, lng)` formula is replaced
by a `d3-geo` projection — **`geoNaturalEarth1`**, not `geoEquirectangular`.
Natural Earth's curved, tapered shape is what most people recognize as "a
world map" (it's the projection behind most editorial/product world maps);
the flat equirectangular grid from v1 reads more like a technical chart.
The projection is configured once with a `.fitSize([width, height], landGeoJSON)`
call so it's automatically centered and scaled to the same `WORLD_VIEWBOX`
dimensions the rest of the app already assumes — `radiusForDeviceCount`,
the tooltip, and the legend/unmapped-panel positioning are all unaffected
by this swap, since they only consume the resulting `{x, y}` point, not the
projection math itself.

`d3.geoPath().projection(projection)` renders the `land-110m` TopoJSON
(decoded once via `topojson-client`'s `feature()`) as the map background,
replacing the hand-drawn `WORLD_OUTLINE_PATHS` array entirely.

## Zoom & Pan

`d3-zoom` is attached imperatively to the SVG via a `ref` + `useEffect`,
not modeled as React state that re-renders on every tick — zoom/pan/pinch
gestures fire many events per second, and routing each one through a React
re-render would be visibly less smooth than letting D3 update the DOM
directly (the standard pattern for combining React and D3: React mounts
the SVG structure once per `sites` change, D3 owns the continuous
transform after that).

- The map background and site circles live inside one `<g>` that receives
  `d3-zoom`'s transform (`translate(x,y) scale(k)`) on every zoom event.
- Scroll wheel, click-drag, pinch (touch), and double-click-to-zoom are
  `d3-zoom`'s defaults — no custom gesture code.
- Two small +/− buttons (bottom-right, near the existing legend's corner)
  call `zoom.scaleBy(selection, 1.4)` / `(1/1.4)` for discoverability and
  keyboard/accessibility-friendly zooming without a wheel or touchscreen.
- Zoom scale is clamped via `d3-zoom`'s `.scaleExtent([1, 20])` — 1 is the
  fitted "see the whole world" state; 20 is deep enough to separate any
  realistically-close sites without becoming disorienting.
- A click on a circle (no drag) still fires `onSelectSite` — `d3-zoom`
  only intercepts a gesture as a pan once the pointer has actually moved
  past its internal threshold, so existing circle click handlers keep
  working unmodified.

## Circle Rendering: Border, Opacity, Zoom-Stable Size

On every `d3-zoom` transform event, in addition to updating the `<g>`
transform, each circle's `r` attribute is recomputed as
`baseRadius / zoomScale` (clamped to `[MIN_RADIUS, MAX_RADIUS]`, same
constants as today), where `baseRadius` is still `radiusForDeviceCount(...)`
— i.e., "size reflects device count" continues to hold at the base (1x)
zoom level, but the *rendered* size at any zoom is corrected so it doesn't
grow with the map. This is the standard "non-scaling stroke/marker" pattern
for D3 zoomable maps.

Circle styling:
- `fill-opacity: 0.82` (health color still clearly readable, but a
  partially-hidden circle underneath shows through).
- A persistent border, `stroke: var(--bg-primary)` at `1px` (scaled by the
  same `1/zoomScale` factor as the radius, so it doesn't thicken into a
  blob at high zoom) — this is what makes two overlapping circles read as
  distinct stacked shapes even at their fill's shared opacity.
- On hover, the border switches to the existing `var(--text-primary)`
  highlight at `2px` (also zoom-corrected), on top of the persistent one.

No clustering, jitter, or force-layout is introduced. Two sites separate on
zoom exactly because their real lat/lng differ — the same projection math
already in place, now simply zoomed in on.

## Fixing the Click-to-Site Transition Origin

v1's `onSelectSite` computed the CSS `transform-origin` for the
zoom-into-topology animation as a percentage of the *viewBox* (`xPct/yPct`
from the circle's static projected coordinates). That's now wrong as soon
as the user has panned or zoomed the map — the circle's `cx/cy` stay in
viewBox space, but its position *on screen* depends on the live `d3-zoom`
transform too.

Fix: compute the origin from the circle's actual rendered position at
click time — `event.currentTarget.getBoundingClientRect()` relative to the
map container's own `getBoundingClientRect()`, converted to a percentage
of the container. This is correct regardless of current pan/zoom state,
and is simpler than threading `d3-zoom`'s transform state up through props
to recompute the same thing manually. `WorldMapView`'s `onSelectSite`
signature (`(networkId, origin: {xPct, yPct}) => void`) is unchanged —
only how `origin` is computed changes, so `App.tsx` needs no changes here.

## Fixing the Hover Tooltip Position

The hover tooltip has the same underlying issue as the click-transition
origin: it's an HTML overlay positioned as a percentage of the container,
computed from the hovered site's static `project(lat, lng)` point — which
breaks the moment the map is panned or zoomed, for the same reason.

Fix: keep the tooltip as an HTML overlay (not moved inside the SVG — its
text needs to stay a constant, readable screen size regardless of zoom
level, which an SVG-embedded element would not do without its own
counter-scaling), but position it from `getBoundingClientRect()` of the
currently-hovered circle, recomputed both on hover-enter and on every
`d3-zoom` transform event while a circle is hovered (so the tooltip stays
glued to its circle if the user zooms/pans mid-hover instead of freezing
at its pre-zoom position).

## What Doesn't Change

- `MerakiSite`, `HealthBucket`, `HEALTH_COLORS`, the backend, the caching
  layers, the hover tooltip's content, the unmapped-sites panel, and the
  legend's content are all unchanged.
- `radiusForDeviceCount(deviceCount, maxDeviceCount)`'s signature and
  "square-root scaling, clamped to `[6, 26]`" contract are unchanged — it
  still defines the *base* radius; zoom-correction is a separate,
  multiplicative step applied on top at render time.

## Error Handling & Edge Cases

- **Two sites at the exact same lat/lng** — they render as fully
  overlapping circles at any zoom (correct: they really are at the same
  place). The semi-transparent fill + border still shows both are present;
  hovering shows whichever is on top, same as v1's existing overlap
  behavior — not solved further by this design (see Non-Goals).
- **Zooming out below the fitted view** — clamped at `scaleExtent`'s lower
  bound (1x = fitted), so the user can't pan the map into empty space
  beyond the world's edges at the zoomed-out extreme.
- **Resizing the browser window** — `d3-geo`'s `.fitSize()` is computed
  once against `WORLD_VIEWBOX` (a fixed logical size), not the live pixel
  size, so it behaves exactly like v1's viewBox-based scaling: the SVG
  scales via `preserveAspectRatio`, and the fix already in place for
  `WorldMapView`'s container aspect ratio (from the final review of v1)
  continues to keep that scaling artifact-free.

## Testing Plan

- No frontend test infrastructure exists in this repo (unchanged from v1).
  Verified manually: `cd ui && npx tsc --noEmit` after each change, and a
  full manual pass (scroll-zoom, drag-pan, pinch if a touch device is
  available, +/− buttons, click-to-site from various zoom/pan states,
  hovering overlapping circles) via `npm run dev` and, where a real Meraki
  key is available, against live data — mirroring how v1 was ultimately
  verified (headless Chrome + real org data).
- Backend is untouched by this design — no backend test changes.

