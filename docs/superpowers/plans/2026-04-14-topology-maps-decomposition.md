# Network Topology Simulator — Master Decomposition

> **For agentic workers:** This is the master decomposition document. Each sub-plan below is a self-contained implementation plan in its own file. Execute them **in order** — each plan builds on the previous. Use superpowers:subagent-driven-development or superpowers:executing-plans for each sub-plan.

**Goal:** Build a Fortinet SD-Branch network topology simulator with SNMP agents, a topology collector, FastAPI server, and React UI — all runnable locally via `docker-compose up`.

**Source spec:** `docs/superpowers/specs/2026-04-13-network-topology-simulator-design.md`

---

## Why 9 Plans?

The full spec is ~450 lines covering 4 subsystems with different tech stacks (Python/pysnmp, Python/FastAPI, React/TypeScript). A single plan would exceed what fits comfortably in a small context window. Each sub-plan below:

- Fits in a ~30K-token context window
- Produces working, testable software on its own
- Has clear input dependencies and output interfaces
- Takes 30–90 minutes to execute with an agentic worker

---

## Dependency Graph

```
Plan 1: Foundation
  │
  ├──► Plan 2: Simulator – Infrastructure Devices
  │      │
  │      └──► Plan 3: Simulator – Endpoints, Wireless & Roaming
  │             │
  │             ├──► Plan 4: Collector Agent
  │             │      │
  │             │      └──► Plan 5: FastAPI Server
  │             │             │
  │             │             ├──► Plan 6: React UI – L2 View
  │             │             │      │
  │             │             │      ├──► Plan 7: UI – Detail Panel & L3 View
  │             │             │      │
  │             │             │      └──► Plan 8: UI – Edit Mode
  │             │             │
  │             │             └──► Plan 9: Integration & Docker
  │             │
  │             └──► Plan 9: Integration & Docker
```

Plans 7 and 8 can run in parallel (both depend on Plan 6, neither depends on the other).

---

## Plan Summaries

### Plan 1: Foundation & Shared Data Model
**File:** `2026-04-14-plan-01-foundation.md`
**Tech:** Python, Pydantic, SQLite, Docker Compose skeleton
**Time estimate:** ~30 min

**Scope:**
- Project directory structure (all folders, `__init__.py` files, `requirements.txt` files)
- Docker Compose skeleton (services defined, ports reserved, but implementations are stubs)
- Shared Pydantic models for the topology data model (nodes, edges, L2/L3 topology)
- SQLite database schema and `database.py` module
- Shared constants (device IPs, ports, VLANs, community strings)

**Produces:** Importable Python packages (`simulator/`, `collector/`, `server/`) with shared types. Docker Compose file that will wire things together later. SQLite schema ready for persistence.

**Key interfaces defined here (used by all later plans):**
- `server/models.py` — Pydantic models: `Device`, `Edge`, `L2Topology`, `L3Topology`, `Subnet`, `Route`, `ConnectionEdit`
- `server/database.py` — SQLite connection, table creation, basic CRUD
- `simulator/topology_state.py` — `TopologyState` class (in-memory store for all device connections)

---

### Plan 2: SNMP Simulator — Infrastructure Devices
**File:** `2026-04-14-plan-02-simulator-infrastructure.md`
**Tech:** Python, pysnmp
**Depends on:** Plan 1

**Scope:**
- Base SNMP agent class (`simulator/agent.py`) — wraps pysnmp to create an SNMP v2c agent on a given UDP port with a configurable MIB tree
- FortiGate device (`simulator/devices/fortigate.py`) — SNMPv2-MIB, IF-MIB, IP-MIB, LLDP-MIB, FORTINET-FORTIGATE-MIB (HA only — wireless tables come in Plan 3)
- Core Switch device (`simulator/devices/core_switch.py`) — SNMPv2-MIB, IF-MIB, LLDP-MIB, Q-BRIDGE-MIB, BRIDGE-MIB
- Floor Switch device (`simulator/devices/floor_switch.py`) — SNMPv2-MIB, IF-MIB, LLDP-MIB, Q-BRIDGE-MIB, POWER-ETHERNET-MIB, BRIDGE-MIB, RFC1213-MIB
- Shared MIB builder utilities (`simulator/devices/base.py`)
- Simulator entrypoint (`simulator/main.py`) — starts 7 SNMP agents (2 FortiGates + 1 core + 4 floor switches)

**Produces:** A running SNMP simulator that responds to GET/GETNEXT/GETBULK/WALK for all 7 infrastructure devices. Each device returns correct system identity, interfaces, and LLDP neighbor tables so a collector can walk from seed to full infrastructure topology.

**Tests:**
- Unit: each device type returns correct OID values for sysDescr, sysName, interface count
- Integration: SNMP WALK against each running agent, validate MIB tree structure
- LLDP consistency: verify bidirectional neighbor entries (if A lists B, B lists A)

