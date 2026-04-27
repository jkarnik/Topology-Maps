# Config Management — New Relic Integration

Surface Meraki config snapshots, change history, and drift alerts inside New Relic One.

---

## Prerequisites

- Topology Maps server has run at least one baseline sweep (config data in `data/topology.db`)
- `.env` file at project root with:
  ```
  NR_LICENSE_KEY=your_license_key
  NR_ACCOUNT_ID=your_account_id
  ```
- `nr1` CLI installed: `npm install -g @newrelic/nr1`
- NR profile configured: `nr1 profiles:add --name default --api-key YOUR_KEY --region US`

---

## Step 1 — Push config data to New Relic

Run the ingest script from the project root:

```bash
python3 nr_ingest/config_ingest.py
```

This reads `data/topology.db` (copying it from the running Docker container if available), then pushes two event types to NR:

- **`MerakiConfigSnapshot`** — current config state for every observed entity + config area
- **`MerakiConfigChange`** — one event per detected hash change between consecutive observations

Output example:
```
Using topology.db copied from topologymaps-server-1:/app/data/topology.db
Snapshot events:  142
Change events:    8
Total to push:    150
Batch 1: posting 150 events...

All 150 events accepted. Marker updated: 2026-04-27T14:30:00Z
```

### Push only recent changes

```bash
python3 nr_ingest/config_ingest.py --since 2h   # changes in last 2 hours
python3 nr_ingest/config_ingest.py --since 30m  # changes in last 30 minutes
```

Without `--since`, the script uses the timestamp from its last successful run (stored in `nr_ingest/data/.last_config_ingest`).

### Scheduling

For continuous updates, run after each sweep completes. Quick cron example:

```bash
# Every 30 minutes
*/30 * * * * cd /path/to/topology-maps && python3 nr_ingest/config_ingest.py
```

---

## Step 2 — Launch the Nerdpack

```bash
cd nerdpack
nr1 nerdpack:serve
```

Open: `https://one.newrelic.com?nerdpacks=local`

---

## Step 3 — Use the app

### Standalone Config Browser (left nav → "Meraki Config")

| Tab | What it shows |
|-----|---------------|
| **Overview** | Select an org → browse entity tree → click any node to see its config areas and current JSON |
| **History** | Change timeline for the selected org/entity — click "View diff" to see exactly what changed |
| **Compare** | Pick two networks from the same org → side-by-side JSON for every config area that differs |

### Entity "Config" tab

Appears on every Meraki entity page (org, site, switch, firewall, AP):

- **Config status cards** — green if stable, amber if changed in the last 24 hours
- **Recent changes** — last 10 change events, each expandable to show the full diff

---

## Publishing to your NR account (beyond local dev)

```bash
cd nerdpack
nr1 nerdpack:publish
nr1 nerdpack:deploy
nr1 nerdpack:subscribe --channel STABLE
```

After publishing, the app is available to all users in your NR account without the `?nerdpacks=local` flag.

---

## Alert conditions (NRQL)

Set these up in NR One → Alerts → Create alert condition → NRQL:

```sql
-- Any config change detected (fires within ~15 min of a drift event)
SELECT count(*) FROM MerakiConfigChange
WHERE tags.source = 'topology-maps-app'
SINCE 1 hour ago

-- Changes on a specific network
SELECT count(*) FROM MerakiConfigChange
WHERE network_id = 'N_123456789'
SINCE 1 hour ago

-- High-frequency drift (> 5 changes in 1 hour)
SELECT count(*) FROM MerakiConfigChange
WHERE tags.source = 'topology-maps-app'
SINCE 1 hour ago HAVING count() > 5
```

Recommended threshold: `count > 0` → warning-level incident.

---

## Limitations (POC scope)

| Feature | Status |
|---------|--------|
| Trigger baseline/sweep from Nerdpack | Not available — use local app or `POST /api/config/baseline/{org_id}` |
| Live sweep progress | Not available — NR data updates on next ingest run (~poll) |
| Golden config templates | Not in scope — deferred |
