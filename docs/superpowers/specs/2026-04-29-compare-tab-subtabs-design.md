# Compare Tab — Sub-tabs Design

**Date:** 2026-04-29
**Scope:** `nerdpack/nerdlets/config-app/components/CompareView.js` only. No backend changes, no new files.

---

## 1. Overview

The Compare tab currently renders a single flat network diff view. This spec adds a three-sub-tab structure — **Networks**, **Coverage**, and **Templates** — inside the existing Compare tab.

---

## 2. Sub-tab Navigation

Pill-style toggle buttons rendered at the top of `CompareView`. Implemented with `useState('networks')` — no NR1 `Tabs` component. Three pills: Networks | Coverage | Templates. Active pill has a blue tinted background and blue border; inactive pills have a muted border and grey text.

Template selection (see §5) resets on page refresh — no persistence required for POC.

---

## 3. Networks Tab

Existing `SideBySideDiff` and `NetworkSelector` logic, unchanged. Rendered when active sub-tab is `'networks'`.

---

## 4. Coverage Tab

**Purpose:** Show what percentage of config areas have been observed (snapshotted) per network across the org.

**Data source:** Single `NrqlQuery` against `MerakiConfigSnapshot`:

```nrql
SELECT latest(timestamp) FROM MerakiConfigSnapshot
WHERE org_id = '{orgId}'
FACET entity_id, config_area
SINCE 30 days ago LIMIT MAX
```

Presence is inferred from whether the facet exists; recency is the `latest(timestamp)` value.

**Client-side logic:**

1. Collect all distinct config area names across the org (columns).
2. For each network (row), compute coverage % = observed areas / total distinct areas × 100.
3. Each cell state: **green** = last snapshot ≤ 7 days ago, **amber** = last snapshot > 7 days ago, **dark grey** = never observed.
4. Sort rows descending by coverage %.

**Rendering:**

- Table at 12px body font, 11px column headers.
- Columns: Network name | Coverage % | one column per config area.
- Coverage % color-coded: green ≥ 80%, amber 50–79%, red < 50%.
- Table scrolls horizontally if config area columns overflow.
- Legend below table: green = observed, amber = stale (>7d), dark = never observed.

---

## 5. Templates Tab

**Purpose:** Designate one network as a golden reference template, then score all other networks against it by config area match.

**Interaction:**

1. Dropdown lists all networks in the org (same `NetworkSelector` pattern as Networks tab, single select).
2. "Set as Template" button writes selection to `useState`.
3. Once a template is set, a header line shows: `Scoring against: [Network Name] · N config areas · last snapshot X ago`.

**Data source:** Same NRQL as the Networks tab diff — `latest(config_json)` from `MerakiConfigSnapshot` faceted by `entity_id` and `config_area`, SINCE 30 days ago. One query loads all networks at once; client-side slices out the template network and compares each other network against it.

**Scoring logic:**

- Score = (number of config areas where network's `config_json` exactly matches template's `config_json`) / (total config areas present in template) × 100%.
- Areas present in the template but missing from the scored network count as mismatches.
- Areas present in the scored network but absent from the template are ignored.

**Rendering (per network card):**

- Border and background tinted by score: green ≥ 80%, amber 50–79%, red < 50%.
- Header row: network name (left), score % in large bold font (right), areas matched as `X / N` (right).
- Below header: per-area badge row — green `area ✓` for matches, red `area ✗` for mismatches.
- Cards sorted descending by score.
- Template network excluded from results.

---

## 6. Spec Coverage Checklist

- [x] Sub-tab pill navigation — §2
- [x] Networks tab unchanged — §3
- [x] Coverage heat grid with % column — §4
- [x] Coverage cell states (green / amber / grey) — §4
- [x] Coverage sorted descending by % — §4
- [x] Font size 12px body, 11px headers — §4
- [x] Template network selector + Set button — §5
- [x] Scoring logic (exact config_json match per area) — §5
- [x] Per-area pass/fail badges — §5
- [x] Score cards color-coded and sorted — §5
- [x] Template excluded from scored results — §5
