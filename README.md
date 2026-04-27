# Topology Maps — Project Overview

> **Audience:** PMs, developers, and AI assistants picking up this codebase.  
> **Purpose:** Explains what the system does, every external API it calls, every internal API it exposes, and how the pieces fit together — without needing to read the source.

---

## 1. What This System Does

Topology Maps is a **read-only network observability platform** for Cisco Meraki environments. It does three things:

### 1a. Live topology visualisation (SNMP path)
A background **collector** polls a simulated Fortinet network via SNMP every 5 seconds, walking LLDP neighbor tables and ARP/MAC forwarding tables starting from a FortiGate seed device. It builds an L2 physical graph (nodes = devices, edges = LLDP links) and an L3 logical graph (subnets, VLANs, routes) which are pushed to the React UI over a WebSocket. This path is used for local demo/development via Docker.

### 1b. Live topology visualisation (Meraki API path)
The same React UI can switch to **Meraki live mode**, where it directly queries the FastAPI server which in turn calls the Meraki Dashboard API v1. Device inventory, link-layer topology, VLAN data, wireless client associations, and switch port statuses are fetched and rendered as an interactive React Flow canvas.

### 1c. Network Configuration Management (NCM)
A full config-collection pipeline pulls **~80 Meraki API endpoints** per org/network/device (firewalls, switch settings, wireless profiles, VPNs, policies, etc.), stores content-addressed blobs in SQLite, and tracks every configuration change. Features:
- **Baseline sweep** — full initial collection of all config endpoints
- **Anti-drift sweep** — re-pull changed endpoints on a schedule
- **Change-log poller** — watches `GET /organizations/{org_id}/configurationChanges` and reactively re-pulls affected areas
- **Diff engine** — field-level JSON diff between any two config snapshots
- **Templates** — promote one network's config as a "golden template"
- **Multi-site comparison** — diff any two networks side-by-side across all config areas
- **Template scoring** — score every network's compliance against a golden template

### 1d. New Relic ingest (offline scripts)
A set of standalone Python scripts under `nr_ingest/` push Meraki topology data into New Relic as custom entities (switches, APs, firewalls, VLANs, switch ports, clients) using the NerdGraph API and Events API. These scripts run locally against the live SQLite DB, not inside Docker.

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Docker Compose                                                           │
│                                                                           │
│  ┌─────────────────┐   SNMP/UDP    ┌─────────────────────────────────┐  │
│  │   simulator     │ ◄──────────── │           server                │  │
│  │  :8001 (REST)   │               │          :8000 (FastAPI)        │  │
│  │  :10161-10167   │               │                                 │  │
│  │  (SNMP agents)  │               │  collector   config_collector   │  │
│  └─────────────────┘               │  (SNMP poll) (Meraki NCM)       │  │
│                                    └──────────────┬──────────────────┘  │
│                                                   │ WebSocket + REST      │
│                                    ┌──────────────▼──────────────────┐  │
│                                    │           ui  :80               │  │
│                                    │    React + Vite + React Flow    │  │
│                                    └─────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────┘

External:  server ──HTTPS──► api.meraki.com/api/v1
           nr_ingest ──HTTPS──► api.newrelic.com (NerdGraph + Events)

Storage:   data/app.db  (SQLite, volume-mounted, shared by server + nr_ingest)
```

**Key source directories:**

| Path | Role |
|---|---|
| `server/` | FastAPI app — REST routes, WebSocket, lifespan |
| `server/routes/` | Route modules: topology, devices, meraki, config, simulation, system |
| `server/config_collector/` | NCM pipeline: scanner, poller, diff engine, store, redactor |
| `server/meraki_client.py` | All Meraki API calls (rate-limited async HTTP client) |
| `server/meraki_transformer.py` | Converts Meraki API responses into L2/L3 topology models |
| `collector/` | SNMP discovery + continuous poller |
| `simulator/` | Fake SNMP agents + REST API for controlling topology state |
| `nr_ingest/` | Standalone NR push scripts (run outside Docker) |
| `ui/src/components/` | React UI: canvas, panels, config browser, network filter |
| `server/database.py` | SQLite connection + NCM schema migrations |
| `server/db.py` | Topology snapshot read/write (legacy path) |

---

## 3. Vendor APIs Called

### 3a. Cisco Meraki Dashboard API v1

**Base URL:** `https://api.meraki.com/api/v1`  
**Auth:** `Authorization: Bearer <MERAKI_API_KEY>` (env var)  
**Rate limit:** 5 req/s (enforced client-side via `server/rate_limiter.py`)  
**Pagination:** RFC 5988 `Link: <url>; rel="next"` headers, followed automatically  
**Client:** `server/meraki_client.py` — all calls go through `MerakiClient`

