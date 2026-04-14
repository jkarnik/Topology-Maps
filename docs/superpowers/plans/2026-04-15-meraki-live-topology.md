# Meraki Live Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Meraki Live data source with progressive refresh, restructure navigation into a two-level source/view system, add simulation start/stop with auto-shutdown, and remove edit mode.

**Architecture:** Backend proxy pattern — FastAPI server calls Meraki Dashboard API with rate limiting (5 req/sec), transforms responses into existing L2/L3 topology types. Frontend reuses all React Flow visualization components. SSE streams progressive topology data during refresh. Simulation lifecycle managed server-side with 10-minute auto-shutdown timer.

**Tech Stack:** React 18, TypeScript, React Flow, FastAPI, httpx, asyncio, Server-Sent Events

---

## File Structure

### New Files
- `server/routes/meraki.py` — Meraki proxy routes + SSE refresh endpoint
- `server/routes/simulation.py` — Simulation start/stop/status routes
- `server/meraki_client.py` — Meraki Dashboard API client with rate limiting
- `server/meraki_transformer.py` — Transform Meraki API responses → L2/L3 models
- `server/rate_limiter.py` — Async token-bucket rate limiter
- `ui/src/hooks/useMerakiTopology.ts` — Meraki data state, SSE refresh, network filter
- `ui/src/hooks/useSimulation.ts` — Simulation start/stop state + countdown
- `ui/src/components/SourceSelector.tsx` — Data source dropdown component
- `ui/src/components/NetworkFilter.tsx` — Meraki network filter dropdown
- `ui/src/components/RefreshOverlay.tsx` — Progressive loading overlay
- `ui/src/components/MerakiDetailPanel.tsx` — Extended detail panel for Meraki devices
- `ui/src/types/meraki.ts` — Meraki-specific TypeScript types
- `server/tests/test_rate_limiter.py` — Rate limiter unit tests
- `server/tests/test_meraki_transformer.py` — Transformer unit tests
- `server/tests/test_simulation.py` — Simulation lifecycle tests

### Modified Files
- `server/main.py` — Add meraki + simulation routers, modify lifespan for simulation control
- `server/models.py` — Add `alerting` device status
- `server/requirements.txt` — Add `sse-starlette`
- `ui/src/App.tsx` — Replace edit mode with source selector, wire up Meraki/simulation
- `ui/src/components/TopBar.tsx` — Restructure into source selector + view pills + controls
- `ui/src/hooks/useTopology.ts` — Remove edit mode refs, add simulation awareness
- `ui/src/types/topology.ts` — Add `DataSource` type, extend `WSEvent`
- `ui/src/index.css` — Add amber accent variables for Meraki theme
- `docker-compose.yml` — Add `MERAKI_API_KEY` env var, make simulator depend on simulation state

### Deleted Files
- `ui/src/hooks/useEditMode.ts` — Edit mode removed
- `ui/src/components/EditMode.tsx` — Edit mode UI removed
- `server/routes/connections.py` — Connection editing routes removed

---

## Task 1: Remove Edit Mode

**Files:**
- Delete: `ui/src/hooks/useEditMode.ts`
- Delete: `ui/src/components/EditMode.tsx`
- Delete: `server/routes/connections.py`
- Modify: `ui/src/App.tsx`
- Modify: `ui/src/components/TopBar.tsx`
- Modify: `ui/src/components/TopologyCanvas.tsx`
- Modify: `server/main.py`
- Modify: `ui/src/index.css`

- [ ] **Step 1: Delete edit mode files**

```bash
rm ui/src/hooks/useEditMode.ts
rm ui/src/components/EditMode.tsx
rm server/routes/connections.py
```

- [ ] **Step 2: Remove edit mode from App.tsx**

Replace the entire content of `ui/src/App.tsx` with:

```tsx
import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import DetailPanel from './components/DetailPanel';
import L3View from './components/L3View';
import HybridView from './components/HybridView';

function App() {
  const {
    l2Topology,
    l3Topology,
    viewMode,
    setViewMode,
    selectedDevice,
    setSelectedDevice,
    drillDown,
    drillInto,
    drillBack,
    drillReset,
    isConnected,
    isLoading,
    pollCount,
    deviceAnimations,
    pinnedDeviceIds,
  } = useTopology();

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <TopBar
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        isConnected={isConnected}
        pollCount={pollCount}
      />
      <div className="flex-1 relative overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}>
              SCANNING NETWORK...
            </div>
          </div>
        ) : viewMode === 'l2' ? (
          <ReactFlowProvider>
            <TopologyCanvas
              topology={l2Topology}
              selectedDevice={selectedDevice}
              onSelectDevice={setSelectedDevice}
              drillDown={drillDown}
              onDrillInto={drillInto}
              onDrillBack={drillBack}
              onDrillReset={drillReset}
              deviceAnimations={deviceAnimations}
              pinnedDeviceIds={pinnedDeviceIds}
            />
          </ReactFlowProvider>
        ) : viewMode === 'hybrid' ? (
          <ReactFlowProvider>
            <HybridView
              l2Topology={l2Topology}
              l3Topology={l3Topology}
              onSelectDevice={setSelectedDevice}
              onSelectVlan={() => {}}
            />
          </ReactFlowProvider>
        ) : (
          <ReactFlowProvider>
            <L3View topology={l3Topology} onSelectVlan={() => {}} />
          </ReactFlowProvider>
        )}

        {(viewMode === 'l2' || viewMode === 'hybrid') && (
          <DetailPanel
            device={selectedDevice}
            topology={l2Topology}
            onClose={() => setSelectedDevice(null)}
          />
        )}
      </div>
    </div>
  );
}

export default App;
```

- [ ] **Step 3: Remove edit mode from TopBar.tsx**

Replace the entire content of `ui/src/components/TopBar.tsx` with:

```tsx
import React from 'react';

interface TopBarProps {
  viewMode: 'l2' | 'l3' | 'hybrid';
  onViewModeChange: (mode: 'l2' | 'l3' | 'hybrid') => void;
  isConnected: boolean;
  pollCount: number;
}

export const TopBar: React.FC<TopBarProps> = ({
  viewMode,
  onViewModeChange,
  isConnected,
  pollCount,
}) => {
  return (
    <header
      style={{
        height: '56px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
        flexShrink: 0,
        position: 'relative',
        zIndex: 50,
      }}
    >
      {/* Left: App Title */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '15px',
            fontWeight: 700,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'var(--text-primary)',
            lineHeight: 1,
          }}
        >
          TOPOLOGY
        </span>
        <div
          style={{
            height: '2px',
            width: '100%',
            background: 'var(--accent-cyan)',
            borderRadius: '1px',
          }}
        />
      </div>

      {/* Center: L2 / L3 Toggle */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '999px',
          padding: '3px',
          gap: '2px',
        }}
      >
        {([['l2', 'L2'], ['hybrid', 'L2+L3'], ['l3', 'L3']] as const).map(([mode, label]) => {
          const isActive = viewMode === mode;
          return (
            <button
              key={mode}
              onClick={() => onViewModeChange(mode)}
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '12px',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                padding: '5px 18px',
                borderRadius: '999px',
                border: 'none',
                cursor: 'pointer',
                transition: 'background 0.15s ease, color 0.15s ease',
                background: isActive ? 'var(--accent-cyan)' : 'transparent',
                color: isActive ? 'var(--bg-primary)' : 'var(--text-secondary)',
                lineHeight: 1,
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Right: Live Indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '7px' }}>
        <span
          className={isConnected ? 'animate-pulse-dot' : undefined}
          style={{
            display: 'inline-block',
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: isConnected ? 'var(--accent-green)' : 'var(--accent-red)',
            boxShadow: isConnected
              ? '0 0 6px rgba(0, 214, 143, 0.6)'
              : '0 0 6px rgba(255, 71, 87, 0.5)',
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            letterSpacing: '0.1em',
          }}
        >
          {isConnected ? (
            <>
              <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>LIVE</span>
              {' '}
              <span style={{ color: 'var(--text-muted)' }}>#{pollCount}</span>
            </>
          ) : (
            <span style={{ color: 'var(--accent-red)', fontWeight: 600 }}>OFFLINE</span>
          )}
        </span>
      </div>
    </header>
  );
};

export default TopBar;
```

- [ ] **Step 4: Remove edit mode from TopologyCanvas.tsx**

In `ui/src/components/TopologyCanvas.tsx`, remove the edit mode props from the interface and handler code:

Remove from the `TopologyCanvasProps` interface (lines 34-36):
```
  editMode?: boolean;
  onEditConnect?: (source: string, target: string) => void;
  onEditDisconnect?: (edgeId: string, source: string, target: string) => void;
```

Remove from the destructured props (line 60-62):
```
  editMode = false,
  onEditConnect,
  onEditDisconnect,
```

Remove the `handleConnect` callback (lines 123-131):
```typescript
  const handleConnect: OnConnect = useCallback(
    (connection) => {
      if (!editMode || !onEditConnect) return;
      if (connection.source && connection.target) {
        onEditConnect(connection.source, connection.target);
      }
    },
    [editMode, onEditConnect],
  );
```

Remove the `handleEdgeClick` callback (lines 134-140):
```typescript
  const handleEdgeClick: EdgeMouseHandler = useCallback(
    (_event, edge) => {
      if (!editMode || !onEditDisconnect) return;
      onEditDisconnect(edge.id, edge.source, edge.target);
    },
    [editMode, onEditDisconnect],
  );
```

Remove `onConnect={handleConnect}` and `onEdgeClick={handleEdgeClick}` from the `<ReactFlow>` props (lines 173-174).

