# Phase 1 Design: Meraki Config Collection & Storage

**Status:** Draft
**Date:** 2026-04-22
**Scope:** Phase 1 of a 7-phase Network Configuration Management initiative for the Topology Maps tool

---

## Executive Summary

Build a continuous, change-log-driven pipeline that captures Meraki configuration state across organization, network, and device levels; redacts secrets at ingestion; stores observations in content-addressed SQLite; and exposes a tree-based browser for inspection. Phase 1 is read-only from Meraki's perspective — the tool remains an observability surface, never writing back to source.

This phase establishes the foundation that later phases build on: diff (Phase 2), topology overlay (Phase 3), drift monitoring (Phase 4), compliance (Phase 5), multi-site comparison (Phase 6), and export/revert bundle generation (Phase 7).

Scale target: up to 30,000 devices per organization, backed by Meraki's configuration change log so steady-state cost is 1 API call + a handful of targeted pulls per 30-minute cycle, rather than exhaustive re-polling. Config changes do not require sub-minute detection latency — 30 minutes is well inside the expected operator reaction window.

---

## Goals

1. Continuously capture Meraki config state for Tier 1 and Tier 2 endpoints across org, network, and device levels, with product-type-aware filtering.
2. Use Meraki's configuration change log as the primary drift-detection mechanism, supplemented by a one-time baseline sweep and a weekly anti-drift sweep.
3. Redact secret-bearing fields at ingestion while preserving the ability to detect change through content hashing.
4. Store snapshots in a content-addressed schema that deduplicates unchanged observations and scales to years of history without bloat.
5. Expose a browse surface in the existing React UI: tree + raw JSON viewer + collection status/progress.
6. Design for multi-org at the schema level while keeping the Phase 1 UI scoped to a single active organization.

## Non-Goals (Deferred to Later Phases)

- **Diff engine** and change-timeline UI (Phase 2)
- **Topology overlay** of changes on the L2/L3/Hybrid views (Phase 3)
- **Baseline drift monitor** and drift dashboard (Phase 4)
- **Compliance rule engine** (Phase 5)
- **Multi-site / template comparison** (Phase 6)
- **Export bundles and revert package generation** (Phase 7)
- **Direct writes to Meraki Dashboard** — the tool remains read-only throughout all phases; any feature that requires config change is delivered as an exportable artifact the user uploads manually.

---

## Scope: Config Endpoints to Collect

All endpoints listed are included in Phase 1. Tier labels reflect collection priority and are informational only — both Tier 1 and Tier 2 are fully pulled.

Conditional filters apply:

- **Product-type filtering:** Network-level endpoints are only pulled if the network's `productTypes` array contains the matching product (appliance / switch / wireless / camera / cellularGateway / systemsManager). Device-level endpoints are only pulled for the matching product.
- **SSID enabled filter:** Per-SSID sub-endpoints (firewall, shaping, splash, etc.) are skipped during sweeps when the SSID has `enabled: false`. A reactive catch triggers a pull of the sub-endpoints when a change-log event references that SSID number, regardless of enabled state.
- **Cellular / routing filters:** Cellular firewall rules skipped if no cellular uplink; OSPF / BGP skipped if not enabled.

### Organization-level endpoints

| Area | Endpoint | Tier |
|---|---|---|
| Admins | `GET /organizations/{orgId}/admins` | 1 |
| SAML roles | `GET /organizations/{orgId}/samlRoles` | 1 |
| SAML settings | `GET /organizations/{orgId}/saml` | 1 |
| Login security | `GET /organizations/{orgId}/loginSecurity` | 1 |
| Policy objects | `GET /organizations/{orgId}/policyObjects` | 1 |
| Policy object groups | `GET /organizations/{orgId}/policyObjects/groups` | 1 |
| Config templates | `GET /organizations/{orgId}/configTemplates` | 1 |
| Adaptive policy settings | `GET /organizations/{orgId}/adaptivePolicy/settings` | 2 |
| Adaptive policy ACLs | `GET /organizations/{orgId}/adaptivePolicy/acls` | 2 |
| Adaptive policy groups | `GET /organizations/{orgId}/adaptivePolicy/groups` | 2 |
| Adaptive policy policies | `GET /organizations/{orgId}/adaptivePolicy/policies` | 2 |
| Third-party VPN peers | `GET /organizations/{orgId}/appliance/vpn/thirdPartyVPNPeers` | 1 |
| Org-wide VPN firewall | `GET /organizations/{orgId}/appliance/vpn/vpnFirewallRules` | 1 |
| SNMP (org access) | `GET /organizations/{orgId}/snmp` | 2 |
| Alert profiles | `GET /organizations/{orgId}/alerts/profiles` | 2 |
| Inventory (claimed devices) | `GET /organizations/{orgId}/inventory/devices` | 2 |
| Per-device licensing | `GET /organizations/{orgId}/licenses` | 2 |
| Co-term licensing | `GET /organizations/{orgId}/licensing/coterm/licenses` | 2 |

### Network-level endpoints — generic

| Area | Endpoint | Tier |
|---|---|---|
| Network metadata | `GET /networks/{networkId}` | 1 |
| Network settings | `GET /networks/{networkId}/settings` | 1 |
| Group policies | `GET /networks/{networkId}/groupPolicies` | 1 |
| Syslog servers | `GET /networks/{networkId}/syslogServers` | 1 |
| SNMP (network) | `GET /networks/{networkId}/snmp` | 2 |
| Traffic analysis | `GET /networks/{networkId}/trafficAnalysis` | 2 |
| Netflow | `GET /networks/{networkId}/netflow` | 2 |
| Alert settings | `GET /networks/{networkId}/alerts/settings` | 2 |
| Webhook HTTP servers | `GET /networks/{networkId}/webhooks/httpServers` | 2 |
| Webhook payload templates | `GET /networks/{networkId}/webhooks/payloadTemplates` | 2 |
| Firmware upgrade policy | `GET /networks/{networkId}/firmwareUpgrades` | 2 |
| Floor plans | `GET /networks/{networkId}/floorPlans` | 2 |

### Network-level — MX (appliance)

