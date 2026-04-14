# Meraki Live Topology — Design Spec

## Overview

Add a "Meraki Live" data source to the topology visualization app that pulls real device, topology, and client data from the Cisco Meraki Dashboard API. The existing simulated Fortinet topology becomes one of two selectable sources, each with its own L2/L3/Hybrid views.

## UI Changes

### Two-Level Navigation

The header bar is restructured into a compact single-row layout:

- **Source selector dropdown** (left) — switches between "Simulated" and "Meraki Live"
- **View mode pills** (inline) — L2, L3, Hybrid sub-tabs per source
- **Right-side controls** — vary by source (see below)

When "Simulated" is selected:
- Cyan accent color (unchanged from current)
- Start/Stop simulation button. When running: green LIVE indicator with update count + countdown timer (10-minute auto-shutdown). When stopped: "Start Simulation" button.
- L2/L3/Hybrid pills in cyan

When "Meraki Live" is selected:
- Amber accent color
- "Updated Xm ago" timestamp + Refresh button
- L2/L3/Hybrid pills in amber

The source dropdown when expanded shows both options with labels: "Simulated (SNMP)" and "Meraki Live (API)".

### Network Filter (Meraki only)

When the Meraki source is active, a second dropdown appears next to the source selector allowing the user to filter by Meraki network. Options:
- "All Networks" (default) — merges devices from all networks into one canvas. Since Meraki's link-layer topology is per-network, cross-network links will not appear; devices from different networks render as separate clusters.
- Individual network names — shows only devices from that network, with full link-layer topology edges.

### Edit Mode Removal

The EDIT button, drag-to-connect, and click-to-disconnect functionality are removed entirely from both the Simulated and Meraki views. The `useEditMode` hook and related connection editing UI are removed.

### Drill-Down and Detail Panel

Both sources support:
- **Single-click** to open the detail panel (right sidebar)
- **Double-click** to drill into a device (show device + direct children)
- **Breadcrumb navigation** for drill-down path

## Backend Architecture

### Approach: Backend Proxy

The FastAPI server gets new `/api/meraki/*` routes that proxy requests to the Meraki Dashboard API. The server:
1. Calls the Meraki API with the stored API key
2. Transforms responses into the existing `L2Topology` and `L3Topology` formats
3. Returns the normalized data to the frontend

This means the frontend reuses all existing visualization components (React Flow, DeviceNode, ConnectionEdge, layout engine, DetailPanel) without modification to the rendering layer.

### API Key Configuration

- Stored as environment variable `MERAKI_API_KEY`
- Read by the FastAPI server on startup
- Passed through Docker Compose environment configuration
- Never sent to the browser

### New Server Routes

| Route | Purpose |
|---|---|
| `GET /api/meraki/status` | Validates API key, returns org info and network list |
| `GET /api/meraki/networks` | Lists all networks in the organization |
| `GET /api/meraki/topology/l2` | Full L2 topology (all networks or filtered) |
| `GET /api/meraki/topology/l2?network={id}` | L2 topology for a specific network |
| `GET /api/meraki/topology/l3` | L3 topology — VLANs, subnets, routes |
| `GET /api/meraki/topology/l3?network={id}` | L3 topology for a specific network |
| `GET /api/meraki/devices/{serial}` | Device detail + interfaces + clients |

### Meraki API Endpoints Used

| Purpose | Meraki API Endpoint |
|---|---|
| List all devices | `GET /organizations/{orgId}/devices` |
| Device statuses | `GET /organizations/{orgId}/devices/statuses` |
| Physical topology (LLDP/CDP) | `GET /networks/{networkId}/topology/linkLayer` |
| VLANs | `GET /networks/{networkId}/appliance/vlans` |
| Connected clients | `GET /devices/{serial}/clients` |
| Switch ports | `GET /devices/{serial}/switch/ports` |
| Wireless SSIDs | `GET /networks/{networkId}/wireless/ssids` |

### Rate Limiting

The server implements a rate limiter for all outbound Meraki API calls, capped at **5 requests per second** to stay within Meraki's documented limit and prevent 429 responses even for large organizations.

- Uses an async token-bucket rate limiter — all Meraki API calls pass through it before executing
- For a large org refresh (e.g., 20 networks × 4 API calls each = 80 calls), requests are queued and dispatched at 5/sec, taking ~16 seconds total
- The server reports progress back to the frontend via the refresh response (see Loading Visualization below)

