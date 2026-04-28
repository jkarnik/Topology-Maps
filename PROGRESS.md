# Config NR Nerdpack — Session Progress

## What was built (previous session, now committed)
- `nr_ingest/config_ingest.py` — pushes `MerakiConfigSnapshot` + `MerakiConfigChange` events to NR
- NR Nerdpack at `nerdpack/` with UUID `b579e606-6ef2-4922-a770-707fdd3e8cee`
- Nerdpack nerdlets: `config-app` with OrgSelector, ConfigTree, ConfigAreaViewer, ChangeHistory, CompareView, DiffViewer

## What was fixed THIS session

### config_ingest.py
- Added `_build_entity_meta(conn)` — reads `device_metadata` + `network_metadata` blobs to build `{entity_id: {name, network_id}}` map
- Added `_derive_network_id()` — network→self, ssid→split(':')[0], device→entity_meta lookup
- Added `_derive_name()` — uses name_hint first, falls back to entity_meta name
- Result: ALL snapshot events now carry `entity_name` and `network_id` correctly for every config_area row, not just the metadata row
- Last ingest run: 2026-04-28T10:27:31Z (1145 events pushed)

### NrqlQuery field name bug (CRITICAL discovery)
NR1 CHART format returns aggregation results with the **bare field name** as key, NOT `latest.fieldname`.
- Wrong: `s.data[0]['latest.entity_name']`
- Correct: `s.data[0]['entity_name']`
- Fixed in ConfigTree.js (entity_name, network_id)
- Fixed in ConfigAreaViewer.js (config_hash, observed_at, config_json) — kept both with fallback
- Fixed in CompareView.js (config_json)

### ConfigTree.js (Nerdpack)
- Removed `NrqlQuery.formatType.RAW` — that property does not exist in this NR1 version
- Now uses default CHART format + Object.assign merge to combine 2 series per entity into one record
- Groups structure confirmed: `[{type:'function',...}, {type:'facet', value: entity_type}, {type:'facet', value: entity_id}]`
- SSIDs now collapsed by default (`defaultOpen` prop removed)

### Color scheme
- All hardcoded dark-only colors replaced with theme-neutral values across all components:
  - `#e0e0e0` → `inherit`
  - `#8e9aad` → `opacity: 0.6`
  - `#0095f7` / `#0d1117` backgrounds → `rgba(0,120,191,0.12)` / `rgba(128,128,128,0.08)`
  - Borders → `rgba(128,128,128,0.15)`

### Topology UI — SSIDs in config tree
SSIDs were missing from the topology app's config browser. Fixed in 3 places:
- `server/routes/config.py` `get_tree()` — now queries `entity_type='ssid'`, maps by `entity_id.split(':')[0]`, includes `ssids: [...]` in each network payload
- `ui/src/types/config.ts` — added `ssids: { id: string; name: string | null }[]` to `ConfigTreeNetwork`
- `ui/src/components/ConfigBrowser/ConfigTree.tsx` — renders collapsed "SSIDs (N)" section under each network; clicking expands; individual SSIDs are selectable (routes to entity config view)

## Current state
- Nerdpack is serving locally: run `cd nerdpack && nvm use 20 && nr1 nerdpack:serve --profile production`
- Access at: `https://one.newrelic.com/?nerdpacks=local`
- NR account: 7980758, org_id: 225248
- Profile used: `production` (region: us)

## Known remaining issues / not yet done
- Nerdpack not yet published to production NR account (T&C must be accepted at one.newrelic.com/developer-center before `nr1 nerdpack:publish` will work)
- Network names and device→network placement in Nerdpack tree: data is correct in NR (verified), should display correctly now that field name bug is fixed. If still showing raw IDs on fresh load, the field name fix resolves it.
- The topology UI SSID fix requires a server restart to pick up the `get_tree` route change

## Key commands
```bash
# Re-run config ingest (push fresh snapshot + change events to NR)
cd "/Users/jkarnik/Code/Topology Maps" && python3 nr_ingest/config_ingest.py

# Serve Nerdpack locally
cd nerdpack && nvm use 20 && nr1 nerdpack:serve --profile production

# Run topology app full stack
docker compose up --build

# Backend tests
python3 -m pytest
```

## Architecture reminder
- `MerakiConfigSnapshot` — one event per (entity_id, config_area), latest state. Fields: entity_type, entity_id, entity_name, config_area, config_hash, config_json, org_id, network_id
- `MerakiConfigChange` — one event per detected hash change. Fields: entity_type, entity_id, from_hash, to_hash, diff_json, change_summary, detected_at, org_id, network_id
- SSID entity_id format: `{network_id}:{ssid_number}` e.g. `L_652458996015307332:1`
- Device→network mapping: stored in `device_metadata` blob under `networkId` (camelCase)