Remove the `edit-mode-active` class from the wrapper div (line 160): change `className={`topology-canvas${editMode ? ' edit-mode-active' : ''}`}` to `className="topology-canvas"`.

Remove unused imports: `OnConnect`, `EdgeMouseHandler` from the `@xyflow/react` import.

- [ ] **Step 5: Remove connections router from server/main.py**

In `server/main.py`, remove line 19:
```python
from server.routes import topology, devices, connections, system
```
Replace with:
```python
from server.routes import topology, devices, system
```

Remove line 72:
```python
app.include_router(connections.router)
```

- [ ] **Step 6: Remove edit mode CSS from index.css**

In `ui/src/index.css`, remove any CSS rules that reference `.edit-mode-active`, edit mode handles, or connection line edit styling. Search for `edit` in the file and remove those blocks.

- [ ] **Step 7: Verify the app builds**

```bash
cd ui && npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "feat: remove edit mode from both frontend and backend"
```

---

## Task 2: Backend Rate Limiter

**Files:**
- Create: `server/rate_limiter.py`
- Create: `server/tests/test_rate_limiter.py`

- [ ] **Step 1: Write failing test for rate limiter**

Create `server/tests/__init__.py` (empty file) and `server/tests/test_rate_limiter.py`:

```python
"""Tests for the async token-bucket rate limiter."""

import asyncio
import time
import pytest
from server.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_burst_up_to_capacity():
    """Requests up to the bucket capacity should complete instantly."""
    limiter = RateLimiter(rate=5, capacity=5)
    start = time.monotonic()
    for _ in range(5):
        await limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1  # All 5 should be near-instant


@pytest.mark.asyncio
async def test_rate_limiter_throttles_beyond_capacity():
    """The 6th request should wait ~200ms (1/5 sec) for a token."""
    limiter = RateLimiter(rate=5, capacity=5)
    # Drain the bucket
    for _ in range(5):
        await limiter.acquire()
    start = time.monotonic()
    await limiter.acquire()  # 6th request — must wait
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15  # Should wait ~200ms


@pytest.mark.asyncio
async def test_rate_limiter_concurrent_requests():
    """Multiple concurrent requests should be serialized by the limiter."""
    limiter = RateLimiter(rate=5, capacity=5)
    start = time.monotonic()
    # Launch 10 requests concurrently — 5 burst + 5 throttled
    await asyncio.gather(*[limiter.acquire() for _ in range(10)])
    elapsed = time.monotonic() - start
    # 5 burst instantly, 5 more at 5/sec = ~1 second
    assert elapsed >= 0.8
    assert elapsed < 2.0
```

- [ ] **Step 2: Install test dependencies and run to verify failure**

```bash
cd server && pip install pytest pytest-asyncio
pytest tests/test_rate_limiter.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'server.rate_limiter'`

- [ ] **Step 3: Implement the rate limiter**

Create `server/rate_limiter.py`:

```python
"""Async token-bucket rate limiter.

Limits outbound API calls to a configured rate (tokens per second).
Used to stay within Meraki's 5 req/sec API limit.
"""

import asyncio
import time


class RateLimiter:
    """Token-bucket rate limiter for async code.

    Parameters
    ----------
    rate : float
        Tokens added per second.
    capacity : int
        Maximum burst size (bucket capacity).
    """

    def __init__(self, rate: float = 5.0, capacity: int = 5):
        self._rate = rate
        self._capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it."""
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # Calculate wait time for next token
                wait = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait)

    def _refill(self) -> None:
        """Add tokens based on elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd server && pytest tests/test_rate_limiter.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add server/rate_limiter.py server/tests/__init__.py server/tests/test_rate_limiter.py
git commit -m "feat: add async token-bucket rate limiter (5 req/sec)"
```

---

## Task 3: Meraki API Client

**Files:**
- Create: `server/meraki_client.py`

- [ ] **Step 1: Create the Meraki API client**

Create `server/meraki_client.py`:

```python
"""Meraki Dashboard API client with rate limiting.

All outbound calls pass through a shared RateLimiter (5 req/sec)
to prevent 429 responses from the Meraki API.
"""

import logging
import os
from typing import Optional

import httpx

from server.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

MERAKI_BASE_URL = "https://api.meraki.com/api/v1"


class MerakiClient:
    """HTTP client for the Meraki Dashboard API.

    Parameters
    ----------
    api_key : str | None
        Meraki Dashboard API key. Falls back to MERAKI_API_KEY env var.
    rate_limit : float
        Max requests per second (default 5).
    """

    def __init__(self, api_key: Optional[str] = None, rate_limit: float = 5.0):
        self.api_key = api_key or os.environ.get("MERAKI_API_KEY", "")
        self._limiter = RateLimiter(rate=rate_limit, capacity=int(rate_limit))
        self._client = httpx.AsyncClient(
            base_url=MERAKI_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    @property
    def is_configured(self) -> bool:
        """Return True if an API key is set."""
        return bool(self.api_key)

    async def _get(self, path: str, params: Optional[dict] = None) -> dict | list:
        """Rate-limited GET request to the Meraki API."""
        await self._limiter.acquire()
        logger.debug("Meraki API GET %s", path)
        resp = await self._client.get(path, params=params)
        resp.raise_for_status()
        return resp.json()

    # ---- Organization ----

    async def get_organizations(self) -> list[dict]:
        return await self._get("/organizations")

    async def get_org_devices(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/devices")

    async def get_org_device_statuses(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/devices/statuses")

    async def get_org_networks(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/networks")

    # ---- Network ----

    async def get_network_topology(self, network_id: str) -> dict:
        """Get link-layer topology for a network. Returns {nodes, links}."""
        return await self._get(f"/networks/{network_id}/topology/linkLayer")

    async def get_network_vlans(self, network_id: str) -> list[dict]:
        """Get VLANs for an MX appliance network."""
        try:
            return await self._get(f"/networks/{network_id}/appliance/vlans")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                # VLANs not enabled on this network
                return []
            raise

    async def get_network_ssids(self, network_id: str) -> list[dict]:
        """Get wireless SSIDs for a network."""
        try:
            return await self._get(f"/networks/{network_id}/wireless/ssids")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                # Not a wireless network
                return []
            raise

    # ---- Device ----

    async def get_device_clients(self, serial: str, timespan: int = 300) -> list[dict]:
        """Get clients connected to a device (last 5 minutes)."""
        return await self._get(f"/devices/{serial}/clients", params={"timespan": timespan})

    async def get_device_switch_ports(self, serial: str) -> list[dict]:
        """Get switch port statuses."""
        try:
            return await self._get(f"/devices/{serial}/switch/ports/statuses")
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (400, 404):
                return []
            raise

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
```

- [ ] **Step 2: Commit**

```bash
git add server/meraki_client.py
git commit -m "feat: add Meraki Dashboard API client with rate limiting"
```

---

## Task 4: Meraki Data Transformer

**Files:**
- Create: `server/meraki_transformer.py`
- Create: `server/tests/test_meraki_transformer.py`
- Modify: `server/models.py`

- [ ] **Step 1: Add `alerting` status to server/models.py**

In `server/models.py`, add `ALERTING` to the `DeviceStatus` enum (after line 21):

```python
class DeviceStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"
    ALERTING = "alerting"
```

- [ ] **Step 2: Write failing test for the transformer**

Create `server/tests/test_meraki_transformer.py`:

```python
"""Tests for Meraki → L2/L3 topology data transformation."""

import pytest
from server.meraki_transformer import MerakiTransformer
from server.models import DeviceType, DeviceStatus


@pytest.fixture
def transformer():
    return MerakiTransformer()


def make_meraki_device(serial="Q2KN-1111-2222", product_type="appliance",
                       model="MX250", name="HQ Gateway", lan_ip="10.0.1.1",
                       status="online", mac="aa:bb:cc:dd:ee:ff",
                       network_id="N_111", **kwargs):
    return {
        "serial": serial, "productType": product_type, "model": model,
        "name": name, "lanIp": lan_ip, "status": status, "mac": mac,
        "networkId": network_id, "firmware": "MX 18.107",
        "address": "123 Main St", "tags": ["hq"], "notes": "",
        **kwargs,
    }


def test_device_type_mapping(transformer):
    """Meraki productType maps to our DeviceType."""
    mx = make_meraki_device(product_type="appliance")
    ms = make_meraki_device(serial="Q2HP-1111", product_type="switch")
    mr = make_meraki_device(serial="Q3AC-1111", product_type="wireless")

    devices = [mx, ms, mr]
    l2 = transformer.build_l2(devices, [], {})
    types = {n.id: n.type for n in l2.nodes}

    assert types["Q2KN-1111-2222"] == DeviceType.FIREWALL
    assert types["Q2HP-1111"] == DeviceType.FLOOR_SWITCH
    assert types["Q3AC-1111"] == DeviceType.ACCESS_POINT


def test_status_mapping(transformer):
    """Meraki status strings map to our DeviceStatus."""
    devices = [
        make_meraki_device(serial="A", status="online"),
        make_meraki_device(serial="B", status="offline"),
        make_meraki_device(serial="C", status="alerting"),
        make_meraki_device(serial="D", status="dormant"),
    ]
    l2 = transformer.build_l2(devices, [], {})
    statuses = {n.id: n.status for n in l2.nodes}

    assert statuses["A"] == DeviceStatus.UP
    assert statuses["B"] == DeviceStatus.DOWN
    assert statuses["C"] == DeviceStatus.ALERTING
    assert statuses["D"] == DeviceStatus.DOWN


def test_edge_creation_from_link_layer(transformer):
    """Link-layer topology data creates edges between devices."""
    devices = [
        make_meraki_device(serial="MX1", product_type="appliance"),
        make_meraki_device(serial="MS1", product_type="switch"),
    ]
    link_data = {
        "N_111": {
            "nodes": [],
            "links": [{
                "ends": [
                    {"device": {"serial": "MX1"}, "node": {"derivedId": "MX1"}, "discovered": {"lldp": {"portId": "Gi0/1"}}},
                    {"device": {"serial": "MS1"}, "node": {"derivedId": "MS1"}, "discovered": {"lldp": {"portId": "Port 1"}}},
                ]
            }]
        }
    }
    l2 = transformer.build_l2(devices, [], link_data)
    assert len(l2.edges) == 1
    assert l2.edges[0].source == "MX1"
    assert l2.edges[0].target == "MS1"
    assert l2.edges[0].source_port == "Gi0/1"
    assert l2.edges[0].target_port == "Port 1"


def test_vlan_to_subnet_mapping(transformer):
    """Meraki VLANs transform into L3 subnets."""
    vlans = {
        "N_111": [
            {"id": 10, "name": "Corporate", "subnet": "10.0.10.0/24", "applianceIp": "10.0.10.1"},
            {"id": 20, "name": "Guest", "subnet": "10.0.20.0/24", "applianceIp": "10.0.20.1"},
        ]
    }
    l3 = transformer.build_l3(vlans, [])
    assert len(l3.subnets) == 2
    assert l3.subnets[0].vlan == 10
    assert l3.subnets[0].cidr == "10.0.10.0/24"
    assert l3.subnets[0].gateway == "10.0.10.1"
```

