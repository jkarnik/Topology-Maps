# Network Topology Simulator & Visualizer — Design Spec

## Overview

A simulation and visualization tool for a Fortinet SD-Branch retail network. Three integrated components — an SNMP simulator, a topology collector, and an interactive web UI — work together to let users explore, visualize, and manually edit the network topology of a 40,000 sqft, 4-floor retail store.

## Store Profile

- **Size:** 40,000 sqft (4 floors x 10,000 sqft)
- **Daily foot traffic:** ~10,000 guests throughout the day
- **Concurrent guest peak:** ~800–1,000 at any given time
- **Employees:** 90

## Network Infrastructure

| Device | Model | Qty | Role |
|--------|-------|-----|------|
| SD-WAN / Firewall | FortiGate 200G | 2 | Secure Edge & Controller (HA pair) |
| Core Switch | FortiSwitch 1024E | 1 | 10G SFP+ Aggregation |
| Floor Switches | FortiSwitch 448E-FPOE | 4 | 48-port Full PoE (one per floor) |
| Access Points | FortiAP 431K | 56 | Wi-Fi 7 Tri-Radio (14 per floor) |

### Endpoints

| Category | VLAN | Subnet | Device Count |
|----------|------|--------|-------------|
| Payment (PCI) | 10 | 10.10.10.0/24 | 30–50 |
| Operations | 20 | 10.10.20.0/24 | 10–15 |
| Employee Mobility | 30 | 10.10.30.0/23 | 90 |
| Security & Safety | 40 | 10.10.40.0/24 | 40–60 |
| Retail IoT | 50 | 10.10.50.0/23 | 100+ |
| Guest Wi-Fi | 60 | 172.16.0.0/20 | ~800–1,000 concurrent |

---

## Architecture

Monorepo with three modules and clear boundaries. All components run locally — one `docker-compose up` starts everything.

```
┌──────────────────────────────────────────────────────────┐
│                      Monorepo                            │
│                                                          │
│  ┌─────────────┐    SNMP (UDP)    ┌─────────────────┐   │
│  │  Simulator   │◄───────────────│    Collector      │   │
│  │  (pysnmp)    │────────────────►│  (pysnmp client) │   │
│  │              │  GET/WALK/BULK  │                   │   │
│  │  One agent   │                │  Seeds from FG IP  │   │
│  │  per device  │                │  Walks LLDP/ARP    │   │
│  │  (diff ports)│                │  Builds topology   │   │
│  └──────▲───────┘                └────────┬──────────┘   │
│         │                                 │              │
│         │ REST (update                    │ Topology     │
│         │  connections)                   │ data         │
│         │                                 ▼              │
│  ┌──────┴─────────────────────────────────────────────┐  │
│  │              FastAPI Server                         │  │
│  │  - REST API for topology CRUD + connection edits    │  │
│  │  - WebSocket for live topology push to UI           │  │
│  │  - Triggers collector re-poll after edits           │  │
│  └────────────────────────┬───────────────────────────┘  │
│                           │                              │
└───────────────────────────┼──────────────────────────────┘
                            │ WebSocket + REST
                            ▼
                 ┌─────────────────────┐
                 │    React UI          │
                 │  - React Flow graph  │
                 │  - L2 / L3 views     │
                 │  - Connection editor  │
                 │  - Drill-down panels  │
                 └─────────────────────┘
```

### Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| SNMP Simulator | Python, pysnmp | Runs one SNMP agent per device on unique UDP ports |
| Collector | Python, pysnmp (client) | Queries simulator agents, builds topology graph |
| API Server | Python, FastAPI | REST + WebSocket hub between all components |
| UI | React, TypeScript, React Flow | Interactive topology visualization |
| Persistence | SQLite | Topology state and connection history |
| Orchestration | Docker Compose | One-command local startup |

---

## Component 1: SNMP Simulator

### Responsibilities

Simulate every network infrastructure device as a real SNMP agent. Each device gets its own pysnmp agent process listening on a unique UDP port. Responds to standard SNMP v2c GET, GETNEXT, GETBULK, and WALK operations with realistic MIB data. Community string: `public` (read-only).

### Port Assignment

| Device | IP (simulated) | SNMP Port |
|--------|----------------|-----------|
| FortiGate 200G (Primary) | 10.0.0.1 | 10161 |
| FortiGate 200G (Standby) | 10.0.0.2 | 10162 |
| FortiSwitch 1024E (Core) | 10.0.1.1 | 10163 |
| FortiSwitch 448E Floor 1 | 10.0.1.11 | 10164 |
| FortiSwitch 448E Floor 2 | 10.0.1.12 | 10165 |
| FortiSwitch 448E Floor 3 | 10.0.1.13 | 10166 |
| FortiSwitch 448E Floor 4 | 10.0.1.14 | 10167 |

