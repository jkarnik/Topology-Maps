# Config Management in New Relic — Design Spec

**Date:** 2026-04-27  
**Status:** Draft  
**Scope:** POC — move the Topology Maps config management experience into New Relic One

---

## 1. Goal

Surface Meraki config management inside New Relic so that config state, history, and drift are visible in the same platform where infrastructure is observed — without switching to a separate tool.

**What this is not:** a rewrite of the backend. The existing FastAPI server and SQLite database remain the source of truth. This adds a push pipeline to NR and a Nerdpack UI on top.

---

## 2. Scope

### In scope
- A `config_ingest.py` script that pushes config data from SQLite to NR as custom events
- A Nerdpack (NR One App) with two surfaces:
  - **Standalone app** — full config browser accessible from the NR left nav
  - **Entity detail tab** — a "Config" tab on every switch, firewall, and AP entity page
- NRQL-based alerting on config drift — the data model supports it from day one; a ready-to-use alert condition recipe is included in this spec

### Out of scope
- Serverless / Lambda data collection (server continues to collect from Meraki)
- NR Flex agent
- Any changes to the existing local React UI
- Writing back to Meraki or any vendor API

---

## 3. Architecture

```
Meraki API
    │
    ▼ (existing collector — unchanged)
FastAPI server + SQLite
    │
    ▼ config_ingest.py  (new — runs manually or on cron)
NR Events API
    ├── MerakiConfigSnapshot events
    └── MerakiConfigChange events
    │
    ▼ NerdGraph / NRQL  (queried by Nerdpack)
NR One App (Nerdpack)
    ├── Standalone launcher app  (left nav)
    └── Entity detail tab  (on EXT-SWITCH / EXT-FIREWALL / EXT-ACCESS_POINT pages)
```

**Key principle:** The Nerdpack has no dependency on the FastAPI server. It reads everything from NR via NerdGraph. The server's only role in this integration is as the source that `config_ingest.py` reads from.

---

## 4. Data Model — NR Event Types

### 4.1 `MerakiConfigSnapshot`

One event per config observation. Pushed on every ingest run, representing the current known state of a config area for a given entity.

| Field | Type | Description |
|---|---|---|
| `entity_type` | string | `org`, `network`, or `device` |
| `entity_id` | string | Serial number, network ID, or org ID |
| `entity_name` | string | Human-readable name |
| `config_area` | string | e.g. `switch_ports`, `vlans`, `firewall_rules` |
| `sub_key` | string | Optional sub-item key (e.g. port number) |
| `config_hash` | string | SHA-256 of canonical JSON — used to detect changes |
| `config_json` | string | Full raw config JSON (no truncation — Pro account) |
| `org_id` | string | Parent org ID |
| `network_id` | string | Parent network ID (blank for org-level) |
| `sweep_run_id` | integer | ID of the sweep run that produced this observation |
| `tags.source` | string | `topology-maps-app` |

### 4.2 `MerakiConfigChange`

One event per detected change. Pushed when a config area's hash differs from the previous ingest run.

| Field | Type | Description |
|---|---|---|
| `entity_type` | string | Same as above |
| `entity_id` | string | Same as above |
| `entity_name` | string | Human-readable name |
| `config_area` | string | Which config area changed |
| `sub_key` | string | Optional |
| `from_hash` | string | Hash before the change |
| `to_hash` | string | Hash after the change |
| `diff_json` | string | Full pre-computed diff JSON (from existing diff_engine) |
| `change_summary` | string | Human-readable summary, e.g. `"3 added, 1 removed"` |
| `detected_at` | string | ISO 8601 timestamp of detection |
| `org_id` | string | Parent org ID |
| `network_id` | string | Parent network ID (blank for org-level) |
| `tags.source` | string | `topology-maps-app` |

### 4.3 Example NRQL

```sql
-- Alert: any config change in the last hour
SELECT count(*) FROM MerakiConfigChange
WHERE org_id = 'YOUR_ORG_ID' SINCE 1 hour ago

-- Current config for a specific switch, by area
SELECT latest(config_json) FROM MerakiConfigSnapshot
WHERE entity_id = 'Q2XX-1234' FACET config_area

-- Change history for a device
SELECT entity_name, config_area, change_summary, detected_at
FROM MerakiConfigChange
WHERE entity_id = 'Q2XX-1234'
SINCE 30 days ago LIMIT 100
```