- [ ] **Step 3: Run tests to verify failure**

```bash
cd server && pytest tests/test_meraki_transformer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'server.meraki_transformer'`

- [ ] **Step 4: Implement the transformer**

Create `server/meraki_transformer.py`:

```python
"""Transform Meraki Dashboard API responses into L2/L3 topology models.

Converts Meraki's device, topology, and VLAN data into the same
L2Topology and L3Topology Pydantic models the frontend already renders.
"""

from server.models import (
    Device, Edge, L2Topology, L3Topology, Subnet, Route,
    DeviceType, DeviceStatus, LinkProtocol,
)


PRODUCT_TYPE_MAP = {
    "appliance": DeviceType.FIREWALL,
    "switch": DeviceType.FLOOR_SWITCH,
    "wireless": DeviceType.ACCESS_POINT,
}

STATUS_MAP = {
    "online": DeviceStatus.UP,
    "offline": DeviceStatus.DOWN,
    "alerting": DeviceStatus.ALERTING,
    "dormant": DeviceStatus.DOWN,
}


class MerakiTransformer:
    """Stateless transformer from Meraki API data to topology models."""

    def build_l2(
        self,
        devices: list[dict],
        device_statuses: list[dict],
        link_layer_data: dict[str, dict],
    ) -> L2Topology:
        """Build an L2Topology from Meraki devices and link-layer data.

        Parameters
        ----------
        devices : list[dict]
            Output of GET /organizations/{orgId}/devices
        device_statuses : list[dict]
            Output of GET /organizations/{orgId}/devices/statuses
        link_layer_data : dict[str, dict]
            Map of networkId → link-layer topology response
        """
        # Build status lookup
        status_by_serial = {}
        for s in device_statuses:
            status_by_serial[s.get("serial", "")] = s

        # Build nodes
        nodes = []
        for d in devices:
            serial = d.get("serial", "")
            product_type = d.get("productType", "")
            status_info = status_by_serial.get(serial, {})
            meraki_status = status_info.get("status", d.get("status", "offline"))

            node = Device(
                id=serial,
                type=PRODUCT_TYPE_MAP.get(product_type, DeviceType.ENDPOINT),
                model=d.get("model", "Unknown"),
                ip=d.get("lanIp", "") or status_info.get("lanIp", ""),
                status=STATUS_MAP.get(meraki_status, DeviceStatus.DOWN),
                mac=d.get("mac", None),
            )
            nodes.append(node)

        # Build edges from link-layer topology
        edges = []
        seen_edges = set()
        for _network_id, topo in link_layer_data.items():
            for link in topo.get("links", []):
                ends = link.get("ends", [])
                if len(ends) != 2:
                    continue
                src_serial = ends[0].get("device", {}).get("serial", "")
                dst_serial = ends[1].get("device", {}).get("serial", "")
                if not src_serial or not dst_serial:
                    continue

                edge_key = tuple(sorted([src_serial, dst_serial]))
                if edge_key in seen_edges:
                    continue
                seen_edges.add(edge_key)

                src_port = ""
                dst_port = ""
                for proto in ("lldp", "cdp"):
                    disc0 = ends[0].get("discovered", {}).get(proto, {})
                    disc1 = ends[1].get("discovered", {}).get(proto, {})
                    if disc0:
                        src_port = disc0.get("portId", "")
                    if disc1:
                        dst_port = disc1.get("portId", "")

                edges.append(Edge(
                    id=f"{src_serial}-{dst_serial}",
                    source=src_serial,
                    target=dst_serial,
                    source_port=src_port or None,
                    target_port=dst_port or None,
                    speed="1G",
                    protocol=LinkProtocol.LLDP,
                ))

        return L2Topology(nodes=nodes, edges=edges)

    def build_l3(
        self,
        vlans_by_network: dict[str, list[dict]],
        devices: list[dict],
    ) -> L3Topology:
        """Build an L3Topology from Meraki VLANs.

        Parameters
        ----------
        vlans_by_network : dict[str, list[dict]]
            Map of networkId → VLANs list
        devices : list[dict]
            All devices (for counting devices per VLAN)
        """
        subnets = []
        for network_id, vlans in vlans_by_network.items():
            for v in vlans:
                vlan_id = v.get("id", 0)
                subnets.append(Subnet(
                    id=f"vlan-{network_id}-{vlan_id}",
                    name=v.get("name", f"VLAN {vlan_id}"),
                    vlan=vlan_id,
                    cidr=v.get("subnet", ""),
                    gateway=v.get("applianceIp", ""),
                    device_count=0,
                ))

        # Routes: each VLAN routes through the appliance gateway
        routes = []
        appliance_serials = [
            d["serial"] for d in devices
            if d.get("productType") == "appliance"
        ]
        gateway_id = appliance_serials[0] if appliance_serials else "unknown"

        for i, s1 in enumerate(subnets):
            for s2 in subnets[i + 1:]:
                routes.append(Route(
                    from_subnet=s1.id,
                    to_subnet=s2.id,
                    via=gateway_id,
                ))

        return L3Topology(subnets=subnets, routes=routes)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd server && pytest tests/test_meraki_transformer.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add server/meraki_transformer.py server/tests/test_meraki_transformer.py server/models.py
git commit -m "feat: add Meraki data transformer with L2/L3 topology mapping"
```

---

## Task 5: Meraki Server Routes + SSE Refresh

**Files:**
- Create: `server/routes/meraki.py`
- Modify: `server/main.py`
- Modify: `server/requirements.txt`

- [ ] **Step 1: Add sse-starlette dependency**

In `server/requirements.txt`, add:
```
sse-starlette==2.2.1
```

Then install:
```bash
cd server && pip install sse-starlette==2.2.1
```

- [ ] **Step 2: Create Meraki routes with SSE refresh**

Create `server/routes/meraki.py`:

```python
"""Meraki Dashboard API proxy routes.

Proxies requests to the Meraki API, transforms responses into
L2/L3 topology models, and streams progressive refresh via SSE.
"""

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Query
from sse_starlette.sse import EventSourceResponse

from server.meraki_client import MerakiClient
from server.meraki_transformer import MerakiTransformer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meraki", tags=["meraki"])

# Shared client and transformer — initialized on first use
_client: Optional[MerakiClient] = None
_transformer = MerakiTransformer()
_org_id: Optional[str] = None
_networks: list[dict] = []


def _get_client() -> MerakiClient:
    global _client
    if _client is None:
        _client = MerakiClient()
    return _client


async def _ensure_org_id() -> str:
    """Discover and cache the organization ID."""
    global _org_id
    if _org_id is not None:
        return _org_id
    client = _get_client()
    orgs = await client.get_organizations()
    if not orgs:
        raise HTTPException(status_code=404, detail="No organizations found for this API key")
    _org_id = orgs[0]["id"]
    return _org_id


@router.get("/status")
async def meraki_status():
    """Validate API key and return org info."""
    client = _get_client()
    if not client.is_configured:
        return {"configured": False, "error": "MERAKI_API_KEY not set"}
    try:
        orgs = await client.get_organizations()
        org = orgs[0] if orgs else None
        return {
            "configured": True,
            "org_id": org["id"] if org else None,
            "org_name": org.get("name") if org else None,
        }
    except Exception as e:
        return {"configured": True, "error": str(e)}


@router.get("/networks")
async def list_networks():
    """List all networks in the organization."""
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=400, detail="MERAKI_API_KEY not set")
    org_id = await _ensure_org_id()
    global _networks
    _networks = await client.get_org_networks(org_id)
    return [{"id": n["id"], "name": n.get("name", ""), "productTypes": n.get("productTypes", [])} for n in _networks]


@router.get("/topology/l2")
async def get_l2_topology(network: Optional[str] = Query(None)):
    """Get L2 topology — all networks or filtered."""
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=400, detail="MERAKI_API_KEY not set")
    org_id = await _ensure_org_id()

    devices = await client.get_org_devices(org_id)
    statuses = await client.get_org_device_statuses(org_id)

    # Filter by network if specified
    if network:
        devices = [d for d in devices if d.get("networkId") == network]
        network_ids = [network]
    else:
        network_ids = list({d.get("networkId") for d in devices if d.get("networkId")})

    # Fetch link-layer topology per network
    link_data = {}
    for nid in network_ids:
        try:
            link_data[nid] = await client.get_network_topology(nid)
        except Exception:
            logger.warning("Failed to get link-layer topology for network %s", nid)

    l2 = _transformer.build_l2(devices, statuses, link_data)
    return l2.model_dump()


@router.get("/topology/l3")
async def get_l3_topology(network: Optional[str] = Query(None)):
    """Get L3 topology — VLANs and routing."""
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=400, detail="MERAKI_API_KEY not set")
    org_id = await _ensure_org_id()

    devices = await client.get_org_devices(org_id)

    if network:
        network_ids = [network]
    else:
        network_ids = list({d.get("networkId") for d in devices if d.get("networkId")})

    vlans_by_network = {}
    for nid in network_ids:
        try:
            vlans = await client.get_network_vlans(nid)
            if vlans:
                vlans_by_network[nid] = vlans
        except Exception:
            logger.warning("Failed to get VLANs for network %s", nid)

    l3 = _transformer.build_l3(vlans_by_network, devices)
    return l3.model_dump()


@router.get("/devices/{serial}")
async def get_device_detail(serial: str):
    """Get full device detail including clients."""
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=400, detail="MERAKI_API_KEY not set")

    try:
        clients = await client.get_device_clients(serial)
    except Exception:
        clients = []

    try:
        ports = await client.get_device_switch_ports(serial)
    except Exception:
        ports = []

    return {"serial": serial, "clients": clients, "ports": ports}


@router.post("/refresh")
async def refresh_topology(network: Optional[str] = Query(None)):
    """Progressive topology refresh via Server-Sent Events.

    Streams incremental data as it arrives from the rate-limited Meraki API:
    - Phase 1 (discovery): org info, device/network counts, time estimate
    - Phase 2 (devices): placeholder nodes
    - Phase 3 (topology): per-network edges + colored nodes
    - Phase 4 (clients): per-device client data
    - Phase 5 (complete): final signal
    """
    client = _get_client()
    if not client.is_configured:
        raise HTTPException(status_code=400, detail="MERAKI_API_KEY not set")

    async def event_generator():
        start_time = time.time()
        org_id = await _ensure_org_id()

        # Phase 1: Discovery
        devices = await client.get_org_devices(org_id)
        statuses = await client.get_org_device_statuses(org_id)

        if network:
            devices = [d for d in devices if d.get("networkId") == network]
            network_ids = [network]
        else:
            network_ids = list({d.get("networkId") for d in devices if d.get("networkId")})

        # Estimate: 1 call per network (topology) + 1 per network (vlans) + 1 per device (clients)
        total_calls = len(network_ids) * 2 + len(devices)
        estimated_seconds = max(1, total_calls / 5)

        yield {
            "event": "progress",
            "data": json.dumps({
                "phase": "discovery",
                "device_count": len(devices),
                "network_count": len(network_ids),
                "estimated_seconds": round(estimated_seconds),
            }),
        }

        # Phase 2: Placeholder nodes
        placeholder_l2 = _transformer.build_l2(devices, statuses, {})
        yield {
            "event": "progress",
            "data": json.dumps({
                "phase": "devices",
                "nodes": [n.model_dump() for n in placeholder_l2.nodes],
            }),
        }

        # Phase 3: Topology per network
        link_data = {}
        vlans_by_network = {}
        for i, nid in enumerate(network_ids):
            try:
                link_data[nid] = await client.get_network_topology(nid)
            except Exception:
                logger.warning("Link-layer failed for %s", nid)

            try:
                vlans = await client.get_network_vlans(nid)
                if vlans:
                    vlans_by_network[nid] = vlans
            except Exception:
                pass

            # Build partial topology with data so far
            partial_l2 = _transformer.build_l2(devices, statuses, link_data)
            elapsed = time.time() - start_time
            remaining = max(0, estimated_seconds - elapsed)

            yield {
                "event": "progress",
                "data": json.dumps({
                    "phase": "topology",
                    "network": nid,
                    "nodes": [n.model_dump() for n in partial_l2.nodes],
                    "edges": [e.model_dump() for e in partial_l2.edges],
                    "progress": i + 1,
                    "total": len(network_ids),
                    "remaining_seconds": round(remaining),
                }),
            }

        # Phase 4: Clients per device (batch in groups of 5 for efficiency)
        device_serials = [d.get("serial", "") for d in devices if d.get("serial")]
        batch_size = 5
        for batch_start in range(0, len(device_serials), batch_size):
            batch = device_serials[batch_start:batch_start + batch_size]
            client_results = await asyncio.gather(
                *[client.get_device_clients(s) for s in batch],
                return_exceptions=True,
            )
            client_data = {}
            for serial, result in zip(batch, client_results):
                if isinstance(result, list):
                    client_data[serial] = len(result)

            elapsed = time.time() - start_time
            remaining = max(0, estimated_seconds - elapsed)

            yield {
                "event": "progress",
                "data": json.dumps({
                    "phase": "clients",
                    "client_counts": client_data,
                    "remaining_seconds": round(remaining),
                }),
            }

        # Phase 5: Complete — send final full topology
        final_l2 = _transformer.build_l2(devices, statuses, link_data)
        final_l3 = _transformer.build_l3(vlans_by_network, devices)

        yield {
            "event": "progress",
            "data": json.dumps({
                "phase": "complete",
                "l2": final_l2.model_dump(),
                "l3": final_l3.model_dump(),
            }),
        }

    return EventSourceResponse(event_generator())
```

- [ ] **Step 3: Register Meraki router in server/main.py**

In `server/main.py`, add the import (line 19):

Change:
```python
from server.routes import topology, devices, system
```
To:
```python
from server.routes import topology, devices, system, meraki
```

Add after line 71 (`app.include_router(system.router)`):
```python
app.include_router(meraki.router)
```

- [ ] **Step 4: Commit**

```bash
git add server/routes/meraki.py server/main.py server/requirements.txt
git commit -m "feat: add Meraki proxy routes with SSE progressive refresh"
```

---

## Task 6: Simulation Start/Stop Backend

**Files:**
- Create: `server/routes/simulation.py`
- Create: `server/tests/test_simulation.py`
- Modify: `server/main.py`

- [ ] **Step 1: Write failing test for simulation lifecycle**

Create `server/tests/test_simulation.py`:

```python
"""Tests for simulation start/stop/auto-shutdown lifecycle."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from server.routes.simulation import SimulationManager


@pytest.fixture
def mock_poller():
    poller = MagicMock()
    poller.start = AsyncMock()
    poller.stop = AsyncMock()
    poller.is_running = False
    return poller


@pytest.fixture
def mock_ws_manager():
    ws = MagicMock()
    ws.broadcast = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_start_simulation(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=600)
    await mgr.start(mock_poller, mock_ws_manager)
    assert mgr.is_running is True
    mock_poller.start.assert_called_once()


@pytest.mark.asyncio
async def test_stop_simulation(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=600)
    await mgr.start(mock_poller, mock_ws_manager)
    await mgr.stop(mock_poller, mock_ws_manager)
    assert mgr.is_running is False
    mock_poller.stop.assert_called_once()


@pytest.mark.asyncio
async def test_auto_shutdown(mock_poller, mock_ws_manager):
    """Simulation auto-stops after timeout."""
    mgr = SimulationManager(timeout_seconds=1)  # 1 second for test
    await mgr.start(mock_poller, mock_ws_manager)
    assert mgr.is_running is True
    await asyncio.sleep(1.5)
    assert mgr.is_running is False
    mock_ws_manager.broadcast.assert_called()


@pytest.mark.asyncio
async def test_remaining_seconds(mock_poller, mock_ws_manager):
    mgr = SimulationManager(timeout_seconds=600)
    assert mgr.remaining_seconds == 0
    await mgr.start(mock_poller, mock_ws_manager)
    remaining = mgr.remaining_seconds
    assert 595 < remaining <= 600
    await mgr.stop(mock_poller, mock_ws_manager)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd server && pytest tests/test_simulation.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement SimulationManager and routes**

Create `server/routes/simulation.py`:

```python
"""Simulation start/stop/status routes.

Manages the SNMP simulator + collector polling lifecycle with
a 10-minute auto-shutdown timer.
"""

import asyncio
import logging
import time

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simulation", tags=["simulation"])

SIMULATION_TIMEOUT = 600  # 10 minutes


class SimulationManager:
    """Manages simulation lifecycle with auto-shutdown.

    Parameters
    ----------
    timeout_seconds : int
        Auto-shutdown after this many seconds (default 600 = 10 min).
    """

    def __init__(self, timeout_seconds: int = SIMULATION_TIMEOUT):
        self._timeout = timeout_seconds
        self._running = False
        self._start_time: float = 0
        self._shutdown_task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def remaining_seconds(self) -> int:
        if not self._running:
            return 0
        elapsed = time.time() - self._start_time
        return max(0, int(self._timeout - elapsed))

    async def start(self, poller, ws_manager) -> None:
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        await poller.start()
        self._shutdown_task = asyncio.create_task(
            self._auto_shutdown(poller, ws_manager)
        )
        logger.info("Simulation started (auto-shutdown in %ds)", self._timeout)

    async def stop(self, poller, ws_manager) -> None:
        if not self._running:
            return
        self._running = False
        if self._shutdown_task:
            self._shutdown_task.cancel()
            try:
                await self._shutdown_task
            except asyncio.CancelledError:
                pass
            self._shutdown_task = None
        await poller.stop()
        await ws_manager.broadcast("simulation_stopped", {})
        logger.info("Simulation stopped")

    async def _auto_shutdown(self, poller, ws_manager) -> None:
        try:
            await asyncio.sleep(self._timeout)
            logger.info("Simulation auto-shutdown triggered after %ds", self._timeout)
            self._running = False
            await poller.stop()
            await ws_manager.broadcast("simulation_stopped", {"reason": "timeout"})
        except asyncio.CancelledError:
            pass


