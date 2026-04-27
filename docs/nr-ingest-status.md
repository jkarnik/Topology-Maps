# New Relic Ingest — Status & Reference

**Goal:** Push the Meraki topology data cached by this app into New Relic so devices, networks,
clients, VLANs, and ports are queryable as entities, and per-site topology is visible via Workload maps.

**NR Account:** `7980758`  
**Data source:** Container DB (`topologymaps-server-1:/app/data/app.db`) pulled via `docker cp`

---

## Entity Model

| Our Data | NR Entity Type | Event Type | Identifier | Count |
|---|---|---|---|---|
| Org | `EXT-MERAKI_ORGANIZATION` | `MerakiOrganization` | `org_id` | 1 |
| Networks / Sites | `EXT-SITE` | `KNetwork` | `SiteID` (network name) | 10 |
| Firewalls (MX) | `EXT-FIREWALL` | `KFirewall` | `device_name` | 11 |
| Switches (MS) | `EXT-SWITCH` | `KSwitch` | `device_name` | 21 |
| Access Points (MR) | `EXT-ACCESS_POINT` | `KAccessPoint` | `device_name` | 117 |
| Clients / Endpoints | `EXT-HOST` | `FlexSystemSample` | `displayName` | ~147 |
| VLANs / Subnets | `EXT-SERVICE` (tag: `subtype=vlan`) | `MerakiVlan` | `service_name` = `vlan-{network_id}-{vlan_id}` | 81 |
| Switch Ports | `EXT-SERVICE` (tag: `subtype=switch_port`) | `MerakiSwitchPort` | `service_name` = `port-{serial}-{portId}` | 1,034 |

**Total entities pushed: 1,404** (18 EXT-HOST still synthesizing at time of writing)

### Key Synthesis Notes
- `EXT-FIREWALL`, `EXT-SWITCH`, `EXT-ACCESS_POINT` synthesize via `provider` field (kentik-firewall / kentik-switch / kentik-cisco-ap)
- `EXT-MERAKI_ORGANIZATION` synthesizes via `instrumentation.provider = kentik` + `instrumentation.name = meraki.organization`
- `EXT-SERVICE` synthesizes via `service_name` attribute (underscore, not dot)
- `EXT-HOST` synthesizes via `displayName` attribute — clients without hostnames fall back to MAC address as name
- All entities tagged `tags.source = topology-maps-app` and `tags.environment = experimental`

---

## Scripts

| Script | Purpose |
|---|---|
| `nr_ingest/phase1_one_switch.py` | Single switch smoke test |
| `nr_ingest/phase1_one_of_each.py` | One entity of each type — validation run |
| `nr_ingest/phase2_all_devices.py` | Full ingest: all 1,422 events across all entity types |
| `nr_ingest/create_workloads.py` | Creates one NR Workload per network (run once) |
| `nr_ingest/create_relationships.py` | Creates user-defined entity relationships (run after full ingest) |
| `nr_ingest/data_source.py` | Loads snapshot from container DB via `docker cp`; falls back to local `data/app.db` |

---

## What Is Done

- [x] Researched NR entity types — chose EXT-* generics over MERAKI_DEVICE (more distinct types = better Service Map filtering)
- [x] Added org as first-class DB entity (`orgs` table, `org_id` FK on `networks`, schema v3)
- [x] Threaded `orgId` through frontend save payload and `load_snapshot()`
- [x] Built ingest scripts reading from live container DB
- [x] Validated each entity type individually (phase1 scripts)
- [x] Pushed all 1,422 events — 1,404 entities synthesized across 7 types
- [x] Created 10 Workloads (one per network), dynamically populated by `tags.network_id`
- [x] Created 1,507 entity relationships across 61 batches — zero errors (2026-04-25)

---

## What Is Next

### 1. Create Entity Relationships (required for Workload map view)

The map view in each Workload is currently empty — entities exist but no edges connect them.
Relationships must be created via NerdGraph `entityRelationshipUserDefinedCreateOrReplace` mutations.

**Planned relationships (~1,500 total):**

| Relationship | From → To | Data Source | Est. Count |
|---|---|---|---|
| `CONTAINS` | Site → Firewall / Switch / AP | `tags.network_id` on each device | ~149 |
| `CONTAINS` | Site → VLAN | `tags.network_id` on each VLAN | 81 |
| `CONTAINS` | Switch → Port | serial encoded in port `service_name` | 1,034 |
| `CONNECTS_TO` | Switch ↔ Switch / Firewall (LLDP) | `l2.edges` where `link_type = lldp` | ~75 |
| `CONNECTS_TO` | Client → AP | `connected_ap` field on endpoint nodes | ~147 |

**Implementation approach:**
1. Query NerdGraph to build a `{identifier → guid}` lookup map for all our entities
2. Walk the topology edges and map each pair to GUIDs
3. Fire batched `entityRelationshipUserDefinedCreateOrReplace` mutations

**Script to create:** `nr_ingest/create_relationships.py`

---

### 2. Verify Workload Map View Works

After relationships are created, open any Workload and check the Map tab.
Expected: devices connected by lines representing L2 topology.

The open question from session research: does NR Service Map render
user-defined relationships between EXT-* entities? Relationships are the first real test of this.

---

### 3. Re-sync Strategy

Currently ingest is manual (run `phase2_all_devices.py` by hand).
Options for keeping NR in sync with the live Meraki state:

- **Scheduled script** — cron job or cloud function running phase2 on a schedule (e.g. every 15 min)
- **Trigger on snapshot save** — hook into the server's `/api/snapshot/save` endpoint to fire ingest after each topology refresh
- **Tag TTL awareness** — entity tags with `tags.` prefix expire after 4 hours (per NR synthesis rules); re-ingest must run at least every 4 hours to keep tags current

---

### 4. Minor Known Issues

- **18 EXT-HOST entities** were still synthesizing at time of last check — expected to resolve automatically
- **Client naming** — clients without hostnames are named by MAC address (e.g. `02:4c:90:0d:93:23`). Could fall back to IP address for slightly more useful names
- **EXT-HOST discoverability** — hosts don't appear in the browsable Entity Explorer sidebar (only findable by name search or NRQL). This is a NR platform limitation for this entity type; Workloads are the practical workaround