| Area | Endpoint | Tier |
|---|---|---|
| VLANs | `GET /networks/{networkId}/appliance/vlans` | 1 |
| VLANs settings | `GET /networks/{networkId}/appliance/vlans/settings` | 1 |
| Single LAN (VLANs disabled) | `GET /networks/{networkId}/appliance/singleLan` | 1 |
| Appliance ports | `GET /networks/{networkId}/appliance/ports` | 1 |
| L3 firewall | `GET /networks/{networkId}/appliance/firewall/l3FirewallRules` | 1 |
| L7 firewall | `GET /networks/{networkId}/appliance/firewall/l7FirewallRules` | 1 |
| Inbound firewall | `GET /networks/{networkId}/appliance/firewall/inboundFirewallRules` | 1 |
| Port forwarding | `GET /networks/{networkId}/appliance/firewall/portForwardingRules` | 1 |
| 1:1 NAT | `GET /networks/{networkId}/appliance/firewall/oneToOneNatRules` | 1 |
| 1:many NAT | `GET /networks/{networkId}/appliance/firewall/oneToManyNatRules` | 2 |
| Firewalled services | `GET /networks/{networkId}/appliance/firewall/firewalledServices` | 2 |
| Firewall settings | `GET /networks/{networkId}/appliance/firewall/settings` | 2 |
| Cellular firewall (conditional) | `GET /networks/{networkId}/appliance/firewall/cellularFirewallRules` | 2 |
| Content filtering | `GET /networks/{networkId}/appliance/contentFiltering` | 1 |
| IDS/IPS | `GET /networks/{networkId}/appliance/security/intrusion` | 1 |
| AMP / malware | `GET /networks/{networkId}/appliance/security/malware` | 1 |
| Traffic shaping rules | `GET /networks/{networkId}/appliance/trafficShaping/rules` | 1 |
| Uplink bandwidth | `GET /networks/{networkId}/appliance/trafficShaping/uplinkBandwidth` | 1 |
| SD-WAN uplink selection | `GET /networks/{networkId}/appliance/trafficShaping/uplinkSelection` | 1 |
| Custom performance classes | `GET /networks/{networkId}/appliance/trafficShaping/customPerformanceClasses` | 2 |
| Site-to-site VPN | `GET /networks/{networkId}/appliance/vpn/siteToSiteVpn` | 1 |
| BGP (conditional) | `GET /networks/{networkId}/appliance/vpn/bgp` | 2 |
| Static routes | `GET /networks/{networkId}/appliance/staticRoutes` | 1 |
| Warm spare | `GET /networks/{networkId}/appliance/warmSpare` | 1 |
| Connectivity monitoring | `GET /networks/{networkId}/appliance/connectivityMonitoringDestinations` | 2 |
| Appliance settings | `GET /networks/{networkId}/appliance/settings` | 2 |

### Network-level — MS (switch)

| Area | Endpoint | Tier |
|---|---|---|
| Access policies (802.1X) | `GET /networks/{networkId}/switch/accessPolicies` | 1 |
| ACLs | `GET /networks/{networkId}/switch/accessControlLists` | 1 |
| QoS rules | `GET /networks/{networkId}/switch/qosRules` | 1 |
| QoS order | `GET /networks/{networkId}/switch/qosRules/order` | 1 |
| DSCP→CoS mappings | `GET /networks/{networkId}/switch/dscpToCosMappings` | 2 |
| Switch settings | `GET /networks/{networkId}/switch/settings` | 2 |
| STP | `GET /networks/{networkId}/switch/stp` | 1 |
| Storm control | `GET /networks/{networkId}/switch/stormControl` | 2 |
| MTU | `GET /networks/{networkId}/switch/mtu` | 2 |
| Switch stacks | `GET /networks/{networkId}/switch/stacks` | 1 |
| Port schedules | `GET /networks/{networkId}/switch/portSchedules` | 2 |
| Link aggregations | `GET /networks/{networkId}/switch/linkAggregations` | 1 |
| DHCP server policy | `GET /networks/{networkId}/switch/dhcpServerPolicy` | 1 |
| Multicast | `GET /networks/{networkId}/switch/routing/multicast` | 2 |
| Multicast RPs | `GET /networks/{networkId}/switch/routing/multicast/rendezvousPoints` | 2 |
| OSPF (conditional) | `GET /networks/{networkId}/switch/routing/ospf` | 2 |

### Network-level — MR (wireless)

| Area | Endpoint | Tier |
|---|---|---|
| SSIDs | `GET /networks/{networkId}/wireless/ssids` | 1 |
| RF profiles | `GET /networks/{networkId}/wireless/rfProfiles` | 1 |
| Wireless settings | `GET /networks/{networkId}/wireless/settings` | 1 |
| Bluetooth settings | `GET /networks/{networkId}/wireless/bluetooth/settings` | 2 |
| AP ethernet port profiles | `GET /networks/{networkId}/wireless/ethernet/ports/profiles` | 2 |

### Network-level — Per-SSID sub-endpoints (for `enabled: true` SSIDs, or reactively on change)

| Area | Endpoint | Tier |
|---|---|---|
| Per-SSID L3 firewall | `GET /networks/{networkId}/wireless/ssids/{n}/firewall/l3FirewallRules` | 1 |
| Per-SSID L7 firewall | `GET /networks/{networkId}/wireless/ssids/{n}/firewall/l7FirewallRules` | 1 |
| Per-SSID traffic shaping | `GET /networks/{networkId}/wireless/ssids/{n}/trafficShaping/rules` | 1 |
| Per-SSID splash settings | `GET /networks/{networkId}/wireless/ssids/{n}/splash/settings` | 2 |
| Per-SSID schedules | `GET /networks/{networkId}/wireless/ssids/{n}/schedules` | 2 |
| Per-SSID VPN | `GET /networks/{networkId}/wireless/ssids/{n}/vpn` | 2 |
| Per-SSID device-type group policies | `GET /networks/{networkId}/wireless/ssids/{n}/deviceTypeGroupPolicies` | 2 |
| Per-SSID identity PSKs | `GET /networks/{networkId}/wireless/ssids/{n}/identityPsks` | 2 |

### Network-level — MV (camera), MG (cellular gateway), SM (systems manager)

| Area | Endpoint | Tier | Condition |
|---|---|---|---|
| Camera quality & retention profiles | `GET /networks/{networkId}/camera/qualityRetentionProfiles` | 2 | has camera |
| Camera schedules | `GET /networks/{networkId}/camera/schedules` | 2 | has camera |
| Cellular gateway DHCP | `GET /networks/{networkId}/cellularGateway/dhcp` | 2 | has cellularGateway |
| Cellular gateway subnet pool | `GET /networks/{networkId}/cellularGateway/subnetPool` | 2 | has cellularGateway |
| Cellular gateway uplink | `GET /networks/{networkId}/cellularGateway/uplink` | 2 | has cellularGateway |
| Cellular gateway connectivity monitoring | `GET /networks/{networkId}/cellularGateway/connectivityMonitoringDestinations` | 2 | has cellularGateway |
| SM device policies | `GET /networks/{networkId}/sm/profiles` | 2 | has systemsManager |

### Device-level endpoints