Endpoints (POS, cameras, IoT) are not individual SNMP agents — they appear in their parent switch's ARP and MAC forwarding tables.

APs are discovered via their parent floor switch's LLDP table (physical connection), but **wireless client-to-AP mappings** come from the FortiGate. In real Fortinet deployments, the FortiGate acts as the wireless controller via FortiLink and maintains a table of all managed APs and their connected clients. The FortiGate's SNMP agent includes FORTINET-FORTIGATE-MIB wireless tables (managed AP list + per-AP station/client list) so the collector can query a single device to learn which clients are on which AP.

### Simulated MIB Trees Per Device Type

**FortiGate 200G:**
- SNMPv2-MIB (sysDescr, sysName, sysUpTime, sysObjectID)
- IF-MIB (interfaces: WAN1, WAN2, LAN, HA-link, VLAN sub-interfaces)
- IP-MIB (ipRouteTable — routes to each VLAN subnet)
- RFC1213-MIB (ipNetToMediaTable — ARP entries)
- LLDP-MIB (lldpRemTable — neighbor: Core Switch)
- FORTINET-FORTIGATE-MIB:
  - HA status and peer state
  - **fgWcApTable** — managed AP list (AP name, serial, IP, status, connected client count, parent switch port)
  - **fgWcStaTable** — wireless station/client list per AP (client MAC, IP, SSID, VLAN, signal strength, connected AP ID)

**FortiSwitch 1024E (Core):**
- SNMPv2-MIB (system identity)
- IF-MIB (24 interfaces: 2x 10G uplinks to FortiGates, 4x 1G downlinks to floor switches)
- LLDP-MIB (6 neighbors: 2 FortiGates + 4 floor switches)
- Q-BRIDGE-MIB (VLAN table, VLAN-to-port mappings)
- BRIDGE-MIB (MAC address forwarding table)

**FortiSwitch 448E-FPOE (Floor):**
- SNMPv2-MIB (system identity)
- IF-MIB (48 access ports + 2 uplink ports)
- LLDP-MIB (uplink neighbor: Core Switch; downlink neighbors: APs and LLDP-capable endpoints)
- Q-BRIDGE-MIB (VLAN assignments per port)
- POWER-ETHERNET-MIB (pethPsePortTable — PoE power draw per port)
- BRIDGE-MIB (MAC forwarding table — all connected endpoints)
- RFC1213-MIB (ARP table for endpoint IP-to-MAC resolution)

### Wireless Client Roaming Simulator

A background task within the simulator that makes the wireless environment feel alive by periodically moving clients between APs.

**Behavior:**
- Runs every 3–5 seconds, selects a small random batch of wireless clients (2–5 at a time) to roam
- Updates the FortiGate's `fgWcStaTable` with the new AP assignment for each roaming client
- The collector detects the change on its next poll cycle and pushes updates to the UI

**Roaming rules by device type:**

| Device Type | Same-Floor Roam | Cross-Floor Roam | Rationale |
|-------------|----------------|-----------------|-----------|
| Employee Handhelds (Zebra scanners) | 70% | 30% | Employees move across floors for inventory, restocking, customer assistance |
| VoIP Badges (Vocera) | 60% | 40% | Managers and security roam the entire store frequently |
| Guest Devices | 85% | 15% | Customers mostly browse one department/floor at a time, occasionally move between floors |

**Constraints:**
- A client always roams to an AP that is within the same SSID/VLAN (employee clients stay on the corporate SSID, guests stay on the guest SSID)
- Same-floor roaming picks a different AP on the same floor; cross-floor roaming picks a random AP on an adjacent floor (floor 1↔2, 2↔3, 3↔4 — no floor 1→4 jumps)
- Signal strength (RSSI) value in `fgWcStaTable` is randomized appropriately after a roam — slightly lower immediately after roaming, stabilizing within a poll cycle

### Connection Update API

The simulator exposes an internal REST endpoint (not SNMP) for the API server to push connection changes:

```
POST /simulator/connections
{
  "action": "move",
  "device": "FortiAP-15",
  "from": {"switch": "floor-switch-2", "port": 12},
  "to": {"switch": "floor-switch-1", "port": 6}
}
```

This updates the LLDP neighbor tables, ARP tables, and MAC forwarding tables on all affected switches. The collector discovers the change on its next poll cycle.

---

## Component 2: Collector Agent

