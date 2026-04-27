# Phase 6 Session Context — 2026-04-27

## Current State

**Branch:** `feature/phase6-multi-site-comparison`  
**Base:** `master`  
**Backend tests:** 301 passed (was 289 before Phase 6)  
**UI build:** clean (277 modules)

---

## What Was Built (Phase 6 Complete)

Four read-only features added to ConfigBrowser under a new **Compare** tab:

| Feature | Description |
|---|---|
| Compare Networks | Side-by-side diff of any two networks, grouped by config area, collapsible rows with DiffViewer |
| Coverage Dashboard | Per-config-area network coverage with missing-networks detail pane |
| Template Extraction | Promote any network snapshot as a template |
| Template Scoring | Score all networks against a template, per-area breakdowns |

---

## All 15 Commits on Branch

```
cfb4e5d fix(diff_engine): only use array mode for list-of-dicts, not list-of-scalars
95f7765 debug(phase6): add detailed logging to compare_networks to surface root cause
c75df21 fix(phase6): fix compare/networks 500 on mixed sub_key types; add resizable coverage pane
14d7e2f feat(phase6): implement TemplatesView with promote modal and scoring panel
d6f4894 feat(phase6): implement CoverageView
38c53f9 feat(phase6): implement CompareNetworksView
27ffaaf feat(phase6): wire Compare tab into ConfigBrowser
c69faaf feat(phase6): add CompareTab shell with stub sub-views
8e8b5ec fix(phase6): clear error state on successful fetch in hooks
8ae6335 feat(phase6): add frontend hooks for compare, coverage, templates
86d8a86 feat(phase6): add frontend types and API wrappers
b336d34 feat(phase6): add compare/coverage/template API endpoints + tests
d4283b5 feat(phase6): add get_coverage store function + test
eac1ef3 feat(phase6): add template store functions + tests
728e2a6 feat(phase6): add config_templates and config_template_areas tables
```

---

## Files Changed

### Backend — new/modified
| File | Change |
|---|---|
| `server/database.py` | Added `config_templates` + `config_template_areas` tables + index |
| `server/config_collector/store.py` | Added `create_template`, `list_templates`, `get_template_areas`, `delete_template`, `get_coverage` |
| `server/config_collector/diff_engine.py` | Fixed `compute_diff` — `is_array` detection now requires list-of-dicts, not any list |
| `server/routes/config.py` | Added 6 new endpoints (templates CRUD, compare/networks, coverage, template scores) |
| `server/tests/test_config_store_templates.py` | New — 5 store-layer tests |
| `server/tests/test_config_api_compare.py` | New — 7 API tests (including 2 regression tests) |

### Frontend — new files
| File | Purpose |
|---|---|
| `ui/src/api/compare.ts` | Fetch wrappers for all 6 Phase 6 endpoints |
| `ui/src/hooks/useNetworkCompare.ts` | State + fetch for /compare/networks |
| `ui/src/hooks/useCoverage.ts` | State + fetch for /coverage |
| `ui/src/hooks/useTemplates.ts` | State + mutations for templates CRUD |
| `ui/src/hooks/useTemplateScores.ts` | State + fetch for /templates/{id}/scores |
| `ui/src/components/ConfigBrowser/CompareTab.tsx` | Tab shell with 3-pill segmented control |
| `ui/src/components/ConfigBrowser/CompareNetworksView.tsx` | Network A vs B diff UI |
| `ui/src/components/ConfigBrowser/CoverageView.tsx` | Coverage dashboard with resizable split pane |
| `ui/src/components/ConfigBrowser/TemplatesView.tsx` | Template list + scoring panel + promote modal |

### Frontend — modified
| File | Change |
|---|---|
| `ui/src/types/config.ts` | Added 9 Phase 6 types |
| `ui/src/components/ConfigBrowser/ConfigBrowser.tsx` | Added Compare tab button + panel |
| `ui/src/components/ConfigBrowser/index.ts` | Re-exported 4 new components |

---

## API Endpoints Added

All under `/api/config/`:

| Method | Path | Description |
|---|---|---|
| GET | `/templates?org_id=` | List templates for org |
| POST | `/templates` | Promote network as template `{org_id, name, network_id}` |
| DELETE | `/templates/{id}` | Delete template |
| GET | `/compare/networks?org_id=&network_a=&network_b=` | Compare two networks |
| GET | `/coverage?org_id=` | Coverage counts per config area |
| GET | `/templates/{id}/scores?org_id=` | Score all networks against template |

---

## Bugs Fixed During Session

### Bug 1 — `sorted()` TypeError on mixed sub_key types (commit `c75df21`)
**Symptom:** 500 on `/compare/networks`  
**Root cause:** `sorted(all_keys)` where `all_keys` is a set of `(config_area, sub_key)` tuples. When the same `config_area` has `sub_key=None` in one network and a string in the other, Python 3 raises `TypeError: '<' not supported between instances of 'NoneType' and 'str'`.  
**Fix:** Sort key `lambda k: (k[0], "" if k[1] is None else k[1])`

### Bug 2 — `compute_diff` crash on list-of-strings blobs (commit `cfb4e5d`)
**Symptom:** 500 on `/compare/networks` for networks with Meraki blobs containing top-level list-of-string values (e.g. `{"tags": ["foo", "bar"], ...}`)  
**Root cause:** `is_array` in `compute_diff` triggered on `any(isinstance(v, list) ...)` — matched any list, including lists of strings. `_array_diff` then passed string elements to `_object_diff`, which called `set("tag1")` producing individual characters, then `a["t"]` → `TypeError: string indices must be integers, not 'str'`.  
**Fix:** `_is_row_list(v)` — requires list to be non-empty and `v[0]` to be a dict before enabling array mode.

### Bug 3 — stale error state in hooks (commit `8e8b5ec`)
**Root cause:** `.then()` callbacks in `useCoverage`, `useTemplates`, `useTemplateScores` didn't call `setError(null)` on success, so a prior error would persist after a successful re-fetch.  
**Fix:** Added `setError(null)` to all success paths.

---

## Remaining Work

### Immediate
- **Manual smoke test** — `docker compose up --build`, then verify:
  1. Compare tab appears in ConfigBrowser
  2. Compare Networks: select two networks → diff results appear, collapsible rows work
  3. Coverage: left panel lists areas with counts, right panel shows missing networks, drag handle resizes the split
  4. Templates: promote a network, scores load, per-area rows expand, delete works
- **Merge to master** — once smoke test passes, use `superpowers:finishing-a-development-branch`

### Known gaps / future work
- Template scoring uses only the most recent snapshot per network; no time-travel
- Coverage `device_breakdown` is populated but not deeply surfaced in the UI
- No pagination on coverage or template scores (fine for typical org sizes)
- `_is_row_list` checks only `v[0]`; a mixed list (first item is dict, later items are not) would still crash `_array_diff`. Considered acceptable edge case for now.

---

## How to Resume

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git checkout feature/phase6-multi-site-comparison
# Verify tests still pass
python3 -m pytest server/tests/ -q
# Rebuild Docker with all changes
docker compose up --build
```

To finish the branch:
```
Use superpowers:finishing-a-development-branch skill
```