| Area | Endpoint | Tier | Applies to |
|---|---|---|---|
| Device metadata | `GET /devices/{serial}` | 1 | all |
| Management interface | `GET /devices/{serial}/managementInterface` | 1 | all |
| Switch ports | `GET /devices/{serial}/switch/ports` | 1 | MS |
| Switch L3 interfaces | `GET /devices/{serial}/switch/routing/interfaces` | 2 | MS |
| Switch L3 static routes | `GET /devices/{serial}/switch/routing/staticRoutes` | 2 | MS |
| Switch warm spare | `GET /devices/{serial}/switch/warmSpare` | 2 | MS |
| AP radio settings override | `GET /devices/{serial}/wireless/radio/settings` | 1 | MR |
| AP Bluetooth settings | `GET /devices/{serial}/wireless/bluetooth/settings` | 2 | MR |
| MX uplink settings | `GET /devices/{serial}/appliance/uplinks/settings` | 1 | MX |
| Camera quality & retention | `GET /devices/{serial}/camera/qualityAndRetention` | 2 | MV |
| Camera video settings | `GET /devices/{serial}/camera/videoSettings` | 2 | MV |
| Camera sense | `GET /devices/{serial}/camera/sense` | 2 | MV |

### Scale estimates at 5 req/sec rate cap

| Deployment | Filtered endpoint calls (baseline) | Baseline duration |
|---|---|---|
| Small retail (5 networks, 30 devices) | ~350 | ~70 sec |
| Mid enterprise (30 networks, 300 devices) | ~2,500 | ~8 min |
| Large enterprise (200 networks, 2,000 devices) | ~15,000 | ~50 min |
| Very large (500 networks, 30K devices) | ~30–50K | ~2–3 hours |

Steady-state (change-log-driven) load is unaffected by scale: 1 change-log poll + typically 0–50 targeted pulls per 30-minute cycle (range reflects the larger window capturing more change events per cycle).

---

## Architecture

Phase 1 extends the existing Topology Maps services with a new config-collection subsystem. No new service process is introduced; the collector runs as FastAPI background tasks inside the existing `server/` container.

```
                        ┌─────────────────────────────────┐
                        │  Meraki Dashboard API           │
                        └──────────────┬──────────────────┘
                                       │ HTTPS — 5 req/sec per org
                  ┌────────────────────┴────────────────────┐
                  │                                         │
                  ▼                                         ▼
      ┌──────────────────────┐                ┌──────────────────────┐
      │  change_log_poller   │                │   baseline_runner    │
      │  (every 30 min / org)│                │  (on-demand / weekly)│
      └──────────┬───────────┘                └──────────┬───────────┘
                 │                                       │
                 └───────────────┬───────────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   targeted_puller       │
                    │   (endpoint dispatcher  │
                    │    + rate limiter)      │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │      redactor           │  masks secrets,
                    │   (secret masking +     │  computes hashes
                    │    hash generation)     │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │    config_store         │  content-addressed
                    │  (blobs + observations  │  SQLite with dedup
                    │   + change_events)      │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  FastAPI /api/config/*  │  browse + status
                    │  + WebSocket progress   │
                    └────────────┬────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │  React Configs tab      │  tree + JSON viewer
                    │  + CollectionStatusBar  │
                    └─────────────────────────┘
```

### New code layout

| Path | Purpose |
|---|---|
| `server/config_collector/__init__.py` | Package init |
| `server/config_collector/endpoints_catalog.py` | Endpoint definitions, product-type filters, change-log event → endpoint mappings, secret-field catalog |
| `server/config_collector/scanner.py` | Baseline runner and anti-drift sweep orchestrator |
| `server/config_collector/change_log_poller.py` | Per-org 30-minute change-log fetch loop |
| `server/config_collector/targeted_puller.py` | Endpoint fetch dispatcher, coalescing, rate-limit enforcement |
| `server/config_collector/redactor.py` | Secret masking + SHA256 hashing |
| `server/config_collector/store.py` | SQLite access layer for blobs, observations, change events, sweep runs |
| `server/routes/config.py` | REST routes under `/api/config/*` |
| `server/websocket.py` | Extend existing module with `/ws/config` channel |
| `server/meraki_client.py` | Extend with tier 1+2 endpoint getter methods |
| `server/database.py` | Extend `_create_tables` with config tables |
| `ui/src/components/ConfigBrowser/` | New component tree: `ConfigBrowser.tsx`, `ConfigTree.tsx`, `ConfigEntityView.tsx`, `ConfigAreaViewer.tsx`, `CollectionStatusBar.tsx`, `BaselineProgressOverlay.tsx` |
| `ui/src/hooks/useConfigCollection.ts` | Hook for progress/status SSE |
| `ui/src/types/config.ts` | TypeScript types for config data |

### Pagination handling

Meraki paginates large list endpoints via RFC 5988 `Link` headers: a `Link: <url>; rel="next"` header on a response indicates another page. `MerakiClient` is extended with a `_get_paginated(path, params)` helper that transparently follows these headers until exhausted, returning the concatenated list. Each page fetch flows through the same per-org `RateLimiter`, so pagination does not bypass the 5 req/sec cap.

**Endpoints that require pagination in Phase 1 scope:**

| Endpoint | Typical page size | Notes |
|---|---|---|
| `GET /organizations/{id}/configurationChanges` | 100 default, up to 5000 | Default to `perPage=1000`; a busy 30K-device org can easily produce 1000+ events in a 60-min window, so pagination must never be silently truncated |
| `GET /organizations/{id}/inventory/devices` | 1000 default | Paginated when claimed inventory is large |
| `GET /organizations/{id}/networks` | 100000 default | Rarely paginates in practice but supported |
| `GET /organizations/{id}/devices` | 1000 default | Device list enumeration |
| `GET /organizations/{id}/licenses` | 1000 default | Per-device licensing mode only |

**Endpoints NOT paginated in Phase 1 scope** (return a complete object or a small fixed array): all per-network config endpoints (`/appliance/vlans`, `/appliance/firewall/*`, `/wireless/ssids` — always 15 entries, `/switch/accessPolicies`, `/switch/stacks`, etc.) and all per-device config endpoints (`/switch/ports` — capped at ~48 ports, `/wireless/radio/settings`, etc.). These call `_get` directly without pagination overhead.

**Safety: never silently truncate.** If the paginated helper reaches a configurable hard ceiling (`CONFIG_MAX_PAGES`, default 100), it logs an `ERROR` and aborts the entire poll cycle. Silent truncation of the change log would create invisible drift gaps, which is worse than a visible failure that operators can diagnose.

---

## Data Flow

### Flow A: One-time baseline (per organization)

Triggered when an organization is first connected or when a user explicitly requests a re-baseline.