---

### Plan 3: SNMP Simulator — Endpoints, Wireless & Roaming
**File:** `2026-04-14-plan-03-simulator-wireless.md`
**Tech:** Python, pysnmp
**Depends on:** Plan 2

**Scope:**
- Endpoint generation in floor switch ARP/MAC tables — POS terminals (VLAN 10), operations PCs (VLAN 20), cameras (VLAN 40), IoT (VLAN 50) distributed across 4 floor switches
- AP entries in floor switch LLDP tables — 14 APs per floor switch as LLDP neighbors
- FortiGate wireless controller tables:
  - `fgWcApTable` — 56 APs with name, serial, IP, status, client count, parent switch port
  - `fgWcStaTable` — ~850 guest clients + 90 employee handhelds mapped to APs
- Wireless client roaming simulator (`simulator/roaming.py`):
  - Background async task, runs every 3–5 seconds
  - Moves 2–5 random clients between APs per tick
  - Same-floor vs cross-floor roaming by device type (employees 70/30, guests 85/15)
  - Adjacent-floor-only constraint (no floor 1→4 jumps)
  - RSSI adjustment after roam
- Simulator REST API (`simulator/api.py`) — `POST /simulator/connections` for connection move/create/delete

**Produces:** Full SNMP simulator with all ~1,200 endpoints visible in switch tables, all 56 APs in LLDP and wireless controller tables, and live roaming that changes wireless client assignments every few seconds.

**Tests:**
- Unit: endpoint counts per VLAN match spec, AP distribution is 14 per floor
- Roaming: run 10 ticks, verify clients actually move, verify same-VLAN constraint, verify adjacency constraint
- REST API: POST a connection move, verify LLDP/ARP tables updated on affected switches

---

### Plan 4: Collector Agent
**File:** `2026-04-14-plan-04-collector.md`
**Tech:** Python, pysnmp (client), asyncio
**Depends on:** Plan 3 (needs a running simulator to test against)

**Scope:**
- SNMP client utilities — wrapper for pysnmp GET/GETNEXT/GETBULK/WALK operations
- LLDP discovery (`collector/discovery.py`):
  - Seed from FortiGate primary (10.0.0.1:10161)
  - Walk `lldpRemTable` to discover neighbors
  - Recursive hop to each neighbor's LLDP table
  - Track visited devices to avoid loops
- ARP/MAC endpoint discovery:
  - Walk `ipNetToMediaTable` (ARP) and `dot1dTpFdbTable` (MAC forwarding) on each switch
  - Resolve endpoints with IP, MAC, VLAN, connected port
- Wireless client discovery:
  - Query FortiGate `fgWcApTable` + `fgWcStaTable`
  - Map each wireless client to its AP
- L2 topology builder (`collector/topology_builder.py`):
  - Build nodes list from all discovered devices
  - Build edges list from LLDP neighbor pairs + ARP/MAC associations
  - Output matches the L2 topology JSON structure from the spec
- L3 topology builder:
  - Query FortiGate `ipRouteTable` for subnet relationships
  - Build subnet list with VLAN, CIDR, gateway, device counts
  - Build inter-VLAN routing relationships
- Continuous polling (`collector/poller.py`):
  - Async loop, polls every 5 seconds
  - Compares new snapshot to previous, detects diffs
  - Exposes topology store that FastAPI can read

**Produces:** A collector that, given a running simulator, discovers the full topology (7 infrastructure devices, 56 APs, ~1,200 endpoints) and continuously maintains L2 + L3 topology graphs.

**Tests:**
- Unit: LLDP table parsing, ARP table parsing, topology diff detection
- Integration: start simulator → run collector → verify all 7 infrastructure devices discovered
- Integration: verify L2 topology has correct node/edge counts
- Integration: verify L3 topology has all 6 VLANs with correct device counts
- Roaming detection: wait for roaming tick, verify collector detects client movement

---

### Plan 5: FastAPI Server
**File:** `2026-04-14-plan-05-server.md`
**Tech:** Python, FastAPI, WebSocket, SQLite
**Depends on:** Plan 4 (collector), Plan 3 (simulator REST API)

**Scope:**
- FastAPI app setup (`server/main.py`) — CORS, lifespan events, mount routes
- Collector integration — runs collector as an async background task at startup
- Topology routes (`server/routes/topology.py`):
  - `GET /api/topology/l2` — full L2 graph
  - `GET /api/topology/l3` — full L3 graph
  - `GET /api/topology/l2/device/{device_id}` — drill-down
  - `GET /api/topology/l3/vlan/{vlan_id}` — VLAN members
