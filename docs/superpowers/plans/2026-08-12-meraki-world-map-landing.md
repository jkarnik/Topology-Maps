# Meraki World Map Landing View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Meraki Live the default data source, and add a world-map landing view (sites as circles sized by device count, colored by health) that zooms/fades into the existing per-site topology view on click.

**Architecture:** One new backend aggregation (`MerakiTransformer.build_sites`) reuses data already fetched elsewhere (org devices, availabilities, networks) to produce a `Site` per network — no new Meraki API calls. A new `GET /api/meraki/sites` route exposes it, with a lightweight SQLite-backed cache mirroring the existing `/cache/load`/`/cache/save` pattern. On the frontend, a new `WorldMapView` component (bundled static world-outline SVG paths + projected site circles) becomes the Meraki landing screen; clicking a site reuses the existing `selectedNetwork` machinery unchanged and plays a CSS scale/fade transition into the existing topology view.

**Tech Stack:** FastAPI + Pydantic (backend, unchanged), React + TypeScript + inline styles (frontend, unchanged). No new dependencies on either side.

**Spec:** `docs/superpowers/specs/2026-08-12-meraki-world-map-landing-design.md`

## Global Constraints

- Read-only from Meraki/vendor APIs — never write back (project-wide constraint, `CLAUDE.md`).
- No new Meraki API calls: `build_sites` uses only `get_org_devices`, `get_org_networks`, `get_org_device_availabilities` — all already called elsewhere in `server/routes/meraki.py`.
- Health bucket thresholds (on `unhealthy_pct = (alerting + offline) / (online + alerting + offline)`): `= 0%` → `green` `#2ecc71`; `> 0% and ≤ 25%` → `yellow` `#f1c40f`; `> 25% and ≤ 60%` → `orange` `#e67e22`; `> 60%` → `red` `#e74c3c`; denominator `0` (no data) → `unknown` `#5a6472`.
- `dormant` devices are excluded from that denominator entirely.
- Circle size is `device_count` (all statuses), square-root scaled, clamped to `[6, 26]` px radius.
- No new frontend dependencies — no mapping library, no animation library. Zoom/fade is plain CSS `transform`/`opacity` transitions driven by React state.
- No frontend test infrastructure exists today and none is introduced — frontend tasks are verified via `tsc --noEmit` (types) and a manual browser pass (Task 11).

---

### Task 1: Backend — `Site` model + `build_sites` aggregation

**Files:**
- Modify: `server/models.py` (add `HealthBucket` enum + `Site` model)
- Modify: `server/meraki_transformer.py` (add `build_sites` method + `_health_bucket` helper)
- Test: `server/tests/test_meraki_sites.py`

**Interfaces:**
- Produces: `MerakiTransformer.build_sites(networks: list[dict], devices: list[dict], availabilities: list[dict]) -> list[Site]`. `Site` fields: `network_id: str`, `name: str`, `lat: Optional[float]`, `lng: Optional[float]`, `device_count: int`, `health_bucket: HealthBucket`, `unhealthy_pct: Optional[float]`, `mapped: bool`. `HealthBucket` values: `"green" | "yellow" | "orange" | "red" | "unknown"`.

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_meraki_sites.py`:

```python
"""Tests for MerakiTransformer.build_sites — world map landing aggregation."""

import pytest

from server.meraki_transformer import MerakiTransformer
from server.models import HealthBucket


@pytest.fixture
def transformer():
    return MerakiTransformer()


NETWORKS = [
    {"id": "N_1", "name": "Dallas DC"},
    {"id": "N_2", "name": "Warehouse B"},
]


def test_resolves_location_from_first_device_with_coords(transformer):
    devices = [
        {"serial": "S1", "networkId": "N_1", "lat": None, "lng": None},
        {"serial": "S2", "networkId": "N_1", "lat": 32.78, "lng": -96.80},
    ]
    sites = transformer.build_sites(NETWORKS, devices, [])
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.mapped is True
    assert dallas.lat == 32.78
    assert dallas.lng == -96.80


def test_network_with_no_coords_is_unmapped(transformer):
    devices = [{"serial": "S1", "networkId": "N_2", "lat": None, "lng": None}]
    sites = transformer.build_sites(NETWORKS, devices, [])
    warehouse = next(s for s in sites if s.network_id == "N_2")
    assert warehouse.mapped is False
    assert warehouse.lat is None
    assert warehouse.lng is None


def test_device_count_includes_all_statuses(transformer):
    devices = [
        {"serial": "S1", "networkId": "N_1", "lat": 1.0, "lng": 2.0},
        {"serial": "S2", "networkId": "N_1", "lat": None, "lng": None},
        {"serial": "S3", "networkId": "N_1", "lat": None, "lng": None},
    ]
    sites = transformer.build_sites(NETWORKS, devices, [])
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.device_count == 3


@pytest.mark.parametrize(
    "statuses,expected_bucket,expected_pct",
    [
        (["online", "online", "online", "online"], HealthBucket.GREEN, 0.0),
        (["online", "online", "online", "alerting"], HealthBucket.YELLOW, 0.25),
        (["online", "online", "alerting", "offline"], HealthBucket.ORANGE, 0.5),
        (["offline", "offline", "offline", "online"], HealthBucket.RED, 0.75),
    ],
)
def test_health_bucket_thresholds(transformer, statuses, expected_bucket, expected_pct):
    devices = [
        {"serial": f"S{i}", "networkId": "N_1", "lat": None, "lng": None}
        for i in range(len(statuses))
    ]
    availabilities = [
        {"serial": f"S{i}", "status": status} for i, status in enumerate(statuses)
    ]
    sites = transformer.build_sites(NETWORKS, devices, availabilities)
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.health_bucket == expected_bucket
    assert dallas.unhealthy_pct == pytest.approx(expected_pct)


def test_dormant_devices_excluded_from_denominator(transformer):
    devices = [
        {"serial": "S1", "networkId": "N_1", "lat": None, "lng": None},
        {"serial": "S2", "networkId": "N_1", "lat": None, "lng": None},
    ]
    availabilities = [
        {"serial": "S1", "status": "online"},
        {"serial": "S2", "status": "dormant"},
    ]
    sites = transformer.build_sites(NETWORKS, devices, availabilities)
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.unhealthy_pct == 0.0
    assert dallas.health_bucket == HealthBucket.GREEN