### Organization Discovery

On startup (or first Meraki request), the server calls `GET /organizations` to find the accessible org, then caches the org ID and network list. The network list is refreshed on each `/api/meraki/networks` call.

## Data Model Mapping

Meraki data is transformed into the existing TypeScript types so the frontend can render it without changes to the visualization layer.

### Device Mapping

| Meraki Field | Maps To | Notes |
|---|---|---|
| `serial` | `Device.id` | Unique identifier |
| `productType` (appliance/switch/wireless) | `Device.type` | Maps to firewall/switch/access_point |
| `model` | `Device.model` | Direct mapping |
| `lanIp` | `Device.ip` | LAN IP address |
| `status` | `Device.status` | online → up, offline → down, alerting → alerting (amber indicator), dormant → down |
| `mac` | `Device.mac` | Direct mapping |
| `name` | Display label | Used in node rendering |
| `networkId` | Additional field | For network filtering |
| `firmware` | Additional field | Shown in detail panel |
| `address` | Additional field | GPS/address in detail panel |
| `tags` | Additional field | Shown in detail panel |
| `notes` | Additional field | Shown in detail panel |
| `publicIp` | Additional field | Shown in detail panel |
| `lastReportedAt` | Additional field | Shown in detail panel |
| `gateway` | Additional field | Shown in detail panel |
| `primaryDns`, `secondaryDns` | Additional field | Shown in detail panel |
| `usingCellularFailover` | Additional field | Shown for MX appliances |

### Edge Mapping (from linkLayer topology)

| Meraki Field | Maps To |
|---|---|
| Link endpoints (device serials + ports) | `Edge.source`, `Edge.target`, `Edge.source_port`, `Edge.target_port` |
| Discovery protocol (LLDP/CDP) | `Edge.protocol` |

### Subnet/VLAN Mapping (L3)

| Meraki Field | Maps To |
|---|---|
| VLAN `id` | `Subnet.vlan` |
| VLAN `name` | `Subnet.name` |
| VLAN `subnet` | `Subnet.cidr` |
| VLAN `applianceIp` | `Subnet.gateway` |
| Client count per VLAN | `Subnet.device_count` |

## Detail Panel — Meraki Devices

The detail panel adapts its sections based on device type. All types share a common header and client list.

### Common Header (all types)

- Status indicator (green dot = online, red = offline, amber = alerting)
- Device name and model
- Serial number
- Network name
- LAN IP and public IP
- Firmware version
- Physical address (if set)
- Tags and notes (if set)
- Last reported time
- Gateway IP, primary/secondary DNS

### MX Security Appliance

- **Uplinks** — WAN 1 and WAN 2 status (active/standby), IP addresses, cellular failover status
- **VLANs** — name, ID, subnet, gateway IP, DHCP settings (handling mode, lease time), DNS nameservers, reserved IP ranges, fixed IP assignments
- **Clients** — name/description, IP, MAC, VLAN, usage (sent/received bytes), DHCP hostname, mDNS name

### MS Switch

- **Ports Summary** — active/inactive count, total PoE draw
- **Port Details** — port ID, name, enabled, PoE enabled, type (access/trunk), VLAN, voice VLAN, allowed VLANs, STP/RSTP settings, link negotiation, storm control, isolation
- **LLDP/CDP Neighbors** — port-to-port mappings with neighbor device info and discovery protocol
- **Clients** — name/description, IP, MAC, switchport, VLAN, usage, DHCP hostname

### MR Access Point

- **Wireless Summary** — total client count, active SSID count, channel
- **SSIDs** — name, enabled, auth mode (WPA2/WPA3/802.1x/open), encryption mode, splash page type, band selection, min bitrate, per-client bandwidth limits (up/down)
- **Clients** — name/description, IP, MAC, SSID, signal strength (RSSI), usage, DHCP hostname, mDNS name, adaptive policy group

## Data Refresh

### Meraki Source — Manual Refresh with Loading Visualization

- Data fetched on initial tab switch to Meraki
- Refresh button triggers a fresh pull from the Meraki API
- "Updated Xm ago" timestamp shows data age
- No automatic polling — respects API rate limits and user preference

**Progressive rendering with countdown during refresh:**

When the user clicks Refresh (or first switches to the Meraki tab), the topology canvas progressively populates with real data as it arrives from the rate-limited API:

1. **Discovery phase** (~1s): "Discovering organization..." message. Server fetches org info + device list.
2. **Placeholder phase**: All discovered devices appear on the canvas as **gray placeholder nodes** — correct names and type-shapes (hexagon for MX, rectangle for MS, circle for MR) but no color, no edges. A small status bar appears at the top of the canvas: "Refreshing — ~14s remaining" with a progress bar.
3. **Topology phase**: As each network's link-layer topology and VLAN data returns, those devices **transition from gray to their full color** (red for MX, amber for MS, purple for MR) and edges animate in between them. The progress bar and countdown update with each completed network.
4. **Client phase**: As per-device client data arrives, client count badges appear on each device node. Devices that have received full data get a subtle checkmark or full-brightness indicator.
5. **Complete**: The status bar fades out. Refresh button returns to normal. "Updated just now" timestamp appears.

The Refresh button shows a spinner and "Refreshing..." (disabled) throughout.

**Implementation:** The refresh endpoint uses Server-Sent Events (SSE) to stream incremental topology data:
- `POST /api/meraki/refresh` returns an SSE stream
- Phase 1 event: `{"phase": "discovery", "device_count": 45, "network_count": 7, "estimated_seconds": 14}`
- Phase 2 event (per device batch): `{"phase": "devices", "nodes": [...placeholder devices...]}`
- Phase 3 events (per network): `{"phase": "topology", "network": "HQ-Main", "nodes": [...updated devices...], "edges": [...], "progress": 3, "total": 7, "remaining_seconds": 10}`
- Phase 4 events (per device batch): `{"phase": "clients", "device_serial": "Q2KN-...", "clients": [...], "remaining_seconds": 4}`
- Final event: `{"phase": "complete"}`
- Frontend applies each event incrementally — updating node colors, drawing edges, adding client badges as data streams in

### Simulated Source — Start/Stop Simulation

The Simulated source gets a **Start/Stop** toggle button in the header bar (where the LIVE indicator currently is):

- **Stopped state**: Button shows "Start Simulation". The topology canvas shows an idle message: "Simulation stopped. Click Start to begin." No SNMP polling, no WebSocket updates. Simulator and collector services are not running.
- **Running state**: Button shows "Stop Simulation" with the existing green LIVE indicator and update count. SNMP polling and WebSocket updates are active as they are today.
- **Auto-shutdown**: The simulation automatically stops after **10 minutes** of running. A countdown timer appears next to the LIVE indicator (e.g., "LIVE #42 — 7:23 remaining"). When the timer reaches zero, the simulation stops gracefully and the UI returns to the stopped state.
- **On app load**: Simulation starts in the stopped state by default. The user must explicitly start it.

**Implementation:**
- New server routes:
  - `POST /api/simulation/start` — starts the SNMP simulator and collector polling loop, records start time
  - `POST /api/simulation/stop` — stops the simulator and collector, clears the timer
  - `GET /api/simulation/status` — returns running/stopped state and remaining time (if running)
- The server manages a 10-minute timer. When it expires, the server stops the simulator/collector and broadcasts a `simulation_stopped` WebSocket event
- The frontend shows the countdown by polling `/api/simulation/status` every second (or receiving WebSocket updates with remaining time)
- When stopped, the existing topology data remains on screen (not cleared) but is static — no live updates

## Error Handling

- **Invalid/missing API key**: Meraki tab shows a configuration message ("Set MERAKI_API_KEY environment variable") instead of the topology canvas
- **API unreachable**: Show error banner with retry button — "Could not reach Meraki API. Check your network connection."
- **Rate limited**: If Meraki returns 429, show "Rate limited — try again in a moment" and disable the refresh button briefly
- **Empty org (no devices)**: Show empty state — "No devices found in this organization"
- **Network with no topology data**: Show devices as disconnected nodes (no edges)

## Testing

- **Backend**: Unit tests for Meraki data transformation (Meraki API response → L2Topology/L3Topology format). Mock Meraki API responses. Tests for rate limiter (verify max 5 calls/sec). Tests for simulation start/stop/auto-shutdown lifecycle.
- **Frontend**: The visualization layer is already tested via the Simulated source. New tests focus on:
  - Source selector state management
  - Network filter dropdown
  - Refresh button, SSE progress stream, and loading overlay
  - Error states (no API key, API down, empty data)
  - Simulation start/stop button states and countdown timer
  - Auto-shutdown transition (running → stopped after timeout)