> **Read-only constraint:** The app never writes to Meraki. Every call is a `GET`.

#### Topology & device inventory (used by the topology UI)

| Method | Endpoint | Data extracted |
|---|---|---|
| GET | `/organizations` | Org IDs, names |
| GET | `/organizations/{org_id}/devices` | All devices: serial, model, name, network, product type, lat/lng |
| GET | `/organizations/{org_id}/devices/availabilities` | Per-device online/offline/alerting/dormant status |
| GET | `/organizations/{org_id}/devices/uplinks/addresses/byDevice` | Per-uplink public IP, gateway, DNS, assignment mode |
| GET | `/organizations/{org_id}/networks` | Network IDs, names, product types |
| GET | `/networks/{network_id}/topology/linkLayer` | Physical link-layer graph (nodes + links) |
| GET | `/networks/{network_id}/appliance/vlans` | VLAN IDs, subnets, names |
| GET | `/networks/{network_id}/wireless/ssids` | SSID names, auth modes, enabled flags |
| GET | `/devices/{serial}/clients` | Clients seen in last 5 min: MAC, IP, hostname, usage |
| GET | `/devices/{serial}/switch/ports/statuses` | Per-port status, speed, VLAN, errors |
| GET | `/networks/{network_id}/switch/stacks` | Switch stack members |

#### Config collection endpoints (used by NCM pipeline — ~80 total)

Grouped by scope. All go through `server/config_collector/endpoints_catalog.py`.

**Org-level** (`scope=org`)

| Endpoint | Config area key | What it captures |
|---|---|---|
| `/organizations/{org_id}/admins` | `org_admins` | Admin accounts and roles |
| `/organizations/{org_id}/samlRoles` | `org_saml_roles` | SAML role mappings |
| `/organizations/{org_id}/saml` | `org_saml` | SAML enabled/disabled |
| `/organizations/{org_id}/loginSecurity` | `org_login_security` | Password policies, 2FA settings |
| `/organizations/{org_id}/policyObjects` | `org_policy_objects` | Named IP objects for firewall rules |
| `/organizations/{org_id}/policyObjects/groups` | `org_policy_object_groups` | Groups of policy objects |
| `/organizations/{org_id}/configTemplates` | `org_config_templates` | Template definitions |
| `/organizations/{org_id}/adaptivePolicy/settings` | `org_adaptive_policy_settings` | Adaptive policy on/off |
| `/organizations/{org_id}/adaptivePolicy/acls` | `org_adaptive_policy_acls` | Adaptive ACL rules |
| `/organizations/{org_id}/adaptivePolicy/groups` | `org_adaptive_policy_groups` | SGT groups |
| `/organizations/{org_id}/adaptivePolicy/policies` | `org_adaptive_policy_policies` | SGT policy pairs |
| `/organizations/{org_id}/appliance/vpn/thirdPartyVPNPeers` | `org_appliance_vpn_third_party_peers` | Third-party VPN peer configs |
| `/organizations/{org_id}/appliance/vpn/vpnFirewallRules` | `org_appliance_vpn_firewall` | VPN firewall rules |
| `/organizations/{org_id}/snmp` | `org_snmp` | SNMP community strings, trap hosts |
| `/organizations/{org_id}/alerts/profiles` | `org_alerts_profiles` | Alert profiles |
| `/organizations/{org_id}/inventory/devices` | `org_inventory_devices` | Hardware inventory (serial, model, claimed status) |
| `/organizations/{org_id}/licenses` | `org_licenses_per_device` | Per-device license assignments |
| `/organizations/{org_id}/licensing/coterm/licenses` | `org_licenses_coterm` | Co-term license pool |
| `/organizations/{org_id}/configurationChanges` | _(change log poller only)_ | Who changed what, when, on which dashboard page |

