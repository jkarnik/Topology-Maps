# Network Topology Simulator & Visualizer

A simulation and visualization tool for a Fortinet SD-Branch retail network. It simulates the full SNMP infrastructure of a 40,000 sqft, 4-floor retail store with ~1,200 endpoints, discovers the topology automatically, and renders it as an interactive web UI with L2 physical, L3 logical, and hybrid views.

One command to run everything:

```bash
docker compose up --build
```

Then open **http://localhost:80** in your browser.

---

## What It Does

- **Simulates** 7 real SNMP agents (FortiGate firewalls, core switch, floor switches) that respond to standard SNMP v2c queries
- **Generates** ~1,200 endpoints across 6 VLANs (POS terminals, IP cameras, IoT sensors, employee handhelds, guest Wi-Fi devices)
- **Discovers** the full topology automatically via LLDP walking, ARP/MAC scanning, and wireless controller queries
- **Visualizes** the network in three interactive views (L2 physical, L3 logical, L2+L3 hybrid)
- **Simulates roaming** by periodically moving wireless clients between access points
- **Supports live editing** of connections via drag-and-drop, with changes propagating through the full stack in ~5 seconds

---

## Architecture

```
                    docker compose up
                          |
          +---------------+---------------+
          |               |               |
    [Simulator]      [Server]          [UI]
     Port 8001       Port 8000        Port 80
          |               |               |
    SNMP agents      FastAPI +        React +
    + REST API       Collector        React Flow
    + Roaming        + WebSocket      + Tailwind
```

### Simulator (`simulator/`)

Runs 7 pysnmp SNMP agents on UDP ports 10161-10167, one per infrastructure device. Each agent serves a full MIB tree with system identity, interfaces, LLDP neighbors, ARP/MAC tables, VLAN assignments, and PoE data.

| Device | Model | SNMP Port |
|--------|-------|-----------|
| FortiGate Primary | FortiGate 200G | 10161 |
| FortiGate Standby | FortiGate 200G | 10162 |
| Core Switch | FortiSwitch 1024E | 10163 |
| Floor Switch 1-4 | FortiSwitch 448E-FPOE | 10164-10167 |

Also includes:
- **Endpoint generator** -- populates ~1,200 endpoints across floor switch ARP/MAC tables
- **Wireless controller tables** -- 56 APs and ~940 wireless clients in the FortiGate's MIB
- **Roaming simulator** -- moves 2-5 wireless clients between APs every 3-5 seconds
- **REST API** (port 8001) -- accepts connection edit commands (move/create/delete)

### Collector (`collector/`)

Discovers the network by starting from the FortiGate seed device and recursively walking LLDP neighbor tables. Runs as a background task inside the server.

Discovery process:
1. Query seed device (FortiGate) for system identity
2. Walk LLDP table to find neighbors (core switch)
3. Recursively walk each neighbor's LLDP table (floor switches)
4. Walk ARP/MAC tables on switches to find wired endpoints
5. Walk FortiGate wireless controller tables for APs and wireless clients
6. Walk IP route table for L3 subnet relationships
7. Build L2 (physical) and L3 (logical) topology graphs
8. Poll every 5 seconds, detect changes, push updates via WebSocket

### Server (`server/`)

FastAPI application serving the REST API and WebSocket hub.

| Endpoint | Purpose |
|----------|---------|
| `GET /api/topology/l2` | Full L2 physical topology |
| `GET /api/topology/l3` | Full L3 logical topology |
| `GET /api/devices` | All devices with status |
| `GET /api/devices/{id}` | Device detail with interfaces |
| `POST /api/connections` | Create/move/delete a connection |
| `GET /api/status` | System health |
| `WS /ws/topology` | Live topology updates |

### UI (`ui/`)

React 18 + TypeScript + React Flow + Tailwind CSS.

**Three views:**

- **L2 Physical** -- Hierarchical layout showing FortiGates at top, through core switch, floor switches, APs, down to endpoints. Color-coded by device type with distinct shapes (hexagons for firewalls, circles for APs, pills for endpoints). Double-click to drill into a switch and see its connected devices.

- **L3 Logical** -- FortiGate as central gateway with VLAN/subnet blocks below. Shows inter-VLAN routing policies (allow/deny). Color-coded by VLAN segment.

- **L2+L3 Hybrid** -- The physical infrastructure backbone (firewalls, switches) at top with VLAN group containers below, connected by physical path edges. Inter-VLAN routing policy overlays show which segments can communicate through the FortiGate.

**Features:**
- Live WebSocket updates (polling indicator shows connection status)
- Device detail panel (interfaces, neighbors, PoE draw, wireless clients)
- Edit mode for drag-to-connect and click-to-disconnect
- New/removed device animations (green/red blinking borders)
- Endpoint color-coding by category (payment, operations, security, IoT, etc.)

---

## Simulated Network

**Store profile:** 40,000 sqft retail store, 4 floors, ~10,000 daily visitors

| Category | VLAN | Devices | Connection |
|----------|------|---------|------------|
| Payment (PCI) | 10 | ~40 POS terminals | Wired |
| Operations | 20 | ~12 PCs/printers | Wired |
| Employee Mobility | 30 | ~90 handhelds/badges | Wi-Fi (Corp) |
| Security & Safety | 40 | ~50 cameras/NVRs | Wired PoE |
| Retail IoT | 50 | ~110 signage/sensors | Wired |
| Guest Wi-Fi | 60 | ~850 phones/tablets | Wi-Fi (Guest) |

**Total:** ~1,200 endpoints at any snapshot, 56 access points, 7 infrastructure devices.

---

## Project Structure

```
simulator/          Python SNMP simulator
  agent.py            SNMP v2c agent (UDP protocol handler)
  devices/            MIB tree builders per device type
  endpoint_generator  Populates wired + wireless endpoints
  roaming.py          Wireless client roaming simulation
  api.py              REST API for connection edits
  topology_state.py   In-memory state store

collector/          Python topology collector
  snmp_client.py      Async SNMP v2c client
  discovery.py        LLDP/ARP/wireless discovery engine
  topology_builder.py Builds L2 + L3 topology graphs
  poller.py           Continuous polling loop

server/             Python FastAPI server
  main.py             App entry point + collector integration
  routes/             REST API endpoints
  websocket.py        WebSocket manager
  models.py           Pydantic data models
  database.py         SQLite persistence

ui/                 React + TypeScript frontend
  src/components/     TopologyCanvas, DeviceNode, L3View, HybridView, etc.
  src/hooks/          useTopology, useWebSocket, useEditMode
  src/utils/          Layout engine
  src/types/          TypeScript type definitions
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| SNMP Simulator | Python, pysnmp 6.x |
| Collector | Python, pysnmp (client), asyncio |
| API Server | Python, FastAPI, uvicorn |
| UI | React 18, TypeScript, React Flow, Tailwind CSS, Vite |
| Orchestration | Docker Compose (3 services) |