---

## 5. Ingest Pipeline — `nr_ingest/config_ingest.py`

A new script following the same pattern as `nr_ingest/phase2_all_devices.py`.

**What it does:**
1. Loads the SQLite DB via `data_source.py` (container copy preferred, local fallback)
2. Reads all `config_observations` rows — builds `MerakiConfigSnapshot` events
3. Reads all `config_change_events` rows newer than the last successful ingest timestamp — builds `MerakiConfigChange` events
4. Batches both event types and POSTs to the NR Events API (`insights-collector.newrelic.com`)
5. Writes a `nr_ingest/data/.last_config_ingest` marker file recording the timestamp of the last successful run (used to avoid re-pushing stale change events)

**Credentials:** reads `NR_API_KEY` and `NR_ACCOUNT_ID` from `.env`, same as existing scripts.

**Running it:**
```bash
python3 nr_ingest/config_ingest.py          # one-shot, pushes everything
python3 nr_ingest/config_ingest.py --since 2h   # only changes in last 2 hours
```

**Scheduling:** For the POC, run manually after a baseline sweep. For production, add a cron job or hook it into the server's sweep completion event.

---

## 6. Nerdpack Structure

**Location:** `nerdpack/` at project root.  
**Built with:** `nr1` CLI (New Relic One SDK).

```
nerdpack/
  nr1.json                        — app manifest (name, id, description)
  package.json
  launchers/
    config-launcher/
      nr1.json                    — registers the standalone app in NR left nav
  nerdlets/
    config-app/                   — standalone full ConfigBrowser app
      index.js
      nr1.json
      components/
        OrgSelector.js
        ConfigTree.js             — org → network → device tree
        ConfigAreaViewer.js       — current config JSON for selected entity
        ChangeHistory.js          — timeline of MerakiConfigChange events
        DiffViewer.js             — renders diff_json as a readable diff
        CompareView.js            — side-by-side network comparison
    config-entity-tab/            — "Config" tab on device entity pages
      index.js
      nr1.json                    — declares entityTypes: EXT-SWITCH, EXT-FIREWALL, EXT-ACCESS_POINT
      components/
        ConfigSummary.js          — list of config areas + drift status
        RecentChanges.js          — last N MerakiConfigChange events for this entity
```

---

## 7. Nerdpack — Feature Breakdown

### 7.1 Standalone App (config-app nerdlet)

Three tabs, mirroring the existing ConfigBrowser:

| Tab | What it shows |
|---|---|
| **Overview** | Org selector → tree (org / network / device). Click any node to see its current config areas and the latest snapshot JSON for each. |
| **History** | Time-range selector. Shows a diff between the current config and a chosen past point, with a tree on the left highlighting which entities changed. |
| **Compare** | Pick two networks from the same org. Shows side-by-side config for each area, with differences highlighted. |

### 7.2 Entity Detail Tab (config-entity-tab nerdlet)

Appears as a **"Config"** tab on every `EXT-SWITCH`, `EXT-FIREWALL`, and `EXT-ACCESS_POINT` entity page.

Sections:
1. **Config status bar** — last synced timestamp, whether any area has drifted since baseline
2. **Config areas list** — one row per config area; green if unchanged, amber if changed recently
3. **Recent changes** — last 10 `MerakiConfigChange` events for this entity, with expandable diff view per change

---

## 8. Deployment

### Local development
```bash
cd nerdpack
npm install
nr1 nerdpack:serve     # hot-reload at https://one.newrelic.com?nerdpacks=local
```

### Publish to NR account (POC)
```bash
nr1 nerdpack:publish   # publish to NR account 7980758
nr1 nerdpack:deploy    # make it available in NR One nav
nr1 nerdpack:subscribe --channel STABLE
```

**Prerequisites:** `nr1` CLI installed, NR API key configured via `nr1 profiles:add`.

---

## 9. Open Questions / Future Work

- **Ingest scheduling:** For the POC, manual runs are fine. Long-term, hook `config_ingest.py` into the server's sweep completion event so NR is always current within minutes of a sweep.
- **Alerts recipe:** Document a standard NRQL alert condition for config drift as a follow-on. The data model supports it from day one.
- **Templates view:** The existing ConfigBrowser has a "Templates" tab (promote a config as a golden template, score networks against it). This is deferred — not in the Nerdpack POC scope.