**Network-level** (`scope=network`, product-type filtered where noted)

| Endpoint | Config area key | Product filter | What it captures |
|---|---|---|---|
| `/networks/{id}` | `network_metadata` | — | Name, timezone, tags, enrollment |
| `/networks/{id}/settings` | `network_settings` | — | Local status page, remote status page |
| `/networks/{id}/groupPolicies` | `network_group_policies` | — | Bandwidth / firewall group policies |
| `/networks/{id}/syslogServers` | `network_syslog_servers` | — | Syslog destinations |
| `/networks/{id}/snmp` | `network_snmp` | — | Per-network SNMP settings |
| `/networks/{id}/trafficAnalysis` | `network_traffic_analysis` | — | Traffic analysis mode |
| `/networks/{id}/netflow` | `network_netflow` | — | NetFlow collector settings |
| `/networks/{id}/alerts/settings` | `network_alerts_settings` | — | Alert recipients and thresholds |
| `/networks/{id}/webhooks/httpServers` | `network_webhooks_http_servers` | — | Webhook receiver URLs |
| `/networks/{id}/webhooks/payloadTemplates` | `network_webhooks_payload_templates` | — | Webhook payload templates |
| `/networks/{id}/firmwareUpgrades` | `network_firmware_upgrades` | — | Scheduled firmware upgrade config |
| `/networks/{id}/floorPlans` | `network_floor_plans` | — | Floor plan images and geo-anchors |
| `/networks/{id}/appliance/vlans` | `appliance_vlans` | appliance | VLAN IDs, subnets, DHCP settings |
| `/networks/{id}/appliance/vlans/settings` | `appliance_vlans_settings` | appliance | VLANs enabled flag |
| `/networks/{id}/appliance/singleLan` | `appliance_single_lan` | appliance | Single-LAN mode config |
| `/networks/{id}/appliance/ports` | `appliance_ports` | appliance | MX port assignments |
| `/networks/{id}/appliance/firewall/l3FirewallRules` | `appliance_firewall_l3` | appliance | Outbound L3 firewall rules |
| `/networks/{id}/appliance/firewall/l7FirewallRules` | `appliance_firewall_l7` | appliance | Application-layer firewall rules |
| `/networks/{id}/appliance/firewall/inboundFirewallRules` | `appliance_firewall_inbound` | appliance | Inbound firewall rules |
| `/networks/{id}/appliance/firewall/portForwardingRules` | `appliance_firewall_port_forwarding` | appliance | Port forwarding / NAT |
| `/networks/{id}/appliance/firewall/oneToOneNatRules` | `appliance_firewall_one_to_one_nat` | appliance | 1:1 NAT |
| `/networks/{id}/appliance/firewall/oneToManyNatRules` | `appliance_firewall_one_to_many_nat` | appliance | 1:many NAT |
| `/networks/{id}/appliance/firewall/firewalledServices` | `appliance_firewall_firewalled_services` | appliance | ICMPv6 / ICMP / BGP exposure |
| `/networks/{id}/appliance/firewall/settings` | `appliance_firewall_settings` | appliance | Spoofing protection |
| `/networks/{id}/appliance/firewall/cellularFirewallRules` | `appliance_firewall_cellular` | appliance | Cellular uplink firewall rules |
| `/networks/{id}/appliance/contentFiltering` | `appliance_content_filtering` | appliance | URL / category blocks |
| `/networks/{id}/appliance/security/intrusion` | `appliance_security_intrusion` | appliance | IDS/IPS mode and ruleset |
| `/networks/{id}/appliance/security/malware` | `appliance_security_malware` | appliance | Anti-malware settings |
| `/networks/{id}/appliance/trafficShaping/rules` | `appliance_traffic_shaping_rules` | appliance | Per-app bandwidth limits |
| `/networks/{id}/appliance/trafficShaping/uplinkBandwidth` | `appliance_uplink_bandwidth` | appliance | Per-uplink bandwidth caps |
| `/networks/{id}/appliance/trafficShaping/uplinkSelection` | `appliance_uplink_selection` | appliance | SD-WAN uplink preference rules |
| `/networks/{id}/appliance/trafficShaping/customPerformanceClasses` | `appliance_custom_performance_classes` | appliance | Custom latency/loss thresholds |
| `/networks/{id}/appliance/vpn/siteToSiteVpn` | `appliance_site_to_site_vpn` | appliance | Hub/spoke topology, subnets advertised |
| `/networks/{id}/appliance/vpn/bgp` | `appliance_vpn_bgp` | appliance | BGP peering over VPN |
| `/networks/{id}/appliance/staticRoutes` | `appliance_static_routes` | appliance | Static routes |
| `/networks/{id}/appliance/warmSpare` | `appliance_warm_spare` | appliance | HA warm-spare config |
| `/networks/{id}/appliance/connectivityMonitoringDestinations` | `appliance_connectivity_monitoring` | appliance | WAN health check targets |
| `/networks/{id}/appliance/settings` | `appliance_settings` | appliance | Client tracking, deployment mode |
| `/networks/{id}/switch/accessPolicies` | `switch_access_policies` | switch | 802.1x / MAB access policies |
| `/networks/{id}/switch/accessControlLists` | `switch_acls` | switch | Switch ACL rules |
| `/networks/{id}/switch/qosRules` | `switch_qos_rules` | switch | QoS classification rules |
| `/networks/{id}/switch/qosRules/order` | `switch_qos_order` | switch | QoS rule evaluation order |
| `/networks/{id}/switch/dscpToCosMappings` | `switch_dscp_to_cos` | switch | DSCP → CoS mapping table |
| `/networks/{id}/switch/settings` | `switch_settings` | switch | VLAN management, power mgmt |
| `/networks/{id}/switch/stp` | `switch_stp` | switch | STP mode and priorities |
| `/networks/{id}/switch/stormControl` | `switch_storm_control` | switch | Broadcast/multicast storm limits |
| `/networks/{id}/switch/mtu` | `switch_mtu` | switch | MTU setting |
| `/networks/{id}/switch/stacks` | `switch_stacks` | switch | Stack memberships |
| `/networks/{id}/switch/portSchedules` | `switch_port_schedules` | switch | Named port schedules |
| `/networks/{id}/switch/linkAggregations` | `switch_link_aggregations` | switch | LAG configurations |
| `/networks/{id}/switch/dhcpServerPolicy` | `switch_dhcp_server_policy` | switch | DHCP server allow/block policy |
| `/networks/{id}/switch/routing/multicast` | `switch_multicast` | switch | Multicast settings |
| `/networks/{id}/switch/routing/multicast/rendezvousPoints` | `switch_multicast_rps` | switch | PIM RP addresses |
| `/networks/{id}/switch/routing/ospf` | `switch_ospf` | switch | OSPF areas and redistribution |
| `/networks/{id}/wireless/ssids` | `wireless_ssids` | wireless | SSID auth, encryption, VLAN, splash |
| `/networks/{id}/wireless/rfProfiles` | `wireless_rf_profiles` | wireless | Band steering, min bitrate, channel width |
| `/networks/{id}/wireless/settings` | `wireless_settings` | wireless | Meshing, LED, location analytics |
| `/networks/{id}/wireless/bluetooth/settings` | `wireless_bluetooth` | wireless | BLE beacon config |
| `/networks/{id}/wireless/ethernet/ports/profiles` | `wireless_ap_port_profiles` | wireless | AP wired port profiles |