- Device routes (`server/routes/devices.py`):
  - `GET /api/devices` — list all with status
  - `GET /api/devices/{device_id}` — detail
  - `GET /api/devices/{device_id}/interfaces` — interface stats
- Connection routes (`server/routes/connections.py`):
  - `POST /api/connections` — create/move (forwards to simulator, triggers re-poll)
  - `DELETE /api/connections/{edge_id}` — remove
- System routes (`server/routes/system.py`):
  - `GET /api/status` — health
  - `POST /api/collector/poll` — trigger re-poll
- WebSocket manager (`server/websocket.py`):
  - `WS /ws/topology` — live updates
  - Event types: `topology_update`, `device_status`, `connection_change`, `metrics_update`
  - Detects topology store changes, pushes diffs to all connected clients
- SQLite persistence for topology snapshots and connection history

**Produces:** A running FastAPI server on port 8000 that serves the full REST API, pushes live topology updates via WebSocket, and bridges the simulator/collector.

**Tests:**
- Unit: each route handler returns correct response shape
- Integration: start full stack (simulator + collector + server), verify API returns topology
- WebSocket: connect client, trigger change, verify event received
- Connection edit: POST a move, verify simulator updated, verify topology changes after re-poll

---

### Plan 6: React UI — Project Setup & L2 View
**File:** `2026-04-14-plan-06-ui-l2.md`
**Tech:** React 18, TypeScript, React Flow, Tailwind CSS, Vite
**Depends on:** Plan 5 (needs running API server)

**Scope:**
- Vite project scaffolding with React + TypeScript + Tailwind
- TypeScript types (`ui/src/types/topology.ts`) — mirrors API response shapes
- WebSocket hook (`ui/src/hooks/useWebSocket.ts`) — connect, reconnect, parse events
- Topology data hook (`ui/src/hooks/useTopology.ts`) — fetch initial topology, merge WebSocket updates
- Top bar (`ui/src/components/TopBar.tsx`) — app title, L2/L3 toggle, polling indicator, Edit Mode button (disabled until Plan 8)
- React Flow canvas (`ui/src/components/TopologyCanvas.tsx`) — pan, zoom, drag
- Custom device nodes (`ui/src/components/DeviceNode.tsx`):
  - Color-coded by type: red (firewall), blue (core switch), amber (floor switch), purple (AP), gray (endpoint)
  - Status indicator: green/red/amber dot
  - Device name and model label
- Custom connection edges (`ui/src/components/ConnectionEdge.tsx`) — port labels, link speed
- Hierarchical layout engine (`ui/src/utils/layoutEngine.ts`):
  - FortiGates at top → Core Switch → Floor Switches → APs/Endpoints
  - Auto-layout on initial load
- Breadcrumb navigation for drill-down (click floor switch → see its ports and connected devices)

**Produces:** A working L2 physical topology view in the browser. Shows the full hierarchy from FortiGates down to endpoints. Nodes are color-coded and show status. Edges show port labels. Live updates via WebSocket. Click a floor switch to drill into its subtree.

**Tests:**
- Component: DeviceNode renders correct color for each device type
- Component: ConnectionEdge shows port labels
- Component: TopBar renders L2/L3 toggle
- Manual: open browser at localhost:5173, verify full topology renders with hierarchy

---

### Plan 7: React UI — Detail Panel & L3 View
**File:** `2026-04-14-plan-07-ui-detail-l3.md`
**Tech:** React, TypeScript, React Flow, Tailwind
**Depends on:** Plan 6
**Can run in parallel with:** Plan 8

**Scope:**
- Detail panel (`ui/src/components/DetailPanel.tsx`) — right sidebar:
  - Device name, model, IP, status
  - Interface list with live throughput stats
  - Connected neighbors with port mappings
  - PoE power draw (for PoE switches)
  - VLAN membership
  - Updates when a different device is selected on canvas
- L3 logical view (`ui/src/components/L3View.tsx`):
  - FortiGate as central gateway at top
  - VLAN/subnet blocks below, color-coded by segment
  - Lines between VLANs show routing relationships
  - Shows inter-VLAN routing policies (allow/deny with color)
  - Click a VLAN block to drill into member devices
- L2/L3 toggle in TopBar switches between views
- Zoom controls (bottom-right)
- Breadcrumb updates for both L2 drill-down and L3 VLAN drill-down

**Produces:** Complete detail panel that shows contextual info for any selected device. Full L3 logical view showing VLAN segments, routing, and policies. Seamless toggle between L2 and L3 views.

**Tests:**
- Component: DetailPanel renders device info for a mock device
- Component: L3View renders VLAN blocks with correct colors
- Component: L2/L3 toggle switches canvas content
- Manual: select a floor switch, verify detail panel shows interfaces and PoE draw. Switch to L3, verify VLAN layout.

---