def test_no_availability_data_is_unknown_not_green(transformer):
    devices = [{"serial": "S1", "networkId": "N_1", "lat": None, "lng": None}]
    sites = transformer.build_sites(NETWORKS, devices, [])
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.health_bucket == HealthBucket.UNKNOWN
    assert dallas.unhealthy_pct is None


def test_network_with_zero_devices(transformer):
    sites = transformer.build_sites(NETWORKS, [], [])
    warehouse = next(s for s in sites if s.network_id == "N_2")
    assert warehouse.device_count == 0
    assert warehouse.mapped is False
    assert warehouse.health_bucket == HealthBucket.UNKNOWN


def test_empty_networks_returns_empty_list(transformer):
    assert transformer.build_sites([], [{"serial": "S1", "networkId": "N_1"}], []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest server/tests/test_meraki_sites.py -v`
Expected: FAIL — `ImportError: cannot import name 'HealthBucket' from 'server.models'` (or `AttributeError: 'MerakiTransformer' object has no attribute 'build_sites'`).

- [ ] **Step 3: Add `HealthBucket` and `Site` to `server/models.py`**

Add after the `L3Topology` class (after line 133, before the `# --- Connection Edit ---` section):

```python
# --- Site Models (world map landing view) ---

class HealthBucket(str, Enum):
    GREEN = "green"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"
    UNKNOWN = "unknown"


class Site(BaseModel):
    network_id: str
    name: str
    lat: Optional[float] = None
    lng: Optional[float] = None
    device_count: int = 0
    health_bucket: HealthBucket = HealthBucket.UNKNOWN
    unhealthy_pct: Optional[float] = None
    mapped: bool = False
```

- [ ] **Step 4: Add `build_sites` to `server/meraki_transformer.py`**

Update the import block at the top to include the two new models:

```python
from server.models import (
    Device,
    DeviceStatus,
    DeviceType,
    Edge,
    HealthBucket,
    L2Topology,
    L3Topology,
    LinkProtocol,
    Route,
    RoutingPolicy,
    Site,
    Subnet,
)
```

Add this method to `MerakiTransformer`, immediately after `build_l3` (after line 358, before the class ends):

```python
    # ------------------------------------------------------------------
    # Sites (world map landing view)
    # ------------------------------------------------------------------

    def build_sites(
        self,
        networks: list[dict],
        devices: list[dict],
        availabilities: list[dict],
    ) -> list[Site]:
        """Aggregate one Site summary per network for the world map view.

        Args:
            networks: List of network objects from GET /organizations/{id}/networks.
            devices: List of device objects from GET /organizations/{id}/devices.
                Location is resolved from each device's `lat`/`lng` fields,
                which Meraki populates when an address is configured.
            availabilities: List of availability objects from
                GET /organizations/{id}/devices/availabilities.

        Returns:
            One Site per input network, in the same order.
        """
        devices_by_network: dict[str, list[dict]] = {}
        for dev in devices:
            net_id = dev.get("networkId")
            if not net_id:
                continue
            devices_by_network.setdefault(net_id, []).append(dev)

        status_by_serial: dict[str, str] = {
            a["serial"]: a.get("status", "")
            for a in availabilities
            if "serial" in a
        }

        sites: list[Site] = []
        for net in networks:
            net_id = net.get("id")
            if not net_id:
                continue
            net_devices = devices_by_network.get(net_id, [])

            lat: Optional[float] = None
            lng: Optional[float] = None
            for dev in net_devices:
                dev_lat, dev_lng = dev.get("lat"), dev.get("lng")
                if dev_lat is not None and dev_lng is not None:
                    lat, lng = dev_lat, dev_lng
                    break

            online = alerting = offline = 0
            for dev in net_devices:
                serial = dev.get("serial")
                status = status_by_serial.get(serial, "") if serial else ""
                if status == "online":
                    online += 1
                elif status == "alerting":
                    alerting += 1
                elif status == "offline":
                    offline += 1
                # "dormant" and unknown/missing statuses are excluded from
                # the denominator entirely — see docstring above.

            denominator = online + alerting + offline
            unhealthy_pct = (alerting + offline) / denominator if denominator else None

            sites.append(
                Site(
                    network_id=net_id,
                    name=net.get("name", net_id),
                    lat=lat,
                    lng=lng,
                    device_count=len(net_devices),
                    health_bucket=_health_bucket(unhealthy_pct),
                    unhealthy_pct=unhealthy_pct,
                    mapped=lat is not None and lng is not None,
                )
            )

        return sites
```

Add this helper next to the other private helpers at the bottom of the file (after `_detect_protocol`):

```python
def _health_bucket(unhealthy_pct: Optional[float]) -> HealthBucket:
    """Bucket a site's unhealthy-device ratio into the 5-tier health scale.

    Boundaries: 0% -> green, (0%, 25%] -> yellow, (25%, 60%] -> orange,
    >60% -> red. No data at all (ratio is None) -> unknown.
    """
    if unhealthy_pct is None:
        return HealthBucket.UNKNOWN
    if unhealthy_pct == 0:
        return HealthBucket.GREEN
    if unhealthy_pct <= 0.25:
        return HealthBucket.YELLOW
    if unhealthy_pct <= 0.60:
        return HealthBucket.ORANGE
    return HealthBucket.RED
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python3 -m pytest server/tests/test_meraki_sites.py -v`
Expected: PASS (9 tests).

- [ ] **Step 6: Run the full backend suite to check for regressions**

Run: `python3 -m pytest`
Expected: all tests pass (previous count + 9).

- [ ] **Step 7: Commit**

```bash
git add server/models.py server/meraki_transformer.py server/tests/test_meraki_sites.py
git commit -m "feat: add build_sites aggregation for world map landing view"
```

---

### Task 2: Backend — sites snapshot persistence in `db.py`

**Files:**
- Modify: `server/db.py`
- Test: `server/tests/test_db_snapshot.py` (append)

**Interfaces:**
- Consumes: nothing new (uses existing `meta_get`, `_conn`, `_write_lock` already in `db.py`).
- Produces: `save_sites_snapshot(sites: list[dict[str, Any]]) -> None`, `load_sites_snapshot() -> Optional[list[dict[str, Any]]]`.

- [ ] **Step 1: Write the failing tests**

Append to `server/tests/test_db_snapshot.py` (reuses the existing `patched_db` fixture already in that file):

```python
def test_load_sites_snapshot_returns_none_when_empty(patched_db):
    assert patched_db.load_sites_snapshot() is None


def test_save_and_load_sites_snapshot_round_trips(patched_db):
    sites = [
        {
            "network_id": "N_1", "name": "Dallas DC", "lat": 32.78, "lng": -96.80,
            "device_count": 84, "health_bucket": "orange", "unhealthy_pct": 0.34,
            "mapped": True,
        },
    ]
    patched_db.save_sites_snapshot(sites)
    result = patched_db.load_sites_snapshot()
    assert result == sites


def test_save_sites_snapshot_overwrites_previous(patched_db):
    patched_db.save_sites_snapshot([
        {"network_id": "N_1", "name": "Old", "device_count": 1, "health_bucket": "unknown",
         "mapped": False, "lat": None, "lng": None, "unhealthy_pct": None},
    ])
    patched_db.save_sites_snapshot([
        {"network_id": "N_2", "name": "New", "device_count": 2, "health_bucket": "green",
         "mapped": False, "lat": None, "lng": None, "unhealthy_pct": 0.0},
    ])
    result = patched_db.load_sites_snapshot()
    assert len(result) == 1
    assert result[0]["network_id"] == "N_2"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest server/tests/test_db_snapshot.py -v`
Expected: FAIL — `AttributeError: module 'server.db' has no attribute 'save_sites_snapshot'`.

- [ ] **Step 3: Add the two functions to `server/db.py`**

Add immediately after `load_snapshot` (after its closing, i.e. after the function that currently ends the file's snapshot section):

```python
# --------------------------------------------------------------------------- #
# Sites cache (world map landing view) — single JSON blob in `meta`.
# Kept independent of save_snapshot/load_snapshot above: the sites list has
# a different lifecycle (fetched once on landing) and a much lighter
# payload than the per-network topology cache, so it doesn't need its own
# table — one `meta` row is enough.
# --------------------------------------------------------------------------- #


def save_sites_snapshot(sites: list[dict[str, Any]]) -> None:
    """Persist the world-map sites list, replacing whatever was stored."""
    with _write_lock:
        _conn().execute(
            "INSERT INTO meta(key, value) VALUES ('sites', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(sites),),
        )


def load_sites_snapshot() -> Optional[list[dict[str, Any]]]:
    """Return the persisted sites list, or None if nothing stored yet."""
    raw = meta_get("sites")
    if raw is None:
        return None
    return json.loads(raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest server/tests/test_db_snapshot.py -v`
Expected: PASS (previous tests in this file + 3 new ones).

- [ ] **Step 5: Run the full backend suite to check for regressions**

Run: `python3 -m pytest`
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/db.py server/tests/test_db_snapshot.py
git commit -m "feat: persist world map sites snapshot in SQLite"
```

---

### Task 3: Backend — wire up `/api/meraki/sites*` routes

**Files:**
- Modify: `server/routes/meraki.py`

**Interfaces:**
- Consumes: `_transformer.build_sites(...)` (Task 1), `db.save_sites_snapshot`/`db.load_sites_snapshot` (Task 2), `_get_org_id()`/`_get_client()` (already in this file).
- Produces: `GET /api/meraki/sites`, `GET /api/meraki/sites/cache/load`, `POST /api/meraki/sites/cache/save`.

No automated test for this task — it's thin route wiring over already-tested logic (`build_sites` and the `db` functions each have full unit coverage from Tasks 1–2), and the existing `server/routes/meraki.py` has no precedent of route-level tests for this file (its tests exercise `MerakiClient` and `MerakiTransformer` directly instead). Verified manually in Step 3 below.

- [ ] **Step 1: Add the `GET /sites` route**

Insert immediately after `get_l3_topology` (right before the `# GET /api/meraki/devices/{serial}` section comment):

```python
# ---------------------------------------------------------------------------
# GET /api/meraki/sites
# ---------------------------------------------------------------------------


@router.get("/sites")
async def get_sites():
    """Return one aggregated entry per network for the world map landing view.

    Reuses org devices, availabilities, and networks — no new Meraki API
    surface beyond what /topology/l2 and /networks already fetch.
    """
    org_id = await _get_org_id()
    client = _get_client()

    try:
        devices, networks, availabilities = await asyncio.gather(
            client.get_org_devices(org_id),
            client.get_org_networks(org_id),
            client.get_org_device_availabilities(org_id),
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Meraki API error: {exc.response.text}",
        ) from exc

    sites = _transformer.build_sites(networks, devices, availabilities)
    return {"sites": [s.model_dump() for s in sites]}
```

- [ ] **Step 2: Add the sites cache routes**

Insert at the end of the file, after the existing `save_cache` function:

```python
# ---------------------------------------------------------------------------
# GET  /api/meraki/sites/cache/load
# POST /api/meraki/sites/cache/save
# ---------------------------------------------------------------------------
# Same server-side persistence pattern as /cache/load and /cache/save above,
# but for the lightweight sites list only — kept independent so the world
# map can paint from cache without touching the (much heavier) per-network
# topology cache.


@router.get("/sites/cache/load")
def load_sites_cache():
    """Return the persisted sites list, or 404 if empty."""
    sites = db.load_sites_snapshot()
    if sites is None:
        raise HTTPException(status_code=404, detail="No cached sites")
    return {"sites": sites}


@router.post("/sites/cache/save")
def save_sites_cache(payload: dict[str, Any] = Body(...)):
    """Replace the persisted sites list with the given snapshot."""
    sites = payload.get("sites")
    if not isinstance(sites, list):
        raise HTTPException(status_code=400, detail="Expected {'sites': [...]}")
    db.save_sites_snapshot(sites)
    return {"saved": True, "rows": len(sites)}
```

- [ ] **Step 3: Manually verify**

Start the server (`docker compose up --build` or run the FastAPI app directly), then:

```bash
# Without MERAKI_API_KEY set, /sites should 401 like the other org-level
# Meraki routes (get_status, get_networks) — confirms the route is wired
# and _get_org_id() is reached correctly:
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/meraki/sites
# Expected: 401

# The cache endpoints don't touch Meraki at all — round-trip a fixture
# payload to confirm the SQLite persistence path works end-to-end:
curl -s -X POST http://localhost:8000/api/meraki/sites/cache/save \
  -H "Content-Type: application/json" \
  -d '{"sites":[{"network_id":"N_1","name":"Test Site","lat":32.78,"lng":-96.80,"device_count":5,"health_bucket":"green","unhealthy_pct":0.0,"mapped":true}]}'
# Expected: {"saved":true,"rows":1}

curl -s http://localhost:8000/api/meraki/sites/cache/load
# Expected: {"sites":[{"network_id":"N_1","name":"Test Site", ...}]}
```

- [ ] **Step 4: Commit**

```bash
git add server/routes/meraki.py
git commit -m "feat: wire up /api/meraki/sites routes"
```

---

### Task 4: Frontend — types + health colors + world projection math

**Files:**
- Modify: `ui/src/types/meraki.ts`
- Create: `ui/src/lib/healthColors.ts`
- Create: `ui/src/lib/worldProjection.ts`

**Interfaces:**
- Produces: type `HealthBucket`, interface `MerakiSite` (mirrors the backend `Site` model from Task 1); `HEALTH_COLORS: Record<HealthBucket, string>`; `WORLD_VIEWBOX: { width: number; height: number }`, `project(lat: number, lng: number): { x: number; y: number }`, `radiusForDeviceCount(deviceCount: number, maxDeviceCount: number): number`.

No frontend test infrastructure exists in this repo (see Global Constraints) — verified via TypeScript's own type checker.

- [ ] **Step 1: Add types to `ui/src/types/meraki.ts`**

Append to the end of the file:

```ts
export type HealthBucket = 'green' | 'yellow' | 'orange' | 'red' | 'unknown';

/**
 * One aggregated entry per Meraki network for the world map landing view.
 * Mirrors the backend `Site` model (server/models.py).
 */
export interface MerakiSite {
  network_id: string;
  name: string;
  lat: number | null;
  lng: number | null;
  device_count: number;
  health_bucket: HealthBucket;
  unhealthy_pct: number | null;
  mapped: boolean;
}
```

- [ ] **Step 2: Create `ui/src/lib/healthColors.ts`**

```ts
import { HealthBucket } from '../types/meraki';

export const HEALTH_COLORS: Record<HealthBucket, string> = {
  green: '#2ecc71',
  yellow: '#f1c40f',
  orange: '#e67e22',
  red: '#e74c3c',
  unknown: '#5a6472',
};

export const HEALTH_LABELS: Record<HealthBucket, string> = {
  green: 'Healthy',
  yellow: 'Minor issues',
  orange: 'Degraded',
  red: 'Critical',
  unknown: 'No data',
};
```

- [ ] **Step 3: Create `ui/src/lib/worldProjection.ts`**

```ts
/**
 * Equirectangular lat/lng -> x/y projection, calibrated to WORLD_VIEWBOX
 * and to the coordinates baked into assets/worldOutline.ts.
 */
export const WORLD_VIEWBOX = { width: 1000, height: 500 };

export function project(lat: number, lng: number): { x: number; y: number } {
  const x = ((lng + 180) / 360) * WORLD_VIEWBOX.width;
  const y = ((90 - lat) / 180) * WORLD_VIEWBOX.height;
  return { x, y };
}

/**
 * Square-root scaling (perceptual area accuracy, not linear radius) from
 * device count to circle radius, clamped so small sites stay clickable
 * and huge sites don't dominate the map.
 */
const MIN_RADIUS = 6;
const MAX_RADIUS = 26;

export function radiusForDeviceCount(deviceCount: number, maxDeviceCount: number): number {
  if (maxDeviceCount <= 0) return MIN_RADIUS;
  const scale = Math.sqrt(Math.max(deviceCount, 0) / maxDeviceCount);
  return MIN_RADIUS + scale * (MAX_RADIUS - MIN_RADIUS);
}
```

- [ ] **Step 4: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors related to these three files (pre-existing unrelated errors, if any, are out of scope).

- [ ] **Step 5: Commit**

```bash
git add ui/src/types/meraki.ts ui/src/lib/healthColors.ts ui/src/lib/worldProjection.ts
git commit -m "feat: add MerakiSite types, health colors, and world projection math"
```

---

### Task 5: Frontend — world outline SVG path data asset

**Files:**
- Create: `ui/src/assets/worldOutline.ts`

**Interfaces:**
- Consumes: nothing (self-contained data).
- Produces: `WORLD_OUTLINE_PATHS: string[]` — one SVG path `d` attribute string per landmass.

This is a static data asset, not a fetched/generated file — no live map tiles or third-party map service (Global Constraints). Coordinates were derived by hand from real coastline reference points using the exact projection formula in `worldProjection.ts` (`x = (lng+180)/360*1000`, `y = (90-lat)/180*500`), so the silhouettes are simplified but correctly positioned relative to where site dots will land. Precision is intentionally low — only the site dots need to be geographically accurate.

- [ ] **Step 1: Create `ui/src/assets/worldOutline.ts`**

```ts
/**
 * Simplified continent silhouettes for the world map background.
 * Coordinates are equirectangular-projected (see lib/worldProjection.ts)
 * from real coastline reference points into a 1000x500 viewBox —
 * intentionally low-fidelity; only WorldMapView's site dots need to be
 * geographically precise.
 */
export const WORLD_OUTLINE_PATHS: string[] = [
  // North America
  'M67,53 L311,56 L353,114 L294,139 L278,181 L256,192 L278,225 L194,186 L175,158 L153,117 L144,111 L125,89 Z',
  // South America
  'M286,225 L322,219 L403,264 L381,314 L344,347 L311,403 L300,342 L286,283 L278,250 Z',
  // Africa
  'M483,153 L528,147 L594,164 L642,219 L614,256 L550,344 L539,314 L536,275 L522,239 L453,208 Z',
  // Europe
  'M475,142 L486,89 L569,53 L583,69 L597,117 L564,144 L536,136 Z',
  // Asia
  'M597,142 L667,61 L972,67 L944,94 L889,150 L839,164 L794,222 L786,244 L714,228 L689,189 L672,175 L625,194 L597,161 Z',
  // Australia
  'M850,289 L867,283 L895,281 L925,325 L903,356 L883,347 L822,339 Z',
];
```

- [ ] **Step 2: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/assets/worldOutline.ts
git commit -m "feat: add simplified world outline SVG paths"
```

---

### Task 6: Frontend — sites localStorage cache module

**Files:**
- Create: `ui/src/lib/merakiSitesCache.ts`

**Interfaces:**
- Consumes: `MerakiSite` (Task 4).
- Produces: `SITES_SCHEMA_VERSION: number`, `MerakiSitesCacheSnapshot { version, sites: MerakiSite[], lastUpdated: string | null }`, `loadSitesCache(): MerakiSitesCacheSnapshot | null`, `saveSitesCache(snapshot: Omit<MerakiSitesCacheSnapshot, 'version'>): void`.

Deliberately a separate localStorage key from `merakiCache.ts` (`meraki-sites-cache`, not `meraki-topology-cache`): sites are fetched once on landing rather than per selected network, and giving them their own key avoids two independent hooks (`useMerakiSites` here, `useMerakiTopology` elsewhere) racing to read-modify-write the same blob.

- [ ] **Step 1: Create `ui/src/lib/merakiSitesCache.ts`**

```ts
/**
 * Persist the Meraki sites list (world map landing view) to localStorage,
 * independent of the per-network topology cache in merakiCache.ts — sites
 * have a different lifecycle (fetched once on landing) and a much lighter
 * payload, so keeping the cache separate avoids the two caches racing to
 * overwrite the same localStorage entry.
 */

import type { MerakiSite } from '../types/meraki';

const STORAGE_KEY = 'meraki-sites-cache';
export const SITES_SCHEMA_VERSION = 1;

export interface MerakiSitesCacheSnapshot {
  version: number;
  sites: MerakiSite[];
  lastUpdated: string | null;
}

export function loadSitesCache(): MerakiSitesCacheSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MerakiSitesCacheSnapshot;
    if (parsed.version !== SITES_SCHEMA_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveSitesCache(snapshot: Omit<MerakiSitesCacheSnapshot, 'version'>): void {
  try {
    const payload: MerakiSitesCacheSnapshot = { version: SITES_SCHEMA_VERSION, ...snapshot };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch (err) {
    console.warn('Failed to persist Meraki sites cache:', err);
  }
}
```

- [ ] **Step 2: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/lib/merakiSitesCache.ts
git commit -m "feat: add localStorage cache for world map sites"
```

---

### Task 7: Frontend — `useMerakiSites` hook

**Files:**
- Create: `ui/src/hooks/useMerakiSites.ts`

**Interfaces:**
- Consumes: `MerakiSite` (Task 4), `loadSitesCache`/`saveSitesCache` (Task 6), `GET /api/meraki/sites`, `GET /api/meraki/sites/cache/load`, `POST /api/meraki/sites/cache/save` (Task 3).
- Produces: `useMerakiSites(): { sites: MerakiSite[]; isLoading: boolean; error: string | null; hasFetched: boolean; lastUpdated: Date | null; loadCached: () => Promise<boolean>; refresh: () => Promise<void> }`.

Mirrors the resolution order already used by `useMerakiTopology`'s `loadSeedFile`/`refresh` (localStorage → server-side snapshot → live API), but as an independent hook with its own cache key, per Task 6.

- [ ] **Step 1: Create `ui/src/hooks/useMerakiSites.ts`**

```ts
import { useState, useCallback, useRef } from 'react';
import { MerakiSite } from '../types/meraki';
import { loadSitesCache, saveSitesCache } from '../lib/merakiSitesCache';

export interface UseMerakiSitesReturn {
  sites: MerakiSite[];
  isLoading: boolean;
  error: string | null;
  hasFetched: boolean;
  lastUpdated: Date | null;
  /**
   * Try localStorage (synchronous, already applied by the time this hook
   * returns), then the server-side seed snapshot. Returns true if either
   * produced data — callers should skip `refresh()` in that case.
   */
  loadCached: () => Promise<boolean>;
  /** Hit the live Meraki API and persist the result to both caches. */
  refresh: () => Promise<void>;
}

export function useMerakiSites(): UseMerakiSitesReturn {
  const bootCacheRef = useRef<ReturnType<typeof loadSitesCache> | undefined>(undefined);
  if (bootCacheRef.current === undefined) bootCacheRef.current = loadSitesCache();
  const bootCache = bootCacheRef.current;

  const [sites, setSites] = useState<MerakiSite[]>(bootCache?.sites ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(!!bootCache);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(
    bootCache?.lastUpdated ? new Date(bootCache.lastUpdated) : null,
  );

  const loadCached = useCallback(async (): Promise<boolean> => {
    if (bootCache) return true; // already hydrated synchronously above
    try {
      const resp = await fetch('/api/meraki/sites/cache/load', { cache: 'no-store' });
      if (!resp.ok) return false;
      const data = (await resp.json()) as { sites: MerakiSite[] };
      setSites(data.sites ?? []);
      setHasFetched(true);
      return true;
    } catch {
      return false;
    }
  }, [bootCache]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/meraki/sites');
      if (!resp.ok) throw new Error(`Failed to fetch sites: ${resp.status}`);
      const data = (await resp.json()) as { sites: MerakiSite[] };
      const nextSites = data.sites ?? [];
      const now = new Date();
      setSites(nextSites);
      setLastUpdated(now);
      saveSitesCache({ sites: nextSites, lastUpdated: now.toISOString() });
      fetch('/api/meraki/sites/cache/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sites: nextSites }),
      }).catch(() => {
        /* best-effort server snapshot — localStorage already has it */
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch sites');
    } finally {
      setIsLoading(false);
      setHasFetched(true);
    }
  }, []);

  return { sites, isLoading, error, hasFetched, lastUpdated, loadCached, refresh };
}
```

- [ ] **Step 2: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/hooks/useMerakiSites.ts
git commit -m "feat: add useMerakiSites hook"
```

---

### Task 8: Frontend — `WorldMapView` component

**Files:**
- Create: `ui/src/components/WorldMapView.tsx`

**Interfaces:**
- Consumes: `MerakiSite` (Task 4), `HEALTH_COLORS`/`HEALTH_LABELS` (Task 4), `WORLD_VIEWBOX`/`project`/`radiusForDeviceCount` (Task 4), `WORLD_OUTLINE_PATHS` (Task 5).
- Produces: `WorldMapView` component with props `{ sites: MerakiSite[]; isConfigured: boolean; isLoading: boolean; error: string | null; onSelectSite: (networkId: string, origin: { xPct: number; yPct: number }) => void }`. `origin` is the clicked site's position as a percentage of the map container (0–100), used by the caller (Task 9) as the CSS `transform-origin` for the zoom transition — passing percentages instead of screen pixels means the caller never needs `getBoundingClientRect()`.

No frontend test infrastructure exists (Global Constraints) — verified visually once wired into `App.tsx` in Task 11.

- [ ] **Step 1: Create `ui/src/components/WorldMapView.tsx`**

```tsx
import React, { useMemo, useState } from 'react';
import { MerakiSite } from '../types/meraki';
import { HEALTH_COLORS, HEALTH_LABELS } from '../lib/healthColors';
import { WORLD_VIEWBOX, project, radiusForDeviceCount } from '../lib/worldProjection';
import { WORLD_OUTLINE_PATHS } from '../assets/worldOutline';

interface WorldMapViewProps {
  sites: MerakiSite[];
  isConfigured: boolean;
  isLoading: boolean;
  error: string | null;
  onSelectSite: (networkId: string, origin: { xPct: number; yPct: number }) => void;
}

const LEGEND_BUCKETS: MerakiSite['health_bucket'][] = ['green', 'yellow', 'orange', 'red', 'unknown'];

const CENTER_ORIGIN = { xPct: 50, yPct: 50 };

function centeredMessage(text: string, color = 'var(--text-muted)') {
  return (
    <div className="flex items-center justify-center h-full">
      <div style={{ fontFamily: "'JetBrains Mono', monospace", color, textAlign: 'center' }}>
        <div style={{ fontSize: '14px' }}>{text}</div>
      </div>
    </div>
  );
}

export const WorldMapView: React.FC<WorldMapViewProps> = ({
  sites,
  isConfigured,
  isLoading,
  error,
  onSelectSite,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const mappedSites = useMemo(
    () => sites.filter((s) => s.mapped && s.lat !== null && s.lng !== null),
    [sites],
  );
  const unmappedSites = useMemo(() => sites.filter((s) => !s.mapped), [sites]);
  const maxDeviceCount = useMemo(
    () => sites.reduce((max, s) => Math.max(max, s.device_count), 1),
    [sites],
  );

  if (!isConfigured) {
    return centeredMessage('Meraki API key is not configured.');
  }
  if (isLoading && sites.length === 0) {
    return centeredMessage('LOADING SITES...');
  }
  if (error && sites.length === 0) {
    return centeredMessage(error, 'var(--accent-red)');
  }
  if (sites.length === 0) {
    return centeredMessage('No sites found.');
  }

  const hoveredSite = sites.find((s) => s.network_id === hoveredId) ?? null;
  const hoveredPoint = hoveredSite?.lat != null && hoveredSite?.lng != null
    ? project(hoveredSite.lat, hoveredSite.lng)
    : null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: 'var(--bg-primary)', overflow: 'hidden' }}>
      <svg
        viewBox={`0 0 ${WORLD_VIEWBOX.width} ${WORLD_VIEWBOX.height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', display: 'block' }}
      >
        {WORLD_OUTLINE_PATHS.map((d, i) => (
          <path key={i} d={d} fill="var(--bg-tertiary)" stroke="var(--border-subtle)" strokeWidth={1} />
        ))}

        {mappedSites.map((site) => {
          const { x, y } = project(site.lat as number, site.lng as number);
          const r = radiusForDeviceCount(site.device_count, maxDeviceCount);
          return (
            <circle
              key={site.network_id}
              cx={x}
              cy={y}
              r={r}
              fill={HEALTH_COLORS[site.health_bucket]}
              stroke={hoveredId === site.network_id ? 'var(--text-primary)' : 'none'}
              strokeWidth={2}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoveredId(site.network_id)}
              onMouseLeave={() => setHoveredId((id) => (id === site.network_id ? null : id))}
              onClick={() =>
                onSelectSite(site.network_id, {
                  xPct: (x / WORLD_VIEWBOX.width) * 100,
                  yPct: (y / WORLD_VIEWBOX.height) * 100,
                })
              }
            />
          );
        })}
      </svg>

      {hoveredSite && hoveredPoint && (
        <div
          style={{
            position: 'absolute',
            left: `${(hoveredPoint.x / WORLD_VIEWBOX.width) * 100}%`,
            top: `${(hoveredPoint.y / WORLD_VIEWBOX.height) * 100}%`,
            transform: 'translate(-50%, -140%)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '4px',
            padding: '5px 9px',
            fontSize: '11px',
            color: 'var(--text-primary)',
            fontFamily: "'JetBrains Mono', monospace",
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
            zIndex: 10,
          }}
        >
          {hoveredSite.name} — {hoveredSite.device_count} device{hoveredSite.device_count === 1 ? '' : 's'}
          {hoveredSite.unhealthy_pct ? `, ${Math.round(hoveredSite.unhealthy_pct * 100)}% alerting` : ''}
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          position: 'absolute', left: '14px', bottom: '12px',
          background: 'rgba(13,17,23,0.85)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', padding: '8px 12px', fontSize: '10px', color: 'var(--text-secondary)',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        <div style={{ marginBottom: '6px' }}>Size = device count</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>Health:</span>
          {LEGEND_BUCKETS.map((bucket) => (
            <span
              key={bucket}
              title={HEALTH_LABELS[bucket]}
              style={{ width: '10px', height: '10px', borderRadius: '50%', background: HEALTH_COLORS[bucket], display: 'inline-block' }}
            />
          ))}
        </div>
      </div>

      {/* Unmapped sites panel */}
      {unmappedSites.length > 0 && (
        <div
          style={{
            position: 'absolute', right: '14px', top: '14px', width: '160px',
            background: 'rgba(13,17,23,0.9)', border: '1px solid var(--border-subtle)',
            borderRadius: '6px', padding: '8px 12px', fontSize: '11px', color: 'var(--text-secondary)',
            fontFamily: "'JetBrains Mono', monospace", maxHeight: '200px', overflowY: 'auto',
          }}
        >
          <div style={{ color: 'var(--text-muted)', fontSize: '10px', marginBottom: '6px', letterSpacing: '0.05em' }}>
            UNMAPPED ({unmappedSites.length})
          </div>
          {unmappedSites.map((site) => (
            <div
              key={site.network_id}
              onClick={() => onSelectSite(site.network_id, CENTER_ORIGIN)}
              style={{ padding: '3px 0', cursor: 'pointer', color: 'var(--text-primary)' }}
            >
              <span style={{ color: HEALTH_COLORS[site.health_bucket] }}>●</span> {site.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default WorldMapView;
```

- [ ] **Step 2: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/WorldMapView.tsx
git commit -m "feat: add WorldMapView component"
```

---

### Task 9: Frontend — `TopBar` back-to-map button

**Files:**
- Modify: `ui/src/components/TopBar.tsx`

**Interfaces:**
- Consumes: nothing new.
- Produces: `TopBarProps` gains `merakiView: 'map' | 'site'` and `onBackToMap: () => void`. When `dataSource === 'meraki' && merakiView === 'site'`, a "◀ World Map" button renders next to the existing network-jump dropdown and calls `onBackToMap`.

No automated test — this is a small, purely presentational addition to an existing component with no test coverage today (see Global Constraints). Verified visually in Task 11.

- [ ] **Step 1: Add the two new props to `TopBarProps`**

In `ui/src/components/TopBar.tsx`, add to the `TopBarProps` interface (after `onSaveSnapshot: () => Promise<boolean>;`):

```ts
  merakiView: 'map' | 'site';
  onBackToMap: () => void;
```

- [ ] **Step 2: Destructure the new props**

Add `merakiView` and `onBackToMap` to the component's destructured props (after `onSaveSnapshot,`):

```ts
  merakiView,
  onBackToMap,
```

- [ ] **Step 3: Render the back button next to the network dropdown**

Replace:

```tsx
      {/* Network filter — Meraki only */}
      {dataSource === 'meraki' && (
        <NetworkFilter
          networks={merakiNetworks}
          value={selectedNetwork}
          onChange={onNetworkChange}
        />
      )}
```

with:

```tsx
      {/* Network filter — Meraki only */}
      {dataSource === 'meraki' && (
        <>
          {merakiView === 'site' && (
            <button
              onClick={onBackToMap}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                height: '32px',
                padding: '0 12px',
                background: 'var(--bg-tertiary)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '6px',
                cursor: 'pointer',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '12px',
                fontWeight: 600,
                color: 'var(--text-secondary)',
              }}
            >
              ◀ World Map
            </button>
          )}
          <NetworkFilter
            networks={merakiNetworks}
            value={selectedNetwork}
            onChange={onNetworkChange}
          />
        </>
      )}
```

- [ ] **Step 4: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: `TopBar.tsx` itself has no errors. (`App.tsx` will still error until Task 10 passes the two new props — that's expected at this point.)

- [ ] **Step 5: Commit**

```bash
git add ui/src/components/TopBar.tsx
git commit -m "feat: add back-to-world-map button to TopBar"
```

---

### Task 10: Frontend — `App.tsx` wiring

**Files:**
- Modify: `ui/src/App.tsx` (full replacement shown below — the diff touches the top-level state, the landing effect, and the main content JSX)

**Interfaces:**
- Consumes: `useMerakiSites` (Task 7), `WorldMapView` (Task 8), `TopBar` with `merakiView`/`onBackToMap` props (Task 9).
- Produces: default `dataSource` is now `'meraki'`; a `merakiView: 'map' | 'site'` state that gates whether `WorldMapView` or the existing per-site view renders.

- [ ] **Step 1: Replace `ui/src/App.tsx`**

```tsx
import { useState, useEffect } from 'react';
import { ReactFlowProvider } from '@xyflow/react';
import { useTopology } from './hooks/useTopology';
import { useSimulation } from './hooks/useSimulation';
import { useMerakiTopology } from './hooks/useMerakiTopology';
import { useMerakiSites } from './hooks/useMerakiSites';
import TopBar from './components/TopBar';
import TopologyCanvas from './components/TopologyCanvas';
import DetailPanel from './components/DetailPanel';
import MerakiDetailPanel from './components/MerakiDetailPanel';
import RefreshOverlay from './components/RefreshOverlay';
import L3View from './components/L3View';
import HybridView from './components/HybridView';
import WorldMapView from './components/WorldMapView';
import { ConfigBrowser } from './components/ConfigBrowser';
import type { DataSource } from './types/topology';

function App() {
  const [dataSource, setDataSource] = useState<DataSource>('meraki');
  const sim = useSimulation();
  const topo = useTopology();
  const meraki = useMerakiTopology();
  const merakiSites = useMerakiSites();

  // World-map landing state — 'map' is the default for Meraki; clicking a
  // site (or the network-jump dropdown) moves to 'site'.
  const [merakiView, setMerakiView] = useState<'map' | 'site'>('map');
  const [transitionOrigin, setTransitionOrigin] = useState<{ xPct: number; yPct: number }>({
    xPct: 50,
    yPct: 50,
  });
  const [isTransitioning, setIsTransitioning] = useState(false);

  // First-switch trigger for Meraki. The world map is the landing view, so
  // this now only needs the lightweight sites summary — not a specific
  // network's full L2/L3 topology. Resolution order for sites mirrors the
  // topology cache: localStorage (synchronous, inside useMerakiSites) →
  // server-side snapshot → live Meraki API. The network-jump dropdown
  // still needs `meraki.networks`, so that's fetched too, but without the
  // eager `refresh(networkId)` call the old effect used to make.
  const [merakiInitialized, setMerakiInitialized] = useState(false);
  useEffect(() => {
    if (dataSource !== 'meraki' || merakiInitialized) return;
    setMerakiInitialized(true);

    if (meraki.networks.length === 0) {
      meraki.fetchNetworks();
    }
    merakiSites.loadCached().then((hit) => {
      if (!hit) merakiSites.refresh();
    });
  }, [dataSource, merakiInitialized]);

  const handleSelectSite = (networkId: string, origin: { xPct: number; yPct: number }) => {
    setTransitionOrigin(origin);
    setIsTransitioning(true);
    meraki.setSelectedNetwork(networkId);
    window.setTimeout(() => {
      setMerakiView('site');
      setIsTransitioning(false);
    }, 400);
  };

  const handleBackToMap = () => {
    setIsTransitioning(true);
    window.setTimeout(() => {
      setMerakiView('map');
      setIsTransitioning(false);
    }, 300);
  };

  const isSimulated = dataSource === 'simulated';
  const showWorldMap = dataSource === 'meraki' && merakiView === 'map';
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

  const showSimStopped = isSimulated && !sim.isRunning;
  const showSimLoading = isSimulated && topo.isLoading && sim.isRunning;

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
        onSaveSnapshot={meraki.saveSnapshot}
        merakiView={merakiView}
        onBackToMap={handleBackToMap}
      />
      <div className="flex-1 relative overflow-hidden">
        {dataSource === 'configs' ? (
          <ConfigBrowser />
        ) : showWorldMap ? (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              transformOrigin: `${transitionOrigin.xPct}% ${transitionOrigin.yPct}%`,
              transform: isTransitioning ? 'scale(2.4)' : 'scale(1)',
              opacity: isTransitioning ? 0 : 1,
              transition: 'transform 0.4s ease, opacity 0.4s ease',
            }}
          >
            <WorldMapView
              sites={merakiSites.sites}
              isConfigured={meraki.isConfigured}
              isLoading={merakiSites.isLoading}
              error={merakiSites.error}
              onSelectSite={handleSelectSite}
            />
          </div>
        ) : (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              opacity: isTransitioning ? 0 : 1,
              transition: 'opacity 0.3s ease',
            }}
          >
            {showSimStopped ? (
              <div className="flex items-center justify-center h-full">
                <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)', textAlign: 'center' }}>
                  <div style={{ fontSize: '14px', marginBottom: '8px' }}>Simulation stopped.</div>
                  <div style={{ fontSize: '11px' }}>Click Start Simulation to begin.</div>
                </div>
              </div>
            ) : showSimLoading ? (
              <div className="flex items-center justify-center h-full">
                <div style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}>SCANNING NETWORK...</div>
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
                <HybridView l2Topology={l2} l3Topology={l3} onSelectDevice={setSelectedDevice} onSelectVlan={() => {}} gatewayLabel={isSimulated ? 'FortiGate' : 'Meraki Gateway'} />
              </ReactFlowProvider>
            ) : (
              <ReactFlowProvider>
                <L3View topology={l3} onSelectVlan={() => {}} gatewayLabel={isSimulated ? 'FortiGate' : 'Meraki Gateway'} />
              </ReactFlowProvider>
            )}
          </div>
        )}

        {!showWorldMap && !isSimulated && meraki.isRefreshing && (
          <RefreshOverlay
            phase={meraki.refreshPhase}
            progress={meraki.refreshProgress}
            total={meraki.refreshTotal}
            message={meraki.loadingMessage}
          />
        )}

        {!showWorldMap && (viewMode === 'l2' || viewMode === 'hybrid') && isSimulated && (
          <DetailPanel device={selectedDevice} topology={l2} onClose={() => setSelectedDevice(null)} />
        )}
        {!showWorldMap && (viewMode === 'l2' || viewMode === 'hybrid') && !isSimulated && (
          <MerakiDetailPanel
            device={selectedDevice}
            topology={l2}
            clientCounts={meraki.clientCounts}
            onClose={() => setSelectedDevice(null)}
            onGetDeviceDetail={meraki.getDeviceDetail}
          />
        )}
      </div>
    </div>
  );
}