**SSID-level** (`scope=ssid`, per enabled SSID in wireless networks)

| Endpoint | Config area key | What it captures |
|---|---|---|
| `/networks/{id}/wireless/ssids/{n}/firewall/l3FirewallRules` | `wireless_ssid_l3_firewall` | Per-SSID L3 rules |
| `/networks/{id}/wireless/ssids/{n}/firewall/l7FirewallRules` | `wireless_ssid_l7_firewall` | Per-SSID app-layer rules |
| `/networks/{id}/wireless/ssids/{n}/trafficShaping/rules` | `wireless_ssid_traffic_shaping` | Per-SSID bandwidth shaping |
| `/networks/{id}/wireless/ssids/{n}/splash/settings` | `wireless_ssid_splash` | Captive portal / splash page |
| `/networks/{id}/wireless/ssids/{n}/schedules` | `wireless_ssid_schedules` | SSID availability schedule |
| `/networks/{id}/wireless/ssids/{n}/vpn` | `wireless_ssid_vpn` | SSID VPN concentrator |
| `/networks/{id}/wireless/ssids/{n}/deviceTypeGroupPolicies` | `wireless_ssid_device_type_policies` | Device-type policy overrides |
| `/networks/{id}/wireless/ssids/{n}/identityPsks` | `wireless_ssid_identity_psks` | Identity PSK list |