### Plan 8: React UI — Edit Mode
**File:** `2026-04-14-plan-08-ui-edit-mode.md`
**Tech:** React, TypeScript, React Flow, Tailwind
**Depends on:** Plan 6
**Can run in parallel with:** Plan 7

**Scope:**
- Edit mode toggle (`ui/src/components/EditMode.tsx`):
  - Toggle button in TopBar
  - Amber banner when active: "Edit Mode — drag to create connections, click to disconnect"
- Connection creation:
  - Drag from source device port to target device
  - Visual feedback during drag (animated dashed line)
  - Drop creates a pending connection
- Connection deletion:
  - Click an existing edge to mark it for deletion
  - Edge highlights in red when marked
- Pending change preview panel:
  - Shows what will change (source, target, ports)
  - "Apply Change" button
  - "Cancel" button
- Apply flow:
  - Sends `POST /api/connections` to server
  - Shows loading spinner (~5 second round-trip)
  - Waits for `connection_change` WebSocket event
  - Animates topology update (node moves to new subtree)
- Cancel flow: discards pending change, resets visual state

**Produces:** Full edit mode where users can drag-connect devices, click to disconnect, preview changes, and apply them. The full loop (UI → API → Simulator → Collector → WebSocket → UI update) works end-to-end.

**Tests:**
- Component: Edit mode toggle shows/hides banner
- Component: Pending change preview renders correct info
- Integration: enable edit mode, drag to create connection, apply, verify topology updates after WebSocket event
- Manual: full drag-and-drop edit flow in the browser

---

### Plan 9: Integration & Docker
**File:** `2026-04-14-plan-09-integration-docker.md`
**Tech:** Docker, Docker Compose, pytest
**Depends on:** All previous plans

**Scope:**
- Dockerfile for simulator + server (single Python container since collector runs inside server)
- Dockerfile for UI (Node build → nginx serve)
- Docker Compose (`docker-compose.yml`):
  - `simulator` service: Python, exposes UDP 10161-10167 + REST 8001
  - `server` service: Python/FastAPI, exposes HTTP 8000 + WS, depends on simulator
  - `ui` service: nginx, exposes HTTP 5173, depends on server
  - Health checks for each service
- Environment configuration (ports, simulator host, etc.)
- End-to-end test:
  1. `docker-compose up`
  2. Wait for health checks
  3. `GET /api/topology/l2` — verify full topology
  4. `POST /api/connections` — move an AP
  5. Wait for WebSocket `connection_change` event
  6. `GET /api/topology/l2` — verify AP moved in topology
  7. Verify round-trip < 10 seconds

**Produces:** One-command local startup via `docker-compose up`. All services healthy. Full connection edit loop works end-to-end.

**Tests:**
- Docker: each service builds and starts
- Health: all health checks pass within 30 seconds
- E2E: full connection edit loop through all components

---

## Interface Contracts

These are the key boundaries between plans. Each plan should implement its side of the interface exactly.

### SNMP Interface (Simulator ↔ Collector)
- **Protocol:** SNMP v2c over UDP
- **Community:** `public` (read-only)
- **Ports:** 10161–10167 (all on localhost)
- **MIBs:** SNMPv2-MIB, IF-MIB, IP-MIB, RFC1213-MIB, LLDP-MIB, Q-BRIDGE-MIB, BRIDGE-MIB, POWER-ETHERNET-MIB, FORTINET-FORTIGATE-MIB

### Simulator REST API (Server → Simulator)
- **Base URL:** `http://localhost:8001`
- **Endpoint:** `POST /simulator/connections`
- **Body:** `{"action": "move"|"create"|"delete", "device": "...", "from": {...}, "to": {...}}`

### Server REST API (UI → Server)
- **Base URL:** `http://localhost:8000`
- **Endpoints:** See Plan 5 scope
- **Response shapes:** Defined by Pydantic models in `server/models.py` (Plan 1)

### WebSocket (Server → UI)
- **URL:** `ws://localhost:8000/ws/topology`
- **Events:** `topology_update`, `device_status`, `connection_change`, `metrics_update`
- **Format:** JSON with `{"type": "...", "data": {...}}`

---

## Execution Order

**Sequential (must be in order):**
1. Plan 1 → Plan 2 → Plan 3 → Plan 4 → Plan 5

**Then parallel tracks:**
- Track A: Plan 6 → Plan 7
- Track B: Plan 6 → Plan 8
- (Plan 7 and Plan 8 share Plan 6 as a prerequisite but are independent of each other)

**Finally:**
- Plan 9 (after all others complete)

**Optimal execution with 2 parallel workers after Plan 6:**
```
Worker 1: Plan 1 → 2 → 3 → 4 → 5 → 6 → 7 → 9
Worker 2:                                    8 ──┘
```