export default App;
```

- [ ] **Step 2: Type-check**

Run: `cd ui && npx tsc --noEmit`
Expected: no errors (this will fail until Task 10 adds `merakiView`/`onBackToMap` to `TopBarProps` — that's why Task 10 must land first).

- [ ] **Step 3: Commit**

```bash
git add ui/src/App.tsx
git commit -m "feat: default to Meraki source and land on the world map"
```

---

### Task 11: Full regression check + manual end-to-end verification

**Files:** none (verification only).

- [ ] **Step 1: Run the full backend test suite**

Run: `python3 -m pytest`
Expected: all tests pass, including the 9 + 3 new tests from Tasks 1–2.

- [ ] **Step 2: Type-check and build the frontend**

Run: `cd ui && npm run build`
Expected: TypeScript compiles cleanly and Vite produces a production build with no errors.

- [ ] **Step 3: Start the dev server**

Run: `cd ui && npm run dev`, open the printed URL in a browser (also start the backend — `docker compose up --build`, or run the FastAPI app directly — since the UI proxies `/api/*` to it).

- [ ] **Step 4: Verify the landing experience**

- Reload the app fresh. Confirm the source selector shows **Meraki Live** selected by default (not Configs).
- Confirm the main panel shows the world map view, not an auto-selected network's topology.
- If `MERAKI_API_KEY` is not set in this environment: confirm the map area shows "Meraki API key is not configured." — not a blank screen, not a crash.
- If a real `MERAKI_API_KEY` is available: confirm sites render as circles positioned roughly at their real-world locations, sized by device count, colored per the health legend; hover a circle and confirm the tooltip shows name/device count/alerting %; confirm any networks without a configured address appear in the "Unmapped" panel instead of on the map.

- [ ] **Step 5: Verify the click-through and back navigation**

(Requires at least one real or mapped site — skip with a note if no Meraki data is available in this environment.)

- Click a site circle. Confirm a zoom/fade transition plays and the existing per-site topology view (same L2 view as before this change) renders for that site.
- Confirm a "◀ World Map" button now appears in the TopBar next to the network dropdown.
- Click it. Confirm the reverse transition plays and the world map reappears.
- Use the network-jump dropdown directly (bypassing the map) and confirm it still jumps straight to a site's topology, unchanged from before this feature.

- [ ] **Step 6: Verify other sources are unaffected**

- Switch to **Simulated** — confirm it behaves exactly as before (start/stop simulation, topology rendering).
- Switch to **Configs** — confirm `ConfigBrowser` renders exactly as before.

- [ ] **Step 7: Check the browser console**

Confirm no new errors or warnings were introduced during any of the steps above.

No commit for this task — it's verification-only. If any step surfaces a bug, fix it in the relevant earlier task's files and re-run that task's tests before continuing.