**Device-level** (`scope=device`, product-type filtered)

| Endpoint | Config area key | Product filter | What it captures |
|---|---|---|---|
| `/devices/{serial}` | `device_metadata` | — | Name, address, notes, tags |
| `/devices/{serial}/managementInterface` | `device_management_interface` | — | VLAN, static IP on mgmt port |
| `/devices/{serial}/switch/ports` | `switch_device_ports` | switch | Per-port config (VLAN, PoE, STP, 802.1x) |
| `/devices/{serial}/switch/routing/interfaces` | `switch_routing_interfaces` | switch | L3 SVI interfaces |
| `/devices/{serial}/switch/routing/staticRoutes` | `switch_routing_static_routes` | switch | Device-level static routes |
| `/devices/{serial}/switch/warmSpare` | `switch_device_warm_spare` | switch | Warm spare role |
| `/devices/{serial}/wireless/radio/settings` | `wireless_radio_settings` | wireless | Per-radio channel, power |
| `/devices/{serial}/wireless/bluetooth/settings` | `wireless_device_bluetooth` | wireless | Per-AP BLE settings |
| `/devices/{serial}/appliance/uplinks/settings` | `appliance_device_uplinks` | appliance | Per-uplink WAN settings |
| `/devices/{serial}/camera/qualityAndRetention` | `camera_quality_retention` | camera | Video quality + retention policy |
| `/devices/{serial}/camera/videoSettings` | `camera_video_settings` | camera | Resolution, motion detection |
| `/devices/{serial}/camera/sense` | `camera_sense` | camera | MV Sense analytics |

### 3b. New Relic APIs (nr_ingest scripts only)

| API | Endpoint | Used for |
|---|---|---|
| NerdGraph (GraphQL) | `https://api.newrelic.com/graphql` | Create/update entities, create relationships, create workloads |
| Events API | `https://insights-collector.newrelic.com/v1/accounts/{id}/events` | Push custom event types (MerakiOrganization, KSwitch, KFirewall, etc.) |

Auth: `NR_API_KEY` env var (user API key), `NR_ACCOUNT_ID` env var.

### 3c. SNMP (simulator path only)

The `collector/` package uses `pysnmp` to walk devices on `127.0.0.1:10161–10167`. OIDs queried:

| OID | What it reads |
|---|---|
| `1.3.6.1.2.1.1.1.0` / `.5.0` | sysDescr / sysName |
| `1.0.8802.1.1.2.1.4.1.1.*` | LLDP remote table (neighbor chassis, port, name) |
| `1.3.6.1.2.1.4.22.1.*` | ARP table (IP ↔ MAC) |
| `1.3.6.1.2.1.17.4.3.1.*` | MAC forwarding table |
| `1.3.6.1.4.1.12356.101.14.4.4.1.*` | FortiGate AP table |
| `1.3.6.1.4.1.12356.101.14.4.5.1.*` | FortiGate wireless station table |
| `1.3.6.1.2.1.4.21.1.*` | IP route table |

---

## 4. Internal REST & WebSocket API

All routes are served by FastAPI on port 8000. The UI runs on port 80 (nginx proxy) and calls the server directly during development (`vite.config.ts` proxies `/api` and `/ws` to `localhost:8000`).

### 4a. SNMP topology routes (`/api/topology`, `/api/devices`)

These serve data from the in-memory SNMP collector — only populated when the simulation is running.