### Responsibilities

Discover and continuously maintain the network topology by querying the SNMP simulator. Produces both L2 (physical) and L3 (logical) topology graphs.

### Discovery Process

1. **Seed**: Starts with the primary FortiGate IP (10.0.0.1:10161)
2. **LLDP Walk**: Queries lldpRemTable to discover directly connected neighbors
3. **Recursive Hop**: For each discovered neighbor, queries their LLDP table to find the next layer
4. **ARP/MAC Sweep**: On each switch, queries ARP and MAC forwarding tables to discover non-LLDP wired endpoints (POS, cameras, IoT)
5. **Wireless Client Discovery**: Queries FortiGate's fgWcApTable and fgWcStaTable to map APs → wireless clients (employee handhelds, guest devices). APs' physical connections are already known from floor switch LLDP; this step adds the wireless layer on top.
6. **Route Table**: On FortiGates, queries ipRouteTable to build L3 subnet relationships

### Discovery Order

```
FortiGate (seed)
  ├─ LLDP → Core Switch (10.0.1.1)
  │    ├─ LLDP → FortiGate Standby (10.0.0.2)
  │    ├─ LLDP → Floor Switch 1 (10.0.1.11)
  │    │    ├─ LLDP → FortiAP-1 through FortiAP-14 (physical uplink)
  │    │    └─ ARP/MAC → POS terminals, cameras, IoT on this floor
  │    ├─ LLDP → Floor Switch 2 (10.0.1.12)
  │    │    └─ ... (same pattern)
  │    ├─ LLDP → Floor Switch 3 (10.0.1.13)
  │    │    └─ ...
  │    └─ LLDP → Floor Switch 4 (10.0.1.14)
  │         └─ ...
  └─ Wireless Controller (fgWcApTable + fgWcStaTable)
       ├─ FortiAP-1 → 15 guest clients, 3 employee handhelds
       ├─ FortiAP-2 → 12 guest clients, 4 employee handhelds
       └─ ... (all 56 APs with their wireless clients)
```

### Topology Data Model

**L2 Topology (Physical):**
```
{
  "nodes": [
    {"id": "fg-primary", "type": "firewall", "model": "FortiGate 200G", "ip": "10.0.0.1", "status": "up"},
    {"id": "core-sw", "type": "core_switch", "model": "FortiSwitch 1024E", "ip": "10.0.1.1", "status": "up"},
    {"id": "floor-sw-1", "type": "floor_switch", "model": "FortiSwitch 448E", "ip": "10.0.1.11", "floor": 1, "status": "up"},
    {"id": "ap-1-01", "type": "access_point", "model": "FortiAP 431K", "ip": "10.0.1.101", "floor": 1, "status": "up"},
    {"id": "pos-001", "type": "endpoint", "category": "payment", "mac": "00:1A:2B:...", "ip": "10.10.10.11", "vlan": 10}
  ],
  "edges": [
    {"source": "fg-primary", "target": "core-sw", "source_port": "port5", "target_port": "port1", "speed": "10G", "protocol": "LLDP"},
    {"source": "core-sw", "target": "floor-sw-1", "source_port": "port3", "target_port": "port49", "speed": "1G", "protocol": "LLDP"},
    {"source": "floor-sw-1", "target": "ap-1-01", "source_port": "port1", "target_port": "eth0", "speed": "1G", "protocol": "LLDP"},
    {"source": "floor-sw-1", "target": "pos-001", "source_port": "port15", "target_port": null, "speed": "1G", "protocol": "ARP"}
  ]
}
```

**L3 Topology (Logical):**
```
{
  "subnets": [
    {"id": "vlan-10", "name": "PCI / Payment", "vlan": 10, "cidr": "10.10.10.0/24", "gateway": "10.0.0.1", "device_count": 40},
    {"id": "vlan-20", "name": "Operations", "vlan": 20, "cidr": "10.10.20.0/24", "gateway": "10.0.0.1", "device_count": 12},
    {"id": "vlan-30", "name": "Employee Wi-Fi", "vlan": 30, "cidr": "10.10.30.0/23", "gateway": "10.0.0.1", "device_count": 90},
    {"id": "vlan-40", "name": "Security", "vlan": 40, "cidr": "10.10.40.0/24", "gateway": "10.0.0.1", "device_count": 50},
    {"id": "vlan-50", "name": "Retail IoT", "vlan": 50, "cidr": "10.10.50.0/23", "gateway": "10.0.0.1", "device_count": 110},
    {"id": "vlan-60", "name": "Guest Wi-Fi", "vlan": 60, "cidr": "172.16.0.0/20", "gateway": "10.0.0.1", "device_count": 850}
  ],
  "routes": [
    {"from": "vlan-10", "to": "vlan-20", "via": "fg-primary", "policy": "allow"},
    {"from": "vlan-10", "to": "vlan-60", "via": "fg-primary", "policy": "deny"},
    {"from": "vlan-60", "to": "internet", "via": "fg-primary", "policy": "allow"}
  ]
}
```