1. User selects org → UI requests baseline preview → server counts expected endpoints using the endpoint catalog and the org's enumerated networks + devices + enabled SSIDs → returns `{estimated_calls, estimated_duration_sec}`.
2. User confirms → `POST /api/config/orgs/{org_id}/baseline` → server creates a row in `config_sweep_runs` with `kind='baseline'`, `status='queued'` → returns the `sweep_run_id` → UI opens a WebSocket to `/ws/config`.
3. The `baseline_runner` task picks up the queued run, sets `status='running'`, and iterates the endpoint catalog:
   - For each endpoint, build concrete URLs for all entities matching its product-type filter (with SSID enabled filter for per-SSID sub-endpoints).
   - Submit URLs to the `targeted_puller`, which enforces the 5 req/sec rate limit per org via the existing `RateLimiter` class.
   - Each response flows through the `redactor` (mask secrets → compute payload SHA256) → `store` (upsert blob if new hash → insert observation row with `source_event='baseline'`).
4. Progress events stream over `/ws/config` using the `sweep.progress` event shape defined in the API Surface section. Emitted at most once per 10 completed calls or once every 2 seconds, whichever comes first.
5. On completion: `status='complete'`, `completed_at=now()`. On failure: `status='failed'` with `error_summary` populated, partial observations preserved.
6. Baseline runs are **resumable at the config-area granularity**: on restart, the runner queries `config_observations` for this sweep_run_id, identifies completed `(entity_id, config_area)` pairs, and skips them.

### Flow B: 30-minute incremental (per organization)

A single `change_log_poller` task per organization runs continuously.

1. Every `CONFIG_CHANGE_LOG_INTERVAL_SECONDS` (default 1800, i.e. 30 min), the poller calls `GET /organizations/{orgId}/configurationChanges?timespan=3600&perPage=1000` (60-minute window for 30-minute overlap against poller downtime). Pagination is followed via `Link` headers until exhausted — see the Pagination section below.
2. For each event returned, the store checks the `config_change_events` unique index `(org_id, ts, network_id, label, old_value, new_value)`. Duplicate events are skipped.
3. New events are inserted and mapped via `endpoints_catalog.event_to_endpoints()`:
   - Event keyed by `page`, `label`, `ssidNumber`, and `clientId` is looked up in a mapping table. Example: `page="Wireless → Access Control"` + `ssidNumber=3` → pull `/wireless/ssids`, `/wireless/ssids/3/firewall/l3FirewallRules`, `/wireless/ssids/3/firewall/l7FirewallRules`.
   - Unmapped events are logged (`WARN`) but do not halt processing — the weekly anti-drift sweep will catch any configs missed by the mapping gap.
4. Endpoint URLs are coalesced: if 10 port-change events hit the same switch, the port-config endpoint is pulled once, not ten times. Coalescing key: `(entity_type, entity_id, config_area, sub_key)`.
5. Each coalesced URL flows through `targeted_puller → redactor → store`, same as baseline. The resulting observation row carries `source_event='change_log'` and `change_event_id` referencing the originating change event.
6. If the fresh hash equals the most recent observation's hash for the same `(org_id, entity_type, entity_id, config_area, sub_key)`, **no new observation row is written**. The data is already correct; we avoid noise in the observation history.
7. WebSocket emits `{type: 'observation.updated', entity_type, entity_id, config_area, observed_at}` so the UI can refresh the relevant pane.

**SSID reactive catch:** When an event's `ssidNumber` is set, the poller triggers pulls of all Tier 1+2 per-SSID sub-endpoints for that SSID number in that network, regardless of whether the SSID is currently `enabled: true`. This ensures that pre-configuration edits to disabled SSIDs are captured.

### Flow C: Weekly anti-drift sweep (per organization)

Runs on a cron schedule (default: Sunday 02:00 local time, `CONFIG_WEEKLY_SWEEP_CRON`).

1. Identical iteration to the baseline runner, except each observation row is annotated based on hash comparison:
   - If the fresh hash matches the most recent stored hash → write observation with `source_event='anti_drift_confirm'` (proof-of-life marker; useful for Phase 4 drift monitoring to distinguish "stable" from "untested").
   - If the fresh hash differs from the most recent stored hash → write observation with `source_event='anti_drift_discrepancy'`. This flags a config that changed without a corresponding change-log event, indicating a potential change-log gap that should be investigated.
2. Discrepancies are additionally logged to application logs at `WARN` level for operator visibility.

### Flow D: Manual targeted refresh

User-initiated refresh of a single entity or config area, exposed via UI "↻" buttons per area.

1. `POST /api/config/orgs/{org_id}/refresh` with body `{entity_type, entity_id, config_area?}`.
2. Server enqueues a targeted pull. If `config_area` is omitted, all Tier 1+2 areas for that entity are pulled.
3. Same redact → store pipeline. Observation rows written with `source_event='manual_refresh'`.
4. Idempotent: if an identical refresh is already in-flight, the endpoint returns the existing task id.

---

## Storage Schema

Four new tables added to the existing SQLite database (`data/topology.db`). WAL mode is already enabled. All timestamps are UTC ISO-8601 strings.