# Singleton manager — injected via middleware
simulation_manager = SimulationManager()


@router.post("/start")
async def start_simulation(request: Request):
    """Start the SNMP simulation and collector polling."""
    poller = request.state.poller
    ws_manager = request.state.ws_manager
    if poller is None:
        raise HTTPException(status_code=503, detail="Collector not initialized")

    await simulation_manager.start(poller, ws_manager)
    return {
        "status": "running",
        "remaining_seconds": simulation_manager.remaining_seconds,
    }


@router.post("/stop")
async def stop_simulation(request: Request):
    """Stop the SNMP simulation and collector polling."""
    poller = request.state.poller
    ws_manager = request.state.ws_manager
    if poller is None:
        raise HTTPException(status_code=503, detail="Collector not initialized")

    await simulation_manager.stop(poller, ws_manager)
    return {"status": "stopped"}


@router.get("/status")
async def simulation_status():
    """Get simulation running state and remaining time."""
    return {
        "running": simulation_manager.is_running,
        "remaining_seconds": simulation_manager.remaining_seconds,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd server && pytest tests/test_simulation.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Modify server/main.py — don't auto-start poller, register simulation router**

In `server/main.py`, modify the `lifespan` function to create the poller but **not start it** (simulation starts stopped). Replace the lifespan function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of the collector poller."""
    global poller

    # Startup: create the collector poller (but don't start — simulation starts stopped)
    poller = create_poller()

    # Register callback to broadcast topology changes via WebSocket
    async def on_topology_change(l2, l3):
        await ws_manager.broadcast("topology_update", {
            "l2": l2.model_dump() if l2 else None,
            "l3": l3.model_dump() if l3 else None,
        })

    poller.on_change(on_topology_change)
    logger.info("Collector poller created (waiting for simulation start)")

    yield

    # Shutdown
    if poller.is_running:
        await poller.stop()
    logger.info("Server shutdown complete")
```

Add the import and router registration:

```python
from server.routes import topology, devices, system, meraki, simulation
```

```python
app.include_router(simulation.router)
```

- [ ] **Step 6: Commit**

```bash
git add server/routes/simulation.py server/tests/test_simulation.py server/main.py
git commit -m "feat: add simulation start/stop with 10-minute auto-shutdown"
```

---

## Task 7: Frontend Types + Simulation Hook

**Files:**
- Modify: `ui/src/types/topology.ts`
- Create: `ui/src/types/meraki.ts`
- Create: `ui/src/hooks/useSimulation.ts`

- [ ] **Step 1: Add DataSource type, alerting status, and extend WSEvent**

In `ui/src/types/topology.ts`:

Update `DeviceStatus` to include `alerting` (matches the backend change in Task 4):
```typescript
export type DeviceStatus = 'up' | 'down' | 'degraded' | 'alerting';
```

Add at the bottom:
```typescript
// Data source selector
export type DataSource = 'simulated' | 'meraki';
```

Update the `WSEvent` type to include simulation events:
```typescript
export interface WSEvent {
  type: 'topology_update' | 'device_status' | 'connection_change' | 'metrics_update' | 'simulation_stopped';
  data: Record<string, unknown>;
}
```

- [ ] **Step 2: Create Meraki types**

Create `ui/src/types/meraki.ts`:

```typescript
/** Types for Meraki-specific data and progressive refresh. */

export interface MerakiNetwork {
  id: string;
  name: string;
  productTypes: string[];
}

export interface MerakiStatus {
  configured: boolean;
  org_id?: string;
  org_name?: string;
  error?: string;
}

/** SSE progress event phases */
export type RefreshPhase = 'discovery' | 'devices' | 'topology' | 'clients' | 'complete';

export interface RefreshProgress {
  phase: RefreshPhase;
  device_count?: number;
  network_count?: number;
  estimated_seconds?: number;
  nodes?: Record<string, unknown>[];
  edges?: Record<string, unknown>[];
  network?: string;
  progress?: number;
  total?: number;
  remaining_seconds?: number;
  client_counts?: Record<string, number>;
  l2?: Record<string, unknown>;
  l3?: Record<string, unknown>;
}
```

- [ ] **Step 3: Create useSimulation hook**

Create `ui/src/hooks/useSimulation.ts`:

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';

interface SimulationStatus {
  running: boolean;
  remaining_seconds: number;
}

interface UseSimulationReturn {
  isRunning: boolean;
  remainingSeconds: number;
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

export function useSimulation(): UseSimulationReturn {
  const [isRunning, setIsRunning] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll status on mount to sync with server state
  useEffect(() => {
    fetch('/api/simulation/status')
      .then(r => r.json())
      .then((data: SimulationStatus) => {
        setIsRunning(data.running);
        setRemainingSeconds(data.remaining_seconds);
      })
      .catch(() => {});
  }, []);

  // Countdown timer — ticks every second while running
  useEffect(() => {
    if (isRunning && remainingSeconds > 0) {
      timerRef.current = setInterval(() => {
        setRemainingSeconds(prev => {
          if (prev <= 1) {
            setIsRunning(false);
            if (timerRef.current) clearInterval(timerRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRunning, remainingSeconds]);

  const start = useCallback(async () => {
    const resp = await fetch('/api/simulation/start', { method: 'POST' });
    if (resp.ok) {
      const data: SimulationStatus = await resp.json();
      setIsRunning(true);
      setRemainingSeconds(data.remaining_seconds);
    }
  }, []);

  const stop = useCallback(async () => {
    const resp = await fetch('/api/simulation/stop', { method: 'POST' });
    if (resp.ok) {
      setIsRunning(false);
      setRemainingSeconds(0);
    }
  }, []);

  return { isRunning, remainingSeconds, start, stop };
}
```

- [ ] **Step 4: Commit**

```bash
git add ui/src/types/topology.ts ui/src/types/meraki.ts ui/src/hooks/useSimulation.ts
git commit -m "feat: add frontend types and simulation hook"
```

---

## Task 8: Meraki Topology Hook

**Files:**
- Create: `ui/src/hooks/useMerakiTopology.ts`

- [ ] **Step 1: Create the Meraki topology hook with SSE refresh**

Create `ui/src/hooks/useMerakiTopology.ts`:

```typescript
import { useState, useCallback, useRef } from 'react';
import type { L2Topology, L3Topology, Device, Edge, ViewMode, DrillDownState } from '../types/topology';
import type { MerakiNetwork, RefreshProgress, RefreshPhase } from '../types/meraki';

interface UseMerakiTopologyReturn {
  l2Topology: L2Topology | null;
  l3Topology: L3Topology | null;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  selectedDevice: Device | null;
  setSelectedDevice: (device: Device | null) => void;
  drillDown: DrillDownState;
  drillInto: (deviceId: string, label: string) => void;
  drillBack: (index: number) => void;
  drillReset: () => void;
  networks: MerakiNetwork[];
  selectedNetwork: string | null;
  setSelectedNetwork: (id: string | null) => void;
  isRefreshing: boolean;
  refreshPhase: RefreshPhase | null;
  refreshProgress: number;
  refreshTotal: number;
  remainingSeconds: number;
  lastUpdated: Date | null;
  refresh: () => void;
  isConfigured: boolean | null;
  orgName: string | null;
  clientCounts: Record<string, number>;
}

export function useMerakiTopology(): UseMerakiTopologyReturn {
  const [l2Topology, setL2Topology] = useState<L2Topology | null>(null);
  const [l3Topology, setL3Topology] = useState<L3Topology | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('l2');
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [drillDown, setDrillDown] = useState<DrillDownState>({
    path: [], currentDeviceId: null, currentVlanId: null,
  });

  const [networks, setNetworks] = useState<MerakiNetwork[]>([]);
  const [selectedNetwork, setSelectedNetwork] = useState<string | null>(null);

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshPhase, setRefreshPhase] = useState<RefreshPhase | null>(null);
  const [refreshProgress, setRefreshProgress] = useState(0);
  const [refreshTotal, setRefreshTotal] = useState(0);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [clientCounts, setClientCounts] = useState<Record<string, number>>({});

  const [isConfigured, setIsConfigured] = useState<boolean | null>(null);
  const [orgName, setOrgName] = useState<string | null>(null);

  const eventSourceRef = useRef<EventSource | null>(null);

  // Fetch networks on first call
  const fetchNetworks = useCallback(async () => {
    try {
      const statusResp = await fetch('/api/meraki/status');
      const status = await statusResp.json();
      setIsConfigured(status.configured);
      setOrgName(status.org_name ?? null);

      if (status.configured && !status.error) {
        const networksResp = await fetch('/api/meraki/networks');
        if (networksResp.ok) {
          setNetworks(await networksResp.json());
        }
      }
    } catch {
      setIsConfigured(false);
    }
  }, []);

  const refresh = useCallback(() => {
    if (isRefreshing) return;

    // Fetch networks if we haven't yet
    if (networks.length === 0) {
      fetchNetworks();
    }

    setIsRefreshing(true);
    setRefreshPhase(null);
    setRefreshProgress(0);
    setRefreshTotal(0);
    setClientCounts({});

    // Close any existing SSE connection
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = selectedNetwork
      ? `/api/meraki/refresh?network=${selectedNetwork}`
      : '/api/meraki/refresh';

    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.addEventListener('progress', (event: MessageEvent) => {
      const data: RefreshProgress = JSON.parse(event.data);

      setRefreshPhase(data.phase);
      if (data.remaining_seconds !== undefined) {
        setRemainingSeconds(data.remaining_seconds);
      }

      switch (data.phase) {
        case 'discovery':
          setRefreshTotal(data.network_count ?? 0);
          setRemainingSeconds(data.estimated_seconds ?? 0);
          break;

        case 'devices':
          if (data.nodes) {
            setL2Topology({
              nodes: data.nodes as unknown as Device[],
              edges: [],
            });
          }
          break;

        case 'topology':
          setRefreshProgress(data.progress ?? 0);
          if (data.nodes && data.edges) {
            setL2Topology({
              nodes: data.nodes as unknown as Device[],
              edges: data.edges as unknown as Edge[],
            });
          }
          break;

        case 'clients':
          if (data.client_counts) {
            setClientCounts(prev => ({ ...prev, ...data.client_counts }));
          }
          break;

        case 'complete':
          if (data.l2) {
            setL2Topology(data.l2 as unknown as L2Topology);
          }
          if (data.l3) {
            setL3Topology(data.l3 as unknown as L3Topology);
          }
          setIsRefreshing(false);
          setRefreshPhase(null);
          setLastUpdated(new Date());
          es.close();
          break;
      }
    });

    es.onerror = () => {
      setIsRefreshing(false);
      setRefreshPhase(null);
      es.close();
    };
  }, [isRefreshing, selectedNetwork, networks.length, fetchNetworks]);

  // Drill-down navigation (same pattern as useTopology)
  const drillInto = useCallback((deviceId: string, label: string) => {
    setDrillDown(prev => ({
      path: [...prev.path, { id: deviceId, label }],
      currentDeviceId: deviceId,
      currentVlanId: null,
    }));
  }, []);

  const drillBack = useCallback((index: number) => {
    setDrillDown(prev => {
      const newPath = prev.path.slice(0, index + 1);
      const last = newPath[newPath.length - 1];
      return { path: newPath, currentDeviceId: last?.id ?? null, currentVlanId: null };
    });
  }, []);

  const drillReset = useCallback(() => {
    setDrillDown({ path: [], currentDeviceId: null, currentVlanId: null });
  }, []);

  return {
    l2Topology, l3Topology, viewMode, setViewMode,
    selectedDevice, setSelectedDevice,
    drillDown, drillInto, drillBack, drillReset,
    networks, selectedNetwork, setSelectedNetwork,
    isRefreshing, refreshPhase, refreshProgress, refreshTotal,
    remainingSeconds, lastUpdated, refresh,
    isConfigured, orgName, clientCounts,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/hooks/useMerakiTopology.ts
git commit -m "feat: add Meraki topology hook with SSE progressive refresh"
```

---

## Task 9: Restructured TopBar + Source Selector

**Files:**
- Create: `ui/src/components/SourceSelector.tsx`
- Create: `ui/src/components/NetworkFilter.tsx`
- Modify: `ui/src/components/TopBar.tsx`
- Modify: `ui/src/index.css`

- [ ] **Step 1: Create SourceSelector component**

Create `ui/src/components/SourceSelector.tsx`:

```tsx
import React, { useState, useRef, useEffect } from 'react';
import type { DataSource } from '../types/topology';

interface SourceSelectorProps {
  value: DataSource;
  onChange: (source: DataSource) => void;
}

const SOURCES: { id: DataSource; label: string; tag: string; color: string }[] = [
  { id: 'simulated', label: 'Simulated', tag: 'SNMP', color: 'var(--accent-cyan)' },
  { id: 'meraki', label: 'Meraki Live', tag: 'API', color: 'var(--accent-amber)' },
];

export const SourceSelector: React.FC<SourceSelectorProps> = ({ value, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const current = SOURCES.find(s => s.id === value)!;

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: 'var(--bg-tertiary)',
          border: `1px solid ${current.color}`,
          borderRadius: '6px',
          padding: '6px 14px',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          cursor: 'pointer',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        <span style={{ color: current.color, fontWeight: 700, fontSize: '12px' }}>
          {current.label}
        </span>
        <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>&#9660;</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            marginTop: '4px',
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '6px',
            overflow: 'hidden',
            width: '200px',
            zIndex: 100,
          }}
        >
          {SOURCES.map(src => {
            const isActive = src.id === value;
            return (
              <div
                key={src.id}
                onClick={() => { onChange(src.id); setOpen(false); }}
                style={{
                  padding: '10px 14px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  background: isActive ? `${src.color}15` : 'transparent',
                  borderLeft: `3px solid ${isActive ? src.color : 'transparent'}`,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: '12px',
                }}
              >
                <span style={{ color: isActive ? src.color : 'var(--text-primary)', fontWeight: isActive ? 700 : 400 }}>
                  {src.label}
                </span>
                <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>{src.tag}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SourceSelector;
```

- [ ] **Step 2: Create NetworkFilter component**

Create `ui/src/components/NetworkFilter.tsx`:

```tsx
import React, { useState, useRef, useEffect } from 'react';
import type { MerakiNetwork } from '../types/meraki';

interface NetworkFilterProps {
  networks: MerakiNetwork[];
  value: string | null;
  onChange: (networkId: string | null) => void;
}

export const NetworkFilter: React.FC<NetworkFilterProps> = ({ networks, value, onChange }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const label = value
    ? networks.find(n => n.id === value)?.name ?? 'Unknown'
    : 'All Networks';

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '6px',
          padding: '6px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          cursor: 'pointer',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
          color: 'var(--text-secondary)',
        }}
      >
        {label}
        <span style={{ color: 'var(--text-muted)', fontSize: '9px' }}>&#9660;</span>
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            top: '100%',
            left: 0,
            marginTop: '4px',
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '6px',
            overflow: 'hidden',
            minWidth: '200px',
            maxHeight: '300px',
            overflowY: 'auto',
            zIndex: 100,
          }}
        >
          <div
            onClick={() => { onChange(null); setOpen(false); }}
            style={{
              padding: '8px 14px',
              cursor: 'pointer',
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '11px',
              color: value === null ? 'var(--accent-amber)' : 'var(--text-secondary)',
              fontWeight: value === null ? 700 : 400,
              background: value === null ? 'var(--accent-amber)10' : 'transparent',
            }}
          >
            All Networks
          </div>
          {networks.map(n => (
            <div
              key={n.id}
              onClick={() => { onChange(n.id); setOpen(false); }}
              style={{
                padding: '8px 14px',
                cursor: 'pointer',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '11px',
                color: value === n.id ? 'var(--accent-amber)' : 'var(--text-secondary)',
                fontWeight: value === n.id ? 700 : 400,
                background: value === n.id ? 'var(--accent-amber)10' : 'transparent',
              }}
            >
              {n.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default NetworkFilter;
```

- [ ] **Step 3: Rewrite TopBar.tsx with two-level navigation**

Replace entire content of `ui/src/components/TopBar.tsx`:

```tsx
import React from 'react';
import type { ViewMode, DataSource } from '../types/topology';
import type { MerakiNetwork } from '../types/meraki';
import SourceSelector from './SourceSelector';
import NetworkFilter from './NetworkFilter';

interface TopBarProps {
  dataSource: DataSource;
  onDataSourceChange: (source: DataSource) => void;
  viewMode: ViewMode;
  onViewModeChange: (mode: ViewMode) => void;
  // Simulated source
  isConnected: boolean;
  pollCount: number;
  simulationRunning: boolean;
  simulationRemaining: number;
  onSimulationStart: () => void;
  onSimulationStop: () => void;
  // Meraki source
  merakiNetworks: MerakiNetwork[];
  selectedNetwork: string | null;
  onNetworkChange: (id: string | null) => void;
  isRefreshing: boolean;
  lastUpdated: Date | null;
  onRefresh: () => void;
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function formatAgo(date: Date | null): string {
  if (!date) return '';
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ago`;
}

export const TopBar: React.FC<TopBarProps> = (props) => {
  const isSimulated = props.dataSource === 'simulated';
  const accentColor = isSimulated ? 'var(--accent-cyan)' : 'var(--accent-amber)';

  return (
    <header
      style={{
        height: '56px',
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        display: 'flex',
        alignItems: 'center',
        padding: '0 20px',
        gap: '16px',
        flexShrink: 0,
        position: 'relative',
        zIndex: 50,
      }}
    >
      {/* Source Selector */}
      <SourceSelector value={props.dataSource} onChange={props.onDataSourceChange} />

      {/* Network filter (Meraki only) */}
      {!isSimulated && (
        <NetworkFilter
          networks={props.merakiNetworks}
          value={props.selectedNetwork}
          onChange={props.onNetworkChange}
        />
      )}

      {/* View Mode Pills */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          background: 'var(--bg-primary)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '999px',
          padding: '3px',
          gap: '2px',
        }}
      >
        {([['l2', 'L2'], ['hybrid', 'L2+L3'], ['l3', 'L3']] as const).map(([mode, label]) => {
          const isActive = props.viewMode === mode;
          return (
            <button
              key={mode}
              onClick={() => props.onViewModeChange(mode)}
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '12px',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                padding: '5px 18px',
                borderRadius: '999px',
                border: 'none',
                cursor: 'pointer',
                transition: 'background 0.15s ease, color 0.15s ease',
                background: isActive ? accentColor : 'transparent',
                color: isActive ? 'var(--bg-primary)' : 'var(--text-secondary)',
                lineHeight: 1,
              }}
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Right Controls — source-dependent */}
      {isSimulated ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {props.simulationRunning && (
            <>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontFamily: "'JetBrains Mono', monospace", fontSize: '11px' }}>
                <span className="animate-pulse-dot" style={{ display: 'inline-block', width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-green)', boxShadow: '0 0 6px rgba(0,214,143,0.6)' }} />
                <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>LIVE</span>
                <span style={{ color: 'var(--text-muted)' }}>#{props.pollCount}</span>
              </div>
              <div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', color: 'var(--accent-amber)', background: 'rgba(245,166,35,0.1)', border: '1px solid rgba(245,166,35,0.2)', borderRadius: '4px', padding: '3px 8px' }}>
                {formatTime(props.simulationRemaining)} remaining
              </div>
            </>
          )}
          <button
            onClick={props.simulationRunning ? props.onSimulationStop : props.onSimulationStart}
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '11px',
              fontWeight: 700,
              padding: '6px 14px',
              borderRadius: '4px',
              border: 'none',
              cursor: 'pointer',
              background: props.simulationRunning ? 'var(--accent-red)' : 'var(--accent-cyan)',
              color: props.simulationRunning ? 'white' : 'var(--bg-primary)',
            }}
          >
            {props.simulationRunning ? '\u25A0 Stop' : '\u25B6 Start Simulation'}
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {props.lastUpdated && !props.isRefreshing && (
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: '10px', color: 'var(--text-muted)' }}>
              Updated {formatAgo(props.lastUpdated)}
            </span>
          )}
          <button
            onClick={props.onRefresh}
            disabled={props.isRefreshing}
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '11px',
              fontWeight: 600,
              padding: '5px 12px',
              borderRadius: '4px',
              border: `1px solid ${props.isRefreshing ? 'var(--border-subtle)' : 'var(--border-subtle)'}`,
              background: 'var(--bg-tertiary)',
              color: props.isRefreshing ? 'var(--text-muted)' : 'var(--text-primary)',
              cursor: props.isRefreshing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            {props.isRefreshing ? (
              <>
                <span className="spin" style={{ display: 'inline-block', width: '10px', height: '10px', border: '2px solid var(--text-muted)', borderTopColor: 'var(--accent-amber)', borderRadius: '50%' }} />
                Refreshing...
              </>
            ) : (
              '\u21BB Refresh'
            )}
          </button>
        </div>
      )}
    </header>
  );
};

export default TopBar;
```

- [ ] **Step 4: Add spin animation to index.css**

In `ui/src/index.css`, add:

```css
@keyframes spin {
  to { transform: rotate(360deg); }
}
.spin {
  animation: spin 1s linear infinite;
}
```

- [ ] **Step 5: Commit**

```bash
git add ui/src/components/SourceSelector.tsx ui/src/components/NetworkFilter.tsx ui/src/components/TopBar.tsx ui/src/index.css
git commit -m "feat: restructure TopBar with source selector, network filter, and simulation controls"
```

---

## Task 10: Progressive Loading Overlay

**Files:**
- Create: `ui/src/components/RefreshOverlay.tsx`

- [ ] **Step 1: Create RefreshOverlay component**

Create `ui/src/components/RefreshOverlay.tsx`:

```tsx
import React from 'react';
import type { RefreshPhase } from '../types/meraki';

interface RefreshOverlayProps {
  phase: RefreshPhase | null;
  progress: number;
  total: number;
  remainingSeconds: number;
}

const PHASE_LABELS: Record<RefreshPhase, string> = {
  discovery: 'Discovering organization...',
  devices: 'Placing devices...',
  topology: 'Building topology',
  clients: 'Loading clients',
  complete: 'Complete',
};

export const RefreshOverlay: React.FC<RefreshOverlayProps> = ({
  phase,
  progress,
  total,
  remainingSeconds,
}) => {
  if (!phase || phase === 'complete') return null;

  const percentage = total > 0 ? Math.round((progress / total) * 100) : 0;
  const isNearDone = phase === 'clients';
  const barColor = isNearDone ? 'var(--accent-green)' : 'var(--accent-amber)';

  let detail = '';
  if (phase === 'topology' && total > 0) {
    detail = `${progress}/${total} networks`;
  }

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 30,
        padding: '0 16px',
      }}
    >
      <div
        style={{
          background: `${barColor}12`,
          border: `1px solid ${barColor}30`,
          borderRadius: '0 0 8px 8px',
          padding: '10px 16px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
        }}
      >
        <span style={{ color: barColor, fontWeight: 700 }}>
          {PHASE_LABELS[phase]}
        </span>

        {detail && (
          <span style={{ color: 'var(--text-secondary)' }}>{detail}</span>
        )}

        {/* Progress bar */}
        <div style={{ flex: 1, background: 'var(--bg-tertiary)', borderRadius: '3px', height: '4px', overflow: 'hidden' }}>
          <div
            style={{
              background: barColor,
              width: phase === 'discovery' || phase === 'devices' ? '15%' : `${Math.max(10, percentage)}%`,
              height: '100%',
              borderRadius: '3px',
              transition: 'width 0.3s ease',
            }}
          />
        </div>

        <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
          ~{remainingSeconds}s remaining
        </span>
      </div>
    </div>
  );
};

export default RefreshOverlay;
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/components/RefreshOverlay.tsx
git commit -m "feat: add progressive loading overlay for Meraki refresh"
```

---

## Task 11: Meraki Detail Panel

**Files:**
- Create: `ui/src/components/MerakiDetailPanel.tsx`

- [ ] **Step 1: Create MerakiDetailPanel**

This component extends the existing DetailPanel pattern with Meraki-specific sections (uplinks, ports, SSIDs, full client list). Create `ui/src/components/MerakiDetailPanel.tsx`:

```tsx
import React, { useState, useEffect } from 'react';
import type { Device, L2Topology } from '../types/topology';

interface MerakiDetailPanelProps {
  device: Device | null;
  topology: L2Topology | null;
  clientCounts: Record<string, number>;
  onClose: () => void;
}

const TYPE_COLORS: Record<string, string> = {
  firewall: 'var(--device-firewall)',
  core_switch: 'var(--device-core-switch)',
  floor_switch: 'var(--device-floor-switch)',
  access_point: 'var(--device-ap)',
  endpoint: 'var(--device-endpoint)',
};

const STATUS_COLORS: Record<string, string> = {
  up: 'var(--accent-green)',
  down: 'var(--accent-red)',
  alerting: 'var(--accent-amber)',
  degraded: 'var(--accent-amber)',
};

interface DeviceDetail {
  serial: string;
  clients: { description?: string; ip?: string; mac?: string; usage?: { sent: number; recv: number }; switchport?: string; vlan?: number }[];
  ports: { portId?: string; name?: string; enabled?: boolean; poeEnabled?: boolean; type?: string; vlan?: number }[];
}

export const MerakiDetailPanel: React.FC<MerakiDetailPanelProps> = ({
  device,
  topology,
  clientCounts,
  onClose,
}) => {
  const [detail, setDetail] = useState<DeviceDetail | null>(null);
  const [loading, setLoading] = useState(false);

  // Fetch full detail when device changes
  useEffect(() => {
    if (!device) {
      setDetail(null);
      return;
    }
    setLoading(true);
    fetch(`/api/meraki/devices/${device.id}`)
      .then(r => r.json())
      .then((data: DeviceDetail) => {
        setDetail(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [device?.id]);

  if (!device) return null;

  const color = TYPE_COLORS[device.type] ?? 'var(--text-muted)';
  const statusColor = STATUS_COLORS[device.status] ?? 'var(--text-muted)';
  const clientCount = clientCounts[device.id] ?? 0;

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        right: 0,
        bottom: 0,
        width: '360px',
        background: 'var(--bg-secondary)',
        borderLeft: '1px solid var(--border-subtle)',
        zIndex: 40,
        display: 'flex',
        flexDirection: 'column',
        fontFamily: "'JetBrains Mono', monospace",
        overflowY: 'auto',
      }}
    >
      {/* Header */}
      <div style={{ padding: '16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
              <span style={{ width: '10px', height: '10px', borderRadius: '50%', background: statusColor, display: 'inline-block' }} />
              <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary)' }}>{device.id}</span>
            </div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', lineHeight: 1.8 }}>
              <div>Model: {device.model} &nbsp;|&nbsp; Status: {device.status.toUpperCase()}</div>
              <div>IP: {device.ip || 'N/A'} &nbsp;|&nbsp; MAC: {device.mac || 'N/A'}</div>
              {clientCount > 0 && <div>Clients: {clientCount}</div>}
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '18px', padding: '0 4px' }}
          >
            &times;
          </button>
        </div>
        <div style={{ height: '2px', background: color, borderRadius: '1px', marginTop: '12px' }} />
      </div>

      {/* Loading state */}
      {loading && (
        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '11px' }}>
          Loading detail...
        </div>
      )}

      {/* Clients section */}
      {detail && detail.clients.length > 0 && (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ color: 'var(--accent-amber)', fontSize: '10px', fontWeight: 700, marginBottom: '8px' }}>
            CLIENTS ({detail.clients.length})
          </div>
          {detail.clients.slice(0, 20).map((c, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-secondary)', lineHeight: 2 }}>
              <span>{c.description || c.mac || 'Unknown'}</span>
              <span style={{ color: 'var(--text-muted)' }}>{c.ip || ''}</span>
            </div>
          ))}
          {detail.clients.length > 20 && (
            <div style={{ fontSize: '9px', color: 'var(--text-muted)', marginTop: '4px' }}>
              + {detail.clients.length - 20} more...
            </div>
          )}
        </div>
      )}

      {/* Switch Ports section */}
      {detail && detail.ports.length > 0 && (
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ color: 'var(--accent-amber)', fontSize: '10px', fontWeight: 700, marginBottom: '8px' }}>
            PORTS ({detail.ports.length})
          </div>
          {detail.ports.slice(0, 10).map((p, i) => (
            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-secondary)', lineHeight: 2 }}>
              <span>Port {p.portId}{p.name ? ` — ${p.name}` : ''}</span>
              <span style={{ color: 'var(--text-muted)' }}>
                {p.type ?? ''} {p.vlan ? `VLAN ${p.vlan}` : ''}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Neighbors from topology */}
      {topology && (
        <div style={{ padding: '12px 16px' }}>
          <div style={{ color: 'var(--accent-amber)', fontSize: '10px', fontWeight: 700, marginBottom: '8px' }}>
            NEIGHBORS
          </div>
          {topology.edges
            .filter(e => e.source === device.id || e.target === device.id)
            .slice(0, 10)
            .map(e => {
              const neighborId = e.source === device.id ? e.target : e.source;
              const port = e.source === device.id ? e.source_port : e.target_port;
              return (
                <div key={e.id} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-secondary)', lineHeight: 2 }}>
                  <span>{port ? `${port} → ` : ''}{neighborId}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{e.protocol}</span>
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
};

export default MerakiDetailPanel;
```

- [ ] **Step 2: Commit**

```bash
git add ui/src/components/MerakiDetailPanel.tsx
git commit -m "feat: add Meraki detail panel with clients and port info"
```

---

## Task 12: Wire Everything in App.tsx + Docker Config

**Files:**
- Modify: `ui/src/App.tsx`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Rewrite App.tsx to integrate all sources**

Replace entire content of `ui/src/App.tsx`:

```tsx
import { useState, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import { useSimulation } from './hooks/useSimulation';
import { useMerakiTopology } from './hooks/useMerakiTopology';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import DetailPanel from './components/DetailPanel';
import MerakiDetailPanel from './components/MerakiDetailPanel';
import RefreshOverlay from './components/RefreshOverlay';
import L3View from './components/L3View';
import HybridView from './components/HybridView';
import type { DataSource } from './types/topology';

function App() {
  const [dataSource, setDataSource] = useState<DataSource>('simulated');

  const sim = useSimulation();
  const topo = useTopology();
  const meraki = useMerakiTopology();

  // Trigger Meraki refresh on first switch to Meraki tab
  const [merakiInitialized, setMerakiInitialized] = useState(false);
  useEffect(() => {
    if (dataSource === 'meraki' && !merakiInitialized) {
      setMerakiInitialized(true);
      meraki.refresh();
    }
  }, [dataSource, merakiInitialized, meraki.refresh]);

  // Pick active data based on source
  const isSimulated = dataSource === 'simulated';
  const l2 = isSimulated ? topo.l2Topology : meraki.l2Topology;
  const l3 = isSimulated ? topo.l3Topology : meraki.l3Topology;
  const viewMode = isSimulated ? topo.viewMode : meraki.viewMode;
  const setViewMode = isSimulated ? topo.setViewMode : meraki.setViewMode;
  const selectedDevice = isSimulated ? topo.selectedDevice : meraki.selectedDevice;
  const setSelectedDevice = isSimulated ? topo.setSelectedDevice : meraki.setSelectedDevice;
  const drillDown = isSimulated ? topo.drillDown : meraki.drillDown;
  const drillInto = isSimulated ? topo.drillInto : meraki.drillInto;
  const drillBack = isSimulated ? topo.drillBack : meraki.drillBack;
  const drillReset = isSimulated ? topo.drillReset : meraki.drillReset;

  const showSimLoading = isSimulated && topo.isLoading && sim.isRunning;
  const showSimStopped = isSimulated && !sim.isRunning;

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <TopBar
        dataSource={dataSource}
        onDataSourceChange={setDataSource}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        isConnected={topo.isConnected}
        pollCount={topo.pollCount}
        simulationRunning={sim.isRunning}
        simulationRemaining={sim.remainingSeconds}
        onSimulationStart={sim.start}
        onSimulationStop={sim.stop}
        merakiNetworks={meraki.networks}
        selectedNetwork={meraki.selectedNetwork}
        onNetworkChange={meraki.setSelectedNetwork}
        isRefreshing={meraki.isRefreshing}
        lastUpdated={meraki.lastUpdated}
        onRefresh={meraki.refresh}
      />
      <div className="flex-1 relative overflow-hidden">
        {/* Simulated: stopped state */}
        {showSimStopped ? (
          <div className="flex items-center justify-center h-full">
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)', textAlign: 'center' }}>
              <div style={{ fontSize: '14px', marginBottom: '8px' }}>Simulation stopped.</div>
              <div style={{ fontSize: '11px' }}>Click Start Simulation to begin.</div>
            </div>
          </div>
        ) : showSimLoading ? (
          <div className="flex items-center justify-center h-full">
            <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}>
              SCANNING NETWORK...
            </div>
          </div>
        ) : viewMode === 'l2' ? (
          <ReactFlowProvider>
            <TopologyCanvas
              topology={l2}
              selectedDevice={selectedDevice}
              onSelectDevice={setSelectedDevice}
              drillDown={drillDown}
              onDrillInto={drillInto}
              onDrillBack={drillBack}
              onDrillReset={drillReset}
              deviceAnimations={isSimulated ? topo.deviceAnimations : undefined}
              pinnedDeviceIds={isSimulated ? topo.pinnedDeviceIds : undefined}
            />
          </ReactFlowProvider>
        ) : viewMode === 'hybrid' ? (
          <ReactFlowProvider>
            <HybridView
              l2Topology={l2}
              l3Topology={l3}
              onSelectDevice={setSelectedDevice}
              onSelectVlan={() => {}}
            />
          </ReactFlowProvider>
        ) : (
          <ReactFlowProvider>
            <L3View topology={l3} onSelectVlan={() => {}} />
          </ReactFlowProvider>
        )}

        {/* Meraki refresh overlay */}
        {!isSimulated && meraki.isRefreshing && (
          <RefreshOverlay
            phase={meraki.refreshPhase}
            progress={meraki.refreshProgress}
            total={meraki.refreshTotal}
            remainingSeconds={meraki.remainingSeconds}
          />
        )}

        {/* Detail panel — source-specific */}
        {(viewMode === 'l2' || viewMode === 'hybrid') && isSimulated && (
          <DetailPanel
            device={selectedDevice}
            topology={l2}
            onClose={() => setSelectedDevice(null)}
          />
        )}
        {(viewMode === 'l2' || viewMode === 'hybrid') && !isSimulated && (
          <MerakiDetailPanel
            device={selectedDevice}
            topology={l2}
            clientCounts={meraki.clientCounts}
            onClose={() => setSelectedDevice(null)}
          />
        )}
      </div>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Update docker-compose.yml**

In `docker-compose.yml`, add `MERAKI_API_KEY` to the server service environment:

```yaml
  server:
    build:
      context: .
      dockerfile: server/Dockerfile
    ports:
      - "8000:8000"
    depends_on:
      simulator:
        condition: service_healthy
    environment:
      - SIMULATOR_HOST=simulator
      - SIMULATOR_REST_PORT=8001
      - MERAKI_API_KEY=${MERAKI_API_KEY:-}
```

- [ ] **Step 3: Verify frontend builds**

```bash
cd ui && npm run build
```

Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add ui/src/App.tsx docker-compose.yml
git commit -m "feat: wire up source selector, simulation controls, and Meraki integration"
```

---

## Task 13: Integration Test + Final Verification

**Files:** None new — testing existing.

- [ ] **Step 1: Start the backend and verify simulation routes**

```bash
cd server && MERAKI_API_KEY="" python -m uvicorn server.main:app --host 0.0.0.0 --port 8000 &
sleep 3

# Simulation should start stopped
curl -s http://localhost:8000/api/simulation/status | python -m json.tool
```

Expected: `{"running": false, "remaining_seconds": 0}`

- [ ] **Step 2: Test simulation start**

```bash
curl -s -X POST http://localhost:8000/api/simulation/start | python -m json.tool
```

Expected: `{"status": "running", "remaining_seconds": 600}` (approximately)

- [ ] **Step 3: Test simulation stop**

```bash
curl -s -X POST http://localhost:8000/api/simulation/stop | python -m json.tool
```

Expected: `{"status": "stopped"}`

- [ ] **Step 4: Test Meraki status (no key configured)**

```bash
curl -s http://localhost:8000/api/meraki/status | python -m json.tool
```

Expected: `{"configured": false, "error": "MERAKI_API_KEY not set"}`

- [ ] **Step 5: Start frontend dev server and test in browser**

```bash
cd ui && npm run dev
```

Open http://localhost:5173 and verify:
- Source selector dropdown shows "Simulated" and "Meraki Live"
- Simulated tab shows "Simulation stopped. Click Start Simulation to begin."
- Clicking Start starts the simulation with LIVE indicator and countdown
- Clicking Stop returns to stopped state
- Switching to Meraki shows unconfigured state (since no API key)
- View mode pills (L2/L3/Hybrid) work for both sources

- [ ] **Step 6: Run all backend tests**

```bash
cd server && pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 7: Kill background server and commit final state**

```bash
kill %1 2>/dev/null
git add -A
git commit -m "feat: complete Meraki Live Topology integration"
```

---