### Continuous Polling

- The collector runs as an async background task within the FastAPI process (not a separate service)
- Polls all devices every 5 seconds
- Compares new topology snapshot to previous
- On any change (link up/down, new device, moved device), updates the shared in-memory topology store directly
- The FastAPI WebSocket manager detects store changes and pushes diffs to all connected UI clients

---

## Component 3: FastAPI Server

### Responsibilities

Central coordination hub. Serves the REST API, manages WebSocket connections, and bridges the simulator and collector.

### API Endpoints

**Topology (read):**
- `GET /api/topology/l2` — Full L2 physical topology graph
- `GET /api/topology/l3` — Full L3 logical topology graph
- `GET /api/topology/l2/device/{device_id}` — Drill-down: device detail + connected children
- `GET /api/topology/l3/vlan/{vlan_id}` — Drill-down: VLAN member devices

**Connection Editing (write):**
- `POST /api/connections` — Create or move a connection (forwards to simulator, triggers collector re-poll)
- `DELETE /api/connections/{edge_id}` — Remove a connection

**Device Info:**
- `GET /api/devices` — List all devices with status
- `GET /api/devices/{device_id}` — Device detail (interfaces, metrics, neighbors)
- `GET /api/devices/{device_id}/interfaces` — Interface list with stats (throughput, PoE draw)

**System:**
- `GET /api/status` — Simulator and collector health
- `POST /api/collector/poll` — Trigger immediate re-poll

**WebSocket:**
- `WS /ws/topology` — Live topology updates. Pushes events:
  - `topology_update` — Full or partial topology change
  - `device_status` — Device up/down/degraded
  - `connection_change` — Result of a connection edit
  - `metrics_update` — Interface throughput, PoE draw changes

---

## Component 4: React UI

### Technology

- React 18 with TypeScript
- React Flow for the node-and-edge graph canvas
- WebSocket client for live updates
- Tailwind CSS for styling

### Views

**L2 Physical View (default):**
- Hierarchical layout: FortiGates at top → Core Switch → Floor Switches → APs/Endpoints
- Color-coded by device type (red = firewall, blue = core switch, amber = floor switch, purple = AP)
- Connection lines show port labels and link speed
- Status indicators: green (up), red (down), amber (degraded)
- Click a floor switch to drill down into its 48 ports and connected devices
- Click an AP to see its wireless clients
- Breadcrumb navigation for drill-down path

**L3 Logical View:**
- FortiGate as central gateway at top
- VLAN/subnet blocks arranged below, color-coded by segment
- Lines between VLANs show routing relationships through the FortiGate
- Click a VLAN block to drill into its member devices
- Shows inter-VLAN routing policies (allow/deny)

**Edit Mode:**
- Toggle button in the top bar
- When active, shows an amber banner confirming edit mode
- Drag from a source device port to a target device to create a connection
- Click an existing connection line to disconnect it
- Shows a "Pending Change Preview" panel before applying
- "Apply Change" button triggers the full loop: API → Simulator → Collector → UI refresh (~5 second round-trip)
- "Cancel" discards the pending change

### Detail Panel (right sidebar)

Always visible. Shows contextual information for the selected device:
- Device name, model, IP, status
- Interface list with live throughput stats
- Connected neighbors with port mappings
- PoE power draw (for PoE switches)
- VLAN membership

### Layout and Navigation

- Top bar: app title, L2/L3 toggle, live polling indicator, Edit Mode button
- Main canvas: interactive React Flow graph with pan, zoom, drag
- Right panel: device detail sidebar
- Bottom-left: breadcrumb path for drill-down navigation
- Bottom-right: zoom controls

---

## Data Flow: Connection Edit (Full Loop)

1. User enables Edit Mode in the UI
2. User drags FortiAP-15 from Floor Switch 2 / port 12 to Floor Switch 1 / port 6
3. UI shows pending change preview
4. User clicks "Apply Change"
5. UI sends `POST /api/connections` to FastAPI
6. FastAPI forwards to simulator: `POST /simulator/connections` with move details
7. Simulator updates LLDP tables on Floor Switch 1, Floor Switch 2, and FortiAP-15; updates ARP/MAC tables accordingly
8. FastAPI triggers collector re-poll: `POST /api/collector/poll`
9. Collector queries all affected devices via SNMP, detects the topology change
10. Collector pushes updated topology diff to FastAPI
11. FastAPI pushes `connection_change` event via WebSocket to all connected UI clients
12. UI animates the topology update — FortiAP-15 moves from Floor 2 subtree to Floor 1 subtree