```sql
-- Content-addressed blob store: one row per unique redacted payload
CREATE TABLE config_blobs (
    hash         TEXT PRIMARY KEY,       -- sha256 of the canonicalized, redacted payload
    payload      TEXT NOT NULL,          -- JSON blob, secrets masked (see Redaction section)
    byte_size    INTEGER NOT NULL,
    first_seen_at TEXT NOT NULL
);

-- Every observation writes a row here; hash points into config_blobs
CREATE TABLE config_observations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id         TEXT NOT NULL,
    entity_type    TEXT NOT NULL,        -- 'org' | 'network' | 'device' | 'ssid' | 'switch_port'
    entity_id      TEXT NOT NULL,        -- orgId | networkId | serial | "networkId:ssidNum" | "serial:portId"
    config_area    TEXT NOT NULL,        -- canonical area key, e.g. 'appliance_vlans', 'wireless_ssid_l3_firewall'
    sub_key        TEXT,                 -- optional secondary key (ssid number, port id, etc.)
    hash           TEXT NOT NULL REFERENCES config_blobs(hash),
    observed_at    TEXT NOT NULL,
    source_event   TEXT NOT NULL,        -- 'baseline' | 'change_log' | 'anti_drift_confirm' | 'anti_drift_discrepancy' | 'manual_refresh'
    change_event_id INTEGER,             -- FK into config_change_events when source_event='change_log'
    sweep_run_id   INTEGER,              -- FK into config_sweep_runs when part of a sweep
    -- Denormalized hot columns, populated at insert time by the redactor
    name_hint      TEXT,                 -- pulled from payload.name if present
    enabled_hint   INTEGER,              -- 0/1/NULL from payload.enabled if present
    FOREIGN KEY (change_event_id) REFERENCES config_change_events(id),
    FOREIGN KEY (sweep_run_id) REFERENCES config_sweep_runs(id)
);

CREATE INDEX idx_obs_entity_latest ON config_observations(
    org_id, entity_type, entity_id, config_area, sub_key, observed_at DESC
);
CREATE INDEX idx_obs_area_time ON config_observations(config_area, observed_at DESC);
CREATE INDEX idx_obs_hash ON config_observations(hash);

-- Raw Meraki change-log events, used to drive incremental flow and seed Phase 2 timeline
CREATE TABLE config_change_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id         TEXT NOT NULL,
    ts             TEXT NOT NULL,
    admin_id       TEXT,
    admin_name     TEXT,
    admin_email    TEXT,
    network_id     TEXT,
    network_name   TEXT,
    ssid_number    INTEGER,
    ssid_name      TEXT,
    page           TEXT,
    label          TEXT,
    old_value      TEXT,
    new_value      TEXT,
    client_id      TEXT,
    client_description TEXT,
    raw_json       TEXT NOT NULL,        -- full event as received, for future-proofing
    fetched_at     TEXT NOT NULL,
    UNIQUE(org_id, ts, network_id, label, old_value, new_value)
);

CREATE INDEX idx_events_org_ts ON config_change_events(org_id, ts DESC);
CREATE INDEX idx_events_network ON config_change_events(network_id, ts DESC);

-- Sweep run metadata for baseline, anti-drift, and incremental cycles
CREATE TABLE config_sweep_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id          TEXT NOT NULL,
    kind            TEXT NOT NULL,       -- 'baseline' | 'anti_drift' | 'incremental'
    status          TEXT NOT NULL,       -- 'queued' | 'running' | 'complete' | 'failed' | 'cancelled'
    started_at      TEXT,
    completed_at    TEXT,
    total_calls     INTEGER,
    completed_calls INTEGER DEFAULT 0,
    failed_calls    INTEGER DEFAULT 0,
    skipped_calls   INTEGER DEFAULT 0,   -- counts SSID-disabled and product-type-filtered skips
    error_summary   TEXT
);

CREATE INDEX idx_runs_org_kind ON config_sweep_runs(org_id, kind, started_at DESC);
```

### Canonical `config_area` keys

To keep the schema consistent, each endpoint maps to a stable `config_area` string. Examples:

| Endpoint | `config_area` |
|---|---|
| `/networks/{id}/appliance/vlans` | `appliance_vlans` |
| `/networks/{id}/appliance/firewall/l3FirewallRules` | `appliance_firewall_l3` |
| `/networks/{id}/wireless/ssids` | `wireless_ssids` |
| `/networks/{id}/wireless/ssids/{n}/firewall/l3FirewallRules` | `wireless_ssid_l3_firewall` (with `sub_key = n`) |
| `/devices/{serial}/switch/ports` | `switch_device_ports` |
| `/organizations/{id}/admins` | `org_admins` |

A central mapping lives in `server/config_collector/endpoints_catalog.py` so there's a single source of truth.

### Entity identity

Meraki-assigned immutable IDs are primary keys. Mutable attributes (names, tags, addresses) are fields in the payload blob, not identity.

| Entity | `entity_id` format |
|---|---|
| Organization | `orgId` (e.g. `"123456"`) |
| Network | `networkId` (e.g. `"L_648..."`) |
| Device | `serial` (e.g. `"Q2AB-CDEF-GHIJ"`) |
| SSID | `"{networkId}:{ssidNumber}"` |
| Switch port | `"{serial}:{portId}"` |

A renamed device is the same entity (same serial) and the rename manifests as a diff in the `devices` config area — which is the intended behavior.

---

## Secret Redaction

Several Meraki config endpoints return secret-bearing fields (PSKs, RADIUS shared secrets, VPN PSKs, SNMP community strings, webhook secrets). Storing these plaintext in SQLite would create unacceptable liability. The tool MUST mask all known secret fields before they reach the storage layer, while preserving the ability to *detect* value changes via hashing.

### Redaction catalog

A central Python data structure in `server/config_collector/endpoints_catalog.py` maps each `config_area` to a list of JSON paths pointing at secret fields. Initial catalog:

| `config_area` | JSON paths to redact |
|---|---|
| `wireless_ssids` | `[*].psk`, `[*].radiusServers[*].secret`, `[*].radiusAccountingServers[*].secret` |
| `wireless_ssid_identity_psks` | `[*].passphrase` |
| `appliance_site_to_site_vpn` | `peers[*].secret`, `peers[*].ikev2.secret` |
| `network_snmp` | `communityString`, `users[*].passphrase` |
| `org_snmp` | `v2CommunityString`, `users[*].passphrase` |
| `network_webhooks_http_servers` | `[*].sharedSecret` |
| `network_syslog_servers` | (no redaction — IPs are infra-sensitive but not secret) |

This catalog is the authoritative list of known secret fields. It is reviewed on a quarterly cadence and updated whenever Meraki adds new endpoints.

### Redaction flow

For each response, the redactor:

1. Walks the JSON structure using the catalog entries for that `config_area`.
2. For each matching path, computes `sha256(original_value)` and replaces the value with a sentinel object: `{"_redacted": true, "_hash": "<sha256>"}`.
3. Serializes the redacted structure with deterministic key ordering (canonical JSON) to ensure identical inputs produce identical output regardless of Meraki response ordering.
4. Computes `sha256(canonical_serialized_payload)` as the blob hash.
5. Returns `(redacted_payload, blob_hash, extracted_hot_columns)` to the store layer.

The `_hash` on a redacted field lets the diff engine (Phase 2) detect "secret value changed" without ever storing the plaintext. Consumers render this as "Secret changed on <date>" instead of showing values.

### Regex-guard test (fail-safe)

A unit test in `server/tests/test_redactor_guard.py` runs every recorded Meraki response fixture through the redactor and asserts:

- No top-level or nested string value matches any of the following regex patterns in the final stored payload:
  - Field-name heuristics: keys containing `(?i)(psk|passphrase|password|secret|shared[-_]?key|community[-_]?string|token|api[-_]?key)` MUST have values that are either `null`, `""`, or a `_redacted` sentinel object.
  - Value-shape heuristics: no string value matches the pattern for a typical 40-character Meraki API key (`[0-9a-f]{40}`) or typical PSK lengths (8–63 printable chars following a field name that looks like a credential).

The test fails the build if any new Meraki response fixture introduces a field that looks like a secret but isn't in the redaction catalog. This forces the catalog to stay current as Meraki evolves its API.

### Admin PII handling