| Method | Path | Description |
|---|---|---|
| GET | `/api/topology/l2` | Full L2 physical graph: `{ nodes: [...], edges: [...] }` |
| GET | `/api/topology/l2/device/{device_id}` | Device drill-down: device + its neighbours + connected edges |
| GET | `/api/topology/l3` | Full L3 logical graph: `{ subnets: [...], routes: [...] }` |
| GET | `/api/topology/l3/vlan/{vlan_id}` | All devices in a VLAN: `{ subnet, devices: [...] }` |
| GET | `/api/devices` | Device list: id, type, model, ip, status, floor, category |
| GET | `/api/devices/{device_id}` | Full device detail including interfaces |
| GET | `/api/devices/{device_id}/interfaces` | Interface list with stats |

### 4b. Meraki live-topology routes (`/api/meraki`)

These proxy to the Meraki Dashboard API on demand. Require `MERAKI_API_KEY`.

| Method | Path | Description |
|---|---|---|
| GET | `/api/meraki/status` | Validate API key; returns org names/IDs |
| GET | `/api/meraki/networks` | List all networks for the first org |
| GET | `/api/meraki/topology/l2?network={id}` | L2 graph for a network (devices + LLDP links + stacks, no clients) |
| GET | `/api/meraki/topology/l2/clients?network={id}` | Wireless clients only; extend the L2 graph with client nodes |
| GET | `/api/meraki/topology/device-details?network={id}` | Serial-keyed map of `{ clients, switch_ports }` for every device |
| GET | `/api/meraki/topology/l3?network={id}` | L3 graph: VLANs/subnets per network |
| GET | `/api/meraki/devices/{serial}` | Per-device clients + switch port statuses |
| POST | `/api/meraki/refresh?network={id}` | **SSE stream** — progressive 4-phase refresh: discovery → topology → clients → complete |
| GET | `/api/meraki/cache/load` | Load persisted topology snapshot from SQLite |
| POST | `/api/meraki/cache/save` | Save topology snapshot to SQLite (user-triggered) |

**SSE refresh phases** (event stream from `POST /api/meraki/refresh`):

| Phase | Payload |
|---|---|
| `discovery` | `device_count`, `network_count`, `estimated_seconds` |
| `topology` | Per-network nodes/edges, progress index, `remaining_seconds` |
| `clients` | `client_counts` map (serial → count) |
| `complete` | Full `l2` + `l3` payloads |

### 4c. Config (NCM) routes (`/api/config`)

| Method | Path | Description |
|---|---|---|
| GET | `/api/config/orgs` | Orgs visible to the API key + local-only history orgs; includes `observation_count`, `baseline_state` |
| GET | `/api/config/orgs/{org_id}/status` | Baseline state, last sync timestamp, active sweep run |
| POST | `/api/config/orgs/{org_id}/baseline` | Start (or resume) a full baseline sweep; returns `sweep_run_id` immediately |
| POST | `/api/config/orgs/{org_id}/sweep` | Start an anti-drift sweep; idempotent if one is already running |
| POST | `/api/config/refresh` | Manually re-pull a single entity+area: `{ entity_type, entity_id, config_area? }` |
| GET | `/api/config/orgs/{org_id}/observations` | Latest config observations for an entity; query params: `entity_type`, `entity_id` |
| GET | `/api/config/orgs/{org_id}/history` | Observation history with diff markers; params: `entity_type`, `entity_id` |
| GET | `/api/config/blob/{hash}` | Raw JSON config blob by content hash |
| GET | `/api/config/diff` | Field-level diff between two blobs; params: `hash_a`, `hash_b` |
| GET | `/api/config/events` | Change events log; params: `org_id`, optional `entity_type`/`entity_id` |
| GET | `/api/config/templates?org_id=` | List golden templates for an org |
| POST | `/api/config/templates` | Promote a network's current config as a template: `{ org_id, name, network_id }` |
| DELETE | `/api/config/templates/{template_id}` | Delete a template |
| GET | `/api/config/templates/{template_id}/scores?org_id=` | Score every network against a template (% match per config area) |
| GET | `/api/config/compare/networks?org_id=&network_a=&network_b=` | Side-by-side diff of two networks across all config areas |
| GET | `/api/config/coverage?org_id=` | Coverage report: which config areas have been collected for each entity |

### 4d. WebSocket channels

| Path | Direction | Messages |
|---|---|---|
| `/ws/topology` | Server → client | `{ type: "topology_update", l2: {...}, l3: {...} }` — pushed on every SNMP poll cycle that produces a change |
| `/ws/config?org_id={id}` | Server → client | Config sweep progress events: `{ event_type, sweep_run_id, config_area, entity_id, status, ... }` — pushed during baseline and anti-drift sweeps |