Total round-trip: ~5 seconds.

---

## Simulated Device Counts (Snapshot at Any Given Time)

| Category | Simulated Count | Distribution |
|----------|----------------|-------------|
| Infrastructure (SNMP agents) | 7 | 2 FortiGates + 1 core switch + 4 floor switches |
| Access Points | 56 | 14 per floor, in parent switch LLDP tables |
| POS / Payment | 40 | VLAN 10, wired to floor switches |
| Operations PCs | 12 | VLAN 20, wired to floor switches |
| Employee Handhelds | 90 | VLAN 30, wireless via APs |
| IP Cameras / Security | 50 | VLAN 40, PoE wired to floor switches |
| IoT (signage, sensors, ESL) | 110 | VLAN 50, mixed wired/wireless |
| Guest Devices | ~850 | VLAN 60, wireless via APs (concurrent peak) |

**Total simulated endpoints:** ~1,200 at any snapshot (not 10,000 — that's daily foot traffic).

---

## Project Structure

```
topology-maps/
├── docker-compose.yml
├── Devices.md
├── simulator/
│   ├── __init__.py
│   ├── main.py              # Starts all SNMP agents
│   ├── agent.py             # Single device SNMP agent (pysnmp)
│   ├── devices/
│   │   ├── fortigate.py     # FortiGate MIB data generator
│   │   ├── core_switch.py   # Core switch MIB data generator
│   │   ├── floor_switch.py  # Floor switch MIB data generator
│   │   └── base.py          # Shared MIB builder utilities
│   ├── topology_state.py    # In-memory topology state (connections, devices)
│   ├── api.py               # Internal REST API for connection updates
│   └── requirements.txt
├── collector/
│   ├── __init__.py
│   ├── main.py              # Collector entry point
│   ├── discovery.py         # LLDP/ARP/route walking logic
│   ├── poller.py            # Continuous polling loop
│   ├── topology_builder.py  # Builds L2/L3 graphs from SNMP data
│   └── requirements.txt
├── server/
│   ├── __init__.py
│   ├── main.py              # FastAPI app entry point
│   ├── routes/
│   │   ├── topology.py      # /api/topology/* endpoints
│   │   ├── connections.py   # /api/connections endpoints
│   │   ├── devices.py       # /api/devices/* endpoints
│   │   └── system.py        # /api/status, /api/collector/poll
│   ├── websocket.py         # WebSocket manager
│   ├── models.py            # Pydantic models for API
│   ├── database.py          # SQLite persistence
│   └── requirements.txt
├── ui/
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── TopologyCanvas.tsx    # React Flow canvas
│   │   │   ├── DeviceNode.tsx        # Custom node for each device type
│   │   │   ├── ConnectionEdge.tsx    # Custom edge with port labels
│   │   │   ├── DetailPanel.tsx       # Right sidebar
│   │   │   ├── L3View.tsx            # VLAN/subnet layout
│   │   │   ├── EditMode.tsx          # Connection editor overlay
│   │   │   └── TopBar.tsx            # Header with controls
│   │   ├── hooks/
│   │   │   ├── useTopology.ts        # Fetches and manages topology state
│   │   │   └── useWebSocket.ts       # WebSocket connection and events
│   │   ├── types/
│   │   │   └── topology.ts           # TypeScript types for topology data
│   │   └── utils/
│   │       └── layoutEngine.ts       # Hierarchical layout calculation
│   └── public/
│       └── index.html
└── docs/
    └── superpowers/
        └── specs/
            └── 2026-04-13-network-topology-simulator-design.md
```

---

## Testing Strategy

- **Simulator**: Unit tests verify each device type returns correct OIDs and values. Integration test: walk the full MIB tree and validate structure.
- **Collector**: Unit tests for LLDP/ARP parsing. Integration test: collector against running simulator, verify complete topology is discovered.
- **API Server**: Endpoint tests for all REST routes. WebSocket test: verify topology updates push correctly.
- **UI**: Component tests for DeviceNode, DetailPanel. E2E test: full flow from connection edit to topology update in the browser.
- **Full Loop**: End-to-end test that starts all components, makes a connection edit via the API, and verifies the topology change propagates through simulator → collector → WebSocket → topology response.