Admin emails and names in `/organizations/{orgId}/admins` are retained unredacted in the payload. They are needed for the change-log timeline to attribute "who changed what." Display is gated at the UI layer behind a future per-user permission (not implemented in Phase 1; all UI viewers see admin identity for now, matching Meraki Dashboard's own behavior).

### Threat model notes

- The SQLite file remains sensitive (contains admin PII, config details, infra IPs), but it contains no WPA2 PSKs, VPN PSKs, RADIUS secrets, or SNMP community strings. This significantly improves the security posture compared to storing raw Meraki responses.
- The change-log endpoint itself **does** return `oldValue`/`newValue` for secret fields in some cases. These values are redacted the same way during change-event ingestion: if the `label` matches a known secret label (`"PSK"`, `"Passphrase"`, `"RADIUS secret"`, etc.), `old_value` and `new_value` are replaced with `"***REDACTED***"` before insert, and a `_hash` companion is stored in `raw_json`.

---

## API Surface

All endpoints live under `/api/config/*` and return JSON. WebSocket channel at `/ws/config`.

### REST endpoints

```
GET    /api/config/orgs
       → list orgs with collection status
       Response: [{
         org_id, name, baseline_state: 'none'|'in_progress'|'complete'|'failed',
         last_baseline_at, last_anti_drift_at, last_incremental_at,
         observation_count, active_sweep_run_id
       }]

POST   /api/config/orgs/{org_id}/baseline
       → start a baseline sweep
       Response: { sweep_run_id, estimated_calls, estimated_duration_sec }
       Idempotent: returns existing run_id if one is active

POST   /api/config/orgs/{org_id}/sweep
       → trigger a manual anti-drift sweep (same shape as baseline)
       Response: { sweep_run_id, estimated_calls, estimated_duration_sec }

POST   /api/config/orgs/{org_id}/refresh
       Body: { entity_type, entity_id, config_area? }
       → targeted refresh of a single entity (optionally a single area)
       Response: { task_id, expected_calls }

GET    /api/config/orgs/{org_id}/status
       → current collection status for the org
       Response: {
         baseline_state, last_sync, active_sweep: { run_id, kind, progress },
         change_log_poller: { last_poll_at, last_event_ts, error_count_24h }
       }

GET    /api/config/orgs/{org_id}/tree
       → hierarchical tree for the browser UI
       Response: {
         org: { id, name, config_areas: [...] },
         networks: [{
           id, name, product_types, config_areas: [...],
           ssids: [{ number, name, enabled, config_areas: [...] }],
           devices: [{ serial, name, model, product_type, config_areas: [...] }]
         }]
       }
       "config_areas" lists areas that have at least one stored observation.

GET    /api/config/entities/{entity_type}/{entity_id}
       Query params: org_id (required)
       → all config areas + latest observation for one entity
       Response: {
         entity_type, entity_id, org_id,
         areas: [{
           config_area, sub_key?, observed_at, source_event,
           name_hint, enabled_hint, hash,
           payload  -- fully inlined redacted JSON
         }]
       }

GET    /api/config/entities/{entity_type}/{entity_id}/history
       Query params: org_id, config_area?, limit?=100, before?
       → observation list, newest first
       Response: {
         observations: [{
           id, config_area, sub_key, observed_at, source_event,
           change_event_id?, hash, name_hint, enabled_hint
         }],
         has_more, next_cursor
       }
       Payloads not inlined; use /api/config/blobs/{hash} to fetch if needed.
       Phase 2 diff engine will consume this endpoint.

GET    /api/config/blobs/{hash}
       → redacted JSON payload by hash
       Response: { hash, payload, byte_size, first_seen_at }

GET    /api/config/change-events
       Query params: org_id, network_id?, limit?=100, before?
       → raw change-log events, newest first
       Response: { events: [...], has_more, next_cursor }
       Phase 2 timeline will consume this endpoint.
```

### WebSocket channel `/ws/config`

Server pushes events of the following shapes:

```
{ type: 'sweep.started',    sweep_run_id, org_id, kind, total_calls }
{ type: 'sweep.progress',   sweep_run_id, completed_calls, total_calls, current_entity, current_area, eta_sec }
{ type: 'sweep.completed',  sweep_run_id, org_id, duration_sec, observations_written }
{ type: 'sweep.failed',     sweep_run_id, org_id, error_summary }
{ type: 'observation.updated', org_id, entity_type, entity_id, config_area, sub_key, observed_at, source_event }
{ type: 'change_event.new', org_id, event_id, network_id, label, ts }
```

Clients subscribe by org via a query param: `/ws/config?org_id=123456`.

### Existing endpoints — minor touches

- `server/routes/meraki.py` gains nothing new; config endpoints live in their own router.
- `server/main.py` registers the new `config` router and starts a background task per connected org for `change_log_poller`.

---

## UI Surface

A new "Configs" workspace added alongside the existing topology views. Selected via the existing `SourceSelector` dropdown or a top-level tab.

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ [Configs ▼] [Source: Meraki Live ▼]  [Org: Acme Corp ▼]             │
│ ● Synced 3 min ago  |  Baseline complete  |  [Run full sweep]  ↻    │
├──────────────────────────┬──────────────────────────────────────────┤
│ Tree                     │ Entity: Store 42 / Switch MS225-48LP-01  │
│                          │ ─────────────────────────────────────    │
│ ▾ Org configs            │   ▾ Device metadata (last: 3 min ago) ↻ │
│   • Admins               │     { name: "...", tags: [...], ... }    │
│   • Policy objects       │   ▾ Switch ports (last: 9 min ago)    ↻ │
│   • SAML roles           │     [ 48 ports as collapsible JSON ]    │
│   • Config templates     │   ▸ Management interface                 │
│ ▾ Networks               │                                          │
│   ▾ Store 42             │                                          │
│     ▾ Appliance          │                                          │
│       • VLANs            │                                          │
│       • L3 firewall      │                                          │
│     ▾ Wireless           │                                          │
│       • SSIDs (4 of 15)  │                                          │
│       • RF profiles      │                                          │
│     ▾ Devices            │                                          │
│       • MX85-SDWAN-01    │                                          │
│       • MS225-48LP-01    │                                          │
└──────────────────────────┴──────────────────────────────────────────┘
```

### Components

| Component | Responsibility |
|---|---|
| `ConfigBrowser.tsx` | Top-level page; owns org selection, split layout |
| `CollectionStatusBar.tsx` | Top strip: org dropdown, status chip, action buttons (Run sweep, Refresh current) |
| `ConfigTree.tsx` | Left pane; hierarchical tree with lazy expansion per network; fetches `/api/config/orgs/{id}/tree` |
| `ConfigEntityView.tsx` | Right pane; renders config areas for the selected entity via `/api/config/entities/.../` |
| `ConfigAreaViewer.tsx` | Collapsible JSON viewer per area, with a "↻ Refresh" button that calls `/api/config/orgs/{org_id}/refresh` |
| `BaselineProgressOverlay.tsx` | Modal shown during baseline/sweep runs; live progress bar, current entity, ETA |

### State & hooks

| Hook | Purpose |
|---|---|
| `useConfigOrgs()` | Fetches org list + collection status; auto-polls every 30s |
| `useConfigTree(orgId)` | Fetches tree for the active org; refreshes on WebSocket `observation.updated` |
| `useConfigEntity(entityType, entityId, orgId)` | Fetches entity detail; refreshes on WebSocket for that entity |
| `useConfigCollection(orgId)` | Subscribes to `/ws/config?org_id=...`; exposes progress state and toast events |

### JSON viewer choice

The right-pane JSON rendering uses a collapsible tree component. Exact library is a Phase-1 implementation detail — options include `react-json-view`, `@uiw/react-json-view`, or a small custom component. Must support: collapse/expand per node, string/number/boolean/null/array/object typing, theming to match the existing Tailwind palette, and 100K+ line performance without blocking the UI thread.

### Accessibility and polish expectations

- Keyboard navigation across the tree (arrow keys to expand/collapse, `/` to focus search).
- Progress overlay is announced to screen readers via `aria-live="polite"`.
- Status chip colors map to the existing palette (green = healthy, yellow = in-progress, red = failed, gray = never baselined).
- Reuses the progressive-refresh feedback pattern from the existing `RefreshOverlay` component for visual consistency.

---

## Configuration

Phase 1 introduces the following environment variables, each with a sensible default so fresh deployments work without tuning.

| Env var | Default | Purpose |
|---|---|---|
| `MERAKI_API_KEY` | (existing) | Meraki Dashboard API key |
| `CONFIG_RATE_LIMIT_REQUESTS_PER_SEC` | `5` | Hard cap on API rate per org (must stay ≤ Meraki's 10 req/sec limit; 5 leaves headroom for other integrations sharing the key) |
| `CONFIG_CHANGE_LOG_INTERVAL_SECONDS` | `1800` | How often the change-log poller runs per org (30 min — config change detection does not require sub-minute latency) |
| `CONFIG_CHANGE_LOG_TIMESPAN_SECONDS` | `3600` | Lookback window per poll (60 min). With a 30-min interval, this gives a 30-min overlap between consecutive polls, which tolerates poller downtime up to 30 min without event loss. |
| `CONFIG_CHANGE_LOG_PER_PAGE` | `1000` | Page size for `configurationChanges` pagination. Meraki allows up to 5000; 1000 is a conservative default that keeps individual response payloads small without excessive round trips. |
| `CONFIG_MAX_PAGES` | `100` | Hard ceiling on paginated fetches per call. Exceeding this aborts the poll with an `ERROR` log to prevent silent truncation. |
| `CONFIG_WEEKLY_SWEEP_CRON` | `0 2 * * 0` | Anti-drift sweep schedule (Sunday 02:00 by default) |
| `CONFIG_BASELINE_CONCURRENCY` | `3` | Max concurrent endpoint fetches per org during baseline/sweep (bounded by rate limit anyway) |
| `CONFIG_ENABLE_AUTO_POLLER` | `true` | Allow disabling the change-log poller for testing |

---

## Testing Strategy

### Unit tests

| Test | Purpose |
|---|---|
| `test_redactor_paths.py` | Verifies each catalog entry correctly masks its JSON paths on recorded fixtures |
| `test_redactor_guard.py` | Regex-heuristic scan of all recorded fixtures; fails if any secret-looking field escapes redaction |
| `test_canonical_json.py` | Confirms deterministic serialization: same input in different key order → same hash |
| `test_endpoints_catalog.py` | Sanity: every endpoint has a `config_area`, product-type filter, and either a static or generated URL pattern |
| `test_event_to_endpoints.py` | Change-log event mapping: given a fixture event, asserts the correct endpoint set is computed |
| `test_store.py` | Blob dedup, observation insert, hash comparison, hot-column population |

### Integration tests

| Test | Purpose |
|---|---|
| `test_baseline_e2e.py` | Runs baseline against a recorded fixture org (mocked HTTP client), verifies all Tier 1+2 endpoints produce observations |
| `test_incremental_e2e.py` | Seeds a baseline, injects a simulated change-log event, verifies targeted pull writes a new observation with matching `change_event_id` |
| `test_ssid_reactive.py` | Injects an event with `ssidNumber=9` where SSID 9 is disabled; verifies sub-endpoints are pulled anyway |
| `test_anti_drift.py` | Pre-seeds an observation, mocks a differing fresh response, verifies `source_event='anti_drift_discrepancy'` |
| `test_resume_baseline.py` | Interrupts a baseline mid-way; restarts; verifies completed areas are skipped and remaining areas pulled |

### Contract tests

Fixtures are recorded Meraki Dashboard API responses stored as JSON under `server/tests/fixtures/meraki/`. No live API calls in CI. Fixtures are refreshed manually via a recorder script (`server/tests/fixtures/refresh_fixtures.py`) that an operator runs with a staging API key.

### Load / scale test

One scripted test (`test_scale_10k.py`) generates a synthetic org with 10K devices and 200 networks, runs a full baseline with fixture responses, and asserts:

- Storage footprint remains below a threshold (indicative of working dedup).
- Observation query for "latest state of entity X" returns in < 50 ms.
- Memory footprint of the collector process stays below 500 MB.

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Change log has gaps for certain programmatic or system-initiated changes | Medium | Weekly anti-drift sweep flags discrepancies with `source_event='anti_drift_discrepancy'`; operator can investigate |
| Secret-field catalog goes stale as Meraki adds endpoints | High (over time) | Regex-guard test fails the build on any secret-looking value escaping redaction; quarterly catalog review |
| Large-org baseline takes hours; user aborts or process restarts | Medium | Baselines are resumable at `(entity_id, config_area)` granularity via `sweep_run_id` checkpointing |
| Rate-limit contention with other API consumers sharing the same key | Medium | 5 req/sec cap leaves 50% headroom below Meraki's 10 req/sec limit; respect `429` with exponential backoff + jitter |
| SQLite write contention at change-log-driven ingestion rate | Low | WAL mode enabled; batch observation inserts per coalesce cycle (default 50 rows per transaction) |
| Downtime exceeds change-log retention (31 days) | Low | On reconnection, orphan detection compares `last_poll_at` to now; if > 25 days, auto-trigger a baseline re-run |
| Meraki changes response shape for an endpoint, breaking redaction paths | Medium | Redactor path walker is lenient (missing paths are silently ignored); regex-guard test catches new unredacted secrets |
| Admin PII retained in `config_change_events.raw_json` | Known limitation | Document clearly; Phase 2+ may add a retention policy (auto-purge events older than N days) |
| User mistakes a baseline re-run for data loss | Low | Baseline re-runs are additive — new observations added, never existing rows deleted; UI explicitly says "adds a new full snapshot, does not replace history" |

---

## Open Questions

These are explicitly deferred and do not block Phase 1 implementation. Captured here for the follow-on phase specs:

1. **Phase 2 diff edge case:** How should the diff view render the "SSID enabled = false → true" transition, when the reactive catch simultaneously pulls sub-endpoints for the first time? Candidates: show the full enable-time config as "initial state" with no diff, or retroactively synthesize an empty baseline and diff against it.
2. **Phase 4 drift attribution:** In the drift dashboard, when an entity drifts from its golden snapshot, should the UI preferentially show the originating change-log event (if any) as the "reason" for the drift, or treat drift as a separate orthogonal signal?
3. **Phase 7 export format:** Should the revert bundle generator produce a literal Meraki-API-shaped `PUT` payload (fastest to apply, tied to current API shape), or a more portable declarative YAML (easier to version-control, requires translation at apply time)?
4. **Change-event retention policy:** Meraki keeps 31 days. Should we extend retention indefinitely in our own store, or enforce a matching 31-day ceiling? Impacts compliance posture and storage footprint.
5. **Multi-org parallelism:** At what number of concurrent orgs does the background-task model become insufficient and warrant a separate worker process? Currently expected ceiling is 10-20 orgs per deployment before this question matters.

---

## Follow-On Phases (Context Only)

Phase 1 is the foundation for a multi-phase Network Configuration Management initiative. Each subsequent phase will get its own design doc. Summarized here so Phase 1 decisions can be evaluated against the downstream trajectory.

### Phase 2 — Diff Engine & Change Timeline
- Structural (field-level) diff between any two observations of the same `(entity, config_area, sub_key)`.
- Change-log timeline view: chronological feed of admin-made changes across the org, filterable by entity, admin, date.
- Consumes `/api/config/entities/.../history` and `/api/config/change-events`.

### Phase 3 — Topology Overlay
- Overlay change markers on the existing L2, L3, and Hybrid topology views.
- "Time-scrubber" to view topology-as-of-date using the observation history.
- Per-node click opens Phase 2 diff for that entity.

### Phase 4 — Baseline & Drift Monitor
- Pin any observation as a "golden" baseline for an entity.
- Scheduled drift comparison: computes diff between current observation and pinned baseline.
- Drift dashboard showing all entities deviating from their baseline, with severity scoring.

### Phase 5 — Compliance Rule Engine
- Declarative rules ("guest SSID must have client isolation enabled", "no port in VLAN 10 without 802.1X").
- Pass/fail dashboard per rule, per network, per device.
- Rule library with prebuilt Tier 1 rules (PCI-relevant, common best practices).

### Phase 6 — Multi-Site & Template Comparison
- Save any config subtree as a reusable template (stored locally, not pushed to Meraki config templates).
- Side-by-side comparison of two networks ("how does Store 42 differ from Store 7?").
- Coverage dashboard: which networks have which config areas populated.

### Phase 7 — Export & Revert Bundles
- Per-entity JSON export ("download this observation").
- Per-network / per-org bundle export for external version control (git-sync).
- "Revert bundle" generator: given a past observation, produces a Meraki-upload-ready artifact the user manually applies via Dashboard or the Meraki CLI. **Tool never writes to Meraki directly.**
- Format decision (literal API shape vs portable YAML) is an open question for the Phase 7 spec.

---

## Approval

This design is ready for user review. On approval, the next step is to invoke the `superpowers:writing-plans` skill to produce an implementation plan with concrete task breakdown, ordering, and checkpoints.

---

## Post-ship amendments (2026-04-23)

The following implementation details diverged from the spec after Phase 1 shipped. The spec's architectural intent is unchanged; these notes document what was built.

### `GET /api/config/orgs` — Meraki-first discovery

**Spec said:** The endpoint returns orgs from local DB tables (`config_sweep_runs`, `config_observations`). On a fresh install the list would be empty until a baseline ran.

**Shipped:** `list_orgs()` calls Meraki `GET /organizations` on every request. Meraki-discovered orgs appear with `baseline_state='none'` even before any local data exists, so the org dropdown is populated immediately after entering a valid API key. Local-only orgs (key rotated, org removed from Meraki) are still appended from the DB to preserve history access.

### `POST /baseline` and `POST /sweep` — fire-and-forget handlers

**Spec said:** The handlers were described in terms of the baseline running and returning a `sweep_run_id`. The spec was silent on whether the HTTP response waited for the sweep to complete.

**Shipped:** Both handlers are explicitly fire-and-forget. The sweep_run row is created synchronously (so the `sweep_run_id` is stable and returnable), the HTTP response is sent immediately, and `asyncio.create_task()` dispatches the work. `total_calls` in the sweep row is initially `NULL` and filled in by an `update_sweep_total_calls(conn, run_id, total)` helper once the runner has enumerated the full work set. This prevents very-large-org baselines from blocking the HTTP response for hours.

### Tree deduplication — `GROUP BY` + `MAX(name_hint)`

**Spec said:** The tree endpoint returns "one entry per entity" (implied de-duplicate). The implementation detail was unspecified.

**Shipped:** The query uses `GROUP BY entity_id` with `MAX(name_hint)`. SQL `MAX` ignores `NULL`, so when some observations for the same entity carry a non-null `name_hint` and others carry `NULL`, the non-null value wins. A `SELECT DISTINCT entity_id, name_hint` would return two rows (one for each name_hint variant), which is incorrect.

### Device → network mapping via inventory API

**Spec said:** The tree `devices` array under each network assumed devices were associated to networks via observation metadata.

**Shipped:** Device-to-network association is resolved at tree-render time by calling Meraki `GET /organizations/{id}/devices` (inventory endpoint). This is authoritative and avoids the case where a device observed under one network has since been moved to another. Best-effort: if the API is unreachable, devices with no mapping are omitted from the per-network device lists.

### `CollectionStatusBar` button guard

**Spec said:** The "Start baseline" button should appear when no baseline exists; the "Run full sweep" button otherwise.

**Shipped:** The condition `hasBaselined = status?.baseline_state !== 'none'` evaluates to `true` when `status` is `null` (because `null?.baseline_state` is `undefined`, and `undefined !== 'none'` is `true`). Fixed to `hasBaselined = !!status && status.baseline_state !== 'none'`.

### Empty config area filtering

**Spec said:** The `ConfigEntityView` renders all config areas for the selected entity.

**Shipped:** Areas whose payload is recursively empty — `[]`, `{}`, `{"rules": []}`, deeply nested empty collections — are hidden from the card list, with a footer showing how many were hidden. The check preserves areas whose payload is a primitive, `null`, or contains any `{"_redacted": true}` sentinel (a secret is present and should be visible). This avoids cluttering the view with Meraki endpoints that returned empty data for a given network/device type.