### 4e. System / simulation routes

| Method | Path | Description |
|---|---|---|
| GET | `/api/status` | Health of server, SNMP collector, and simulator |
| POST | `/api/simulation/start` | Start the SNMP poller (auto-stops after 10 min) |
| POST | `/api/simulation/stop` | Stop the SNMP poller immediately |
| GET | `/api/simulation/status` | Running state, uptime, auto-shutdown countdown |

---

## 5. Config Collection Pipeline (NCM)

The pipeline lives in `server/config_collector/`. It is the most complex subsystem.

```
Meraki API
    │
    ▼
endpoints_catalog.py  ← single source of truth for all ~80 endpoint specs
    │   expand_for_org() → yields concrete URL jobs (url, config_area, scope, entity_id)
    ▼
scanner.py
  run_baseline()       → pulls every URL job, stores blobs + observations
  run_anti_drift_sweep() → re-pulls all URL jobs, compares hashes, records changes
    │
    ▼
store.py              ← all SQLite reads/writes
  config_blobs        → content-addressed storage (SHA-256 hash → JSON payload)
  config_observations → latest + history per (org, entity_type, entity_id, config_area, sub_key)
  config_change_events → Meraki change-log events (who, what page, when)
  config_sweep_runs   → sweep lifecycle (queued → running → complete/failed)
  config_templates    → golden template metadata
  config_template_areas → per-area blobs for a template
    │
    ▼
change_log_poller.py  → polls GET /organizations/{id}/configurationChanges every 60s
  event_to_endpoints() (in endpoints_catalog.py) maps dashboard page → config_areas to re-pull
  targeted_puller.py  → re-pulls only the affected areas for affected entities
    │
    ▼
diff_engine.py        → field-level diff between two JSON blobs
  returns DiffResult(changes: list[Change], unchanged_count: int)
  Change = { path, old_value, new_value, change_type: added|removed|changed }
    │
    ▼
WebSocket broadcast   → progress events pushed to UI during sweeps
```

**Redaction** (`redactor.py`, `redaction_catalog.py`): sensitive fields (PSK passwords, RADIUS secrets, API keys) are scrubbed from blobs before storage. The catalog lists field paths by config area.

**Canonical JSON** (`canonical_json.py`): blobs are normalized (keys sorted, floats rounded) before hashing so cosmetic API response variations don't generate false diffs.

**Hashing** (`hashing.py`): SHA-256 of the canonical JSON string. Identical config = identical hash = no new blob written.

---

## 6. New Relic Ingest (`nr_ingest/`)

Standalone scripts, run manually outside Docker. They read from the same SQLite DB the server writes to.

```
data_source.py       → copies DB from container via `docker cp`, falls back to data/app.db
phase1_one_switch.py → smoke test: push one switch entity
phase1_one_of_each.py → one entity per device type (org, network, MX, MS, MR, client, VLAN, port)
phase2_all_devices.py → full push of all devices across all entity types
create_relationships.py → create NR relationships (e.g. switch CONTAINS port, network CONTAINS device)
create_workloads.py  → create NR workloads (one per Meraki network/site)
```

**Entity model in New Relic:**

| Meraki data | NR entity type | NR event type | Identifier field |
|---|---|---|---|
| Org | `EXT-MERAKI_ORGANIZATION` | `MerakiOrganization` | `org_id` |
| Network/site | `EXT-SITE` | `KNetwork` | `SiteID` (network name) |
| MX firewall | `EXT-FIREWALL` | `KFirewall` | `device_name` |
| MS switch | `EXT-SWITCH` | `KSwitch` | `device_name` |
| MR access point | `EXT-ACCESS_POINT` | `KAccessPoint` | `device_name` |
| Client/endpoint | `EXT-HOST` | `FlexSystemSample` | `displayName` (hostname or MAC) |
| VLAN | `EXT-SERVICE` (tag: `subtype=vlan`) | `MerakiVlan` | `service_name = vlan-{network_id}-{vlan_id}` |
| Switch port | `EXT-SERVICE` (tag: `subtype=switch_port`) | `MerakiSwitchPort` | `service_name = port-{serial}-{portId}` |

Synthesis notes: `EXT-FIREWALL/SWITCH/ACCESS_POINT` use the `provider` field (kentik-firewall / kentik-switch / kentik-cisco-ap). `EXT-MERAKI_ORGANIZATION` uses `instrumentation.provider=kentik` + `instrumentation.name=meraki.organization`. `EXT-HOST` synthesizes via `displayName`.

---

## 7. SQLite Schema

All tables live in `data/app.db` (path overridable via `DB_PATH` env var in tests).

**Topology snapshot** (legacy, managed by `server/db.py`):
- `topology_snapshots` — raw JSON blobs of L2/L3 topology, loaded/saved by the UI

**NCM tables** (managed by `server/database.py`):

| Table | Purpose |
|---|---|
| `config_blobs` | `(hash, payload)` — content-addressed config storage |
| `config_observations` | `(org_id, entity_type, entity_id, config_area, sub_key, hash, observed_at, source_event, name_hint)` — latest + full history |
| `config_change_events` | `(org_id, ts, page, admin_email, network_id, serial, ssid_number, raw_json)` — Meraki change log |
| `config_sweep_runs` | `(org_id, kind, status, started_at, completed_at, total_calls, completed_calls)` |
| `config_templates` | `(org_id, name, network_id, network_name, created_at)` |
| `config_template_areas` | `(template_id, config_area, sub_key, blob_hash)` |

---

## 8. UI Components

The React app (`ui/src/`) uses React Flow for graph rendering, Tailwind CSS for styling, and Vite for bundling.

| Component | What it renders |
|---|---|
| `TopologyCanvas.tsx` | Main React Flow canvas; SNMP or Meraki topology graph |
| `DeviceNode.tsx` | Custom node: device icon + status badge |
| `ConnectionEdge.tsx` | Custom edge: link type label + protocol colour |
| `DetailPanel.tsx` | Right-hand panel: device info, interfaces, clients (SNMP mode) |
| `MerakiDetailPanel.tsx` | Right-hand panel: Meraki device info, clients, switch ports |
| `L3View.tsx` | VLAN/subnet list and L3 topology view |
| `HybridView.tsx` | Toggles between SNMP and Meraki data sources |
| `NetworkFilter.tsx` | Dropdown to filter topology to a single Meraki network |
| `SourceSelector.tsx` | Switch between SNMP simulator and Meraki live data |
| `TopBar.tsx` | Header: source selector, refresh button, status indicators |
| `RefreshOverlay.tsx` | Progress overlay shown during SSE refresh phases |
| `ConfigBrowser/` | Full NCM UI: org selector, entity browser, diff viewer, templates, comparison, scoring |

---

## 9. Development Quick-Start

```bash
# Full stack (simulator + server + UI)
docker compose up --build

# Backend tests only (no Docker needed)
python3 -m pytest

# UI hot-reload dev server (port 5173, proxies API to localhost:8000)
cd ui && npm run dev
```

**Required env vars** (in `.env` at project root):

| Variable | Required for |
|---|---|
| `MERAKI_API_KEY` | Meraki topology UI + NCM pipeline |
| `NR_API_KEY` | nr_ingest scripts |
| `NR_ACCOUNT_ID` | nr_ingest scripts |

**Testing:** 289 pytest tests covering the NCM pipeline. Tests use an in-memory SQLite DB (monkeypatched via `server.database.DB_PATH`). Never rely on `data/app.db` in tests.

---

## 10. Key Design Constraints

- **Read-only from all vendor APIs.** No writes to Meraki or any vendor API. Exports and observability only.
- **No mock DB in tests.** Tests must hit a real (temp) SQLite instance — mocked DB caused a prior production incident when a migration broke silently.
- **Config blobs are immutable.** A blob is written once and never updated; observations point to blobs by hash.
- **Rate limiter is shared.** All Meraki API calls (topology + NCM) share the 5 req/s token bucket in `MerakiClient`. Running a baseline sweep while the topology UI is open will slow both.
- **SNMP simulator is demo-only.** The `simulator/` service is a fake Fortinet topology for local development. It has no Meraki equivalent — Meraki topology always comes from the real API.

