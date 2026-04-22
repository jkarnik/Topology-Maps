# Plan 1.09 — Meraki Client: Device + MV/MG/SM Endpoints

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Add ~19 methods to `MerakiClient`: 12 device-level + 7 MV/MG/SM. All use `_get`. Device methods take `serial`; MV/MG/SM methods take `network_id`.

**Depends on:** Plan 1.05.
**Unblocks:** Plan 1.13 (baseline runner).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/meraki_client.py` | Modify | Add ~19 new methods |
| `server/tests/test_meraki_device_misc.py` | Create | respx-mocked tests |

---

## Task 1: Device metadata + management interface (2)

- [ ] **Step 1.1: Write failing tests**

Create `server/tests/test_meraki_device_misc.py`:

```python
"""Tests for device-level + MV/MG/SM Meraki client methods (Plan 1.09)."""
from __future__ import annotations

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


@pytest.mark.asyncio
async def test_get_device_metadata(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/devices/Q2AB-CDEF-GHIJ").mock(
            return_value=httpx.Response(200, json={"serial": "Q2AB-CDEF-GHIJ", "name": "MS1"})
        )
        result = await client.get_device_metadata("Q2AB-CDEF-GHIJ")
    assert result["name"] == "MS1"


@pytest.mark.asyncio
async def test_get_device_management_interface(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/devices/Q2AB-CDEF-GHIJ/managementInterface").mock(
            return_value=httpx.Response(200, json={"wan1": {"usingStaticIp": False}})
        )
        assert "wan1" in await client.get_device_management_interface("Q2AB-CDEF-GHIJ")
```

- [ ] **Step 1.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_device_misc.py -v`

- [ ] **Step 1.3: Add the 2 methods**

```python
    # --- Plan 1.09: Device metadata + mgmt interface ----------------------

    async def get_device_metadata(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}")

    async def get_device_management_interface(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/managementInterface")
```

- [ ] **Step 1.4: Run — should pass**

Expected: 2 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_device_misc.py
git commit -m "feat(meraki): device metadata + mgmt interface methods (Plan 1.09)"
```

---

## Task 2: MS/MR/MX device-specific methods (7)

- [ ] **Step 2.1: Write failing tests**

Append to `server/tests/test_meraki_device_misc.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_switch_device_ports",                 "/devices/SW-001/switch/ports",                      []),
    ("get_switch_device_routing_interfaces",    "/devices/SW-001/switch/routing/interfaces",         []),
    ("get_switch_device_routing_static_routes", "/devices/SW-001/switch/routing/staticRoutes",       []),
    ("get_switch_device_warm_spare",            "/devices/SW-001/switch/warmSpare",                  {"enabled": False}),
    ("get_wireless_device_radio_settings",      "/devices/AP-001/wireless/radio/settings",           {"rfProfileId": None}),
    ("get_wireless_device_bluetooth",           "/devices/AP-001/wireless/bluetooth/settings",       {"uuid": ""}),
    ("get_appliance_device_uplinks",            "/devices/MX-001/appliance/uplinks/settings",        {"interfaces": {}}),
])
@pytest.mark.asyncio
async def test_device_specific_methods(client, method, path, body):
    serial = path.split("/")[2]
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        assert await getattr(client, method)(serial) == body
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Add the 7 methods**

```python
    # --- Plan 1.09: Device-level per-product methods ---------------------

    async def get_switch_device_ports(self, serial: str) -> list[dict]:
        return await self._get(f"/devices/{serial}/switch/ports")

    async def get_switch_device_routing_interfaces(self, serial: str) -> list[dict]:
        return await self._get(f"/devices/{serial}/switch/routing/interfaces")

    async def get_switch_device_routing_static_routes(self, serial: str) -> list[dict]:
        return await self._get(f"/devices/{serial}/switch/routing/staticRoutes")

    async def get_switch_device_warm_spare(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/switch/warmSpare")

    async def get_wireless_device_radio_settings(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/wireless/radio/settings")

    async def get_wireless_device_bluetooth(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/wireless/bluetooth/settings")

    async def get_appliance_device_uplinks(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/appliance/uplinks/settings")
```

- [ ] **Step 2.4: Run — should pass**

Expected: 9 total tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_device_misc.py
git commit -m "feat(meraki): 7 device-level per-product methods (Plan 1.09)"
```

---

## Task 3: MV (camera) device methods (3)

- [ ] **Step 3.1: Write failing tests**

Append to `server/tests/test_meraki_device_misc.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_camera_device_quality_retention", "/devices/MV-001/camera/qualityAndRetention",  {"motionBasedRetentionEnabled": False}),
    ("get_camera_device_video_settings",    "/devices/MV-001/camera/videoSettings",        {"externalRtspEnabled": False}),
    ("get_camera_device_sense",             "/devices/MV-001/camera/sense",                {"senseEnabled": False}),
])
@pytest.mark.asyncio
async def test_camera_methods(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        assert await getattr(client, method)("MV-001") == body
```

- [ ] **Step 3.2: Run — should fail**

- [ ] **Step 3.3: Add the 3 methods**

```python
    # --- Plan 1.09: MV camera device methods -----------------------------

    async def get_camera_device_quality_retention(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/camera/qualityAndRetention")

    async def get_camera_device_video_settings(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/camera/videoSettings")

    async def get_camera_device_sense(self, serial: str) -> dict:
        return await self._get(f"/devices/{serial}/camera/sense")
```

- [ ] **Step 3.4: Run — should pass**

Expected: 12 total tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_device_misc.py
git commit -m "feat(meraki): 3 MV camera device methods (Plan 1.09)"
```

---

## Task 4: Network-level MV / MG / SM methods (7)

- [ ] **Step 4.1: Write failing tests**

Append to `server/tests/test_meraki_device_misc.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_camera_quality_retention_profiles", "/networks/N_1/camera/qualityRetentionProfiles",               []),
    ("get_camera_schedules",                  "/networks/N_1/camera/schedules",                              []),
    ("get_cellular_dhcp",                     "/networks/N_1/cellularGateway/dhcp",                          {"dhcpLeaseTime": "1 day"}),
    ("get_cellular_subnet_pool",              "/networks/N_1/cellularGateway/subnetPool",                    {"subnets": []}),
    ("get_cellular_uplink",                   "/networks/N_1/cellularGateway/uplink",                        {"bandwidthLimits": {}}),
    ("get_cellular_connectivity_monitoring",  "/networks/N_1/cellularGateway/connectivityMonitoringDestinations", {"destinations": []}),
    ("get_sm_profiles",                       "/networks/N_1/sm/profiles",                                   []),
])
@pytest.mark.asyncio
async def test_mv_mg_sm_network_methods(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        assert await getattr(client, method)("N_1") == body
```

- [ ] **Step 4.2: Run — should fail**

- [ ] **Step 4.3: Add the 7 methods**

```python
    # --- Plan 1.09: MV/MG/SM network-level methods ------------------------

    async def get_camera_quality_retention_profiles(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/camera/qualityRetentionProfiles")

    async def get_camera_schedules(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/camera/schedules")

    async def get_cellular_dhcp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/cellularGateway/dhcp")

    async def get_cellular_subnet_pool(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/cellularGateway/subnetPool")

    async def get_cellular_uplink(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/cellularGateway/uplink")

    async def get_cellular_connectivity_monitoring(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/cellularGateway/connectivityMonitoringDestinations")

    async def get_sm_profiles(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/sm/profiles")
```

- [ ] **Step 4.4: Run — should pass**

Expected: 19 total tests pass.

- [ ] **Step 4.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_device_misc.py
git commit -m "feat(meraki): MV/MG/SM network-level methods (Plan 1.09)"
```

---

## Task 5: `configurationChanges` method

This is the critical endpoint for the change-log poller.

- [ ] **Step 5.1: Write failing test**

Append to `server/tests/test_meraki_device_misc.py`:

```python
@pytest.mark.asyncio
async def test_get_org_configuration_changes(client):
    """Change-log endpoint is paginated; timespan + perPage passed through."""
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/configurationChanges").mock(
            return_value=httpx.Response(200, json=[
                {"ts": "2026-04-22T10:00:00Z", "label": "VLAN", "networkId": "N_1"},
            ])
        )
        result = await client.get_org_configuration_changes("123", timespan=3600, per_page=1000)
    assert len(result) == 1
    assert result[0]["label"] == "VLAN"
```

- [ ] **Step 5.2: Run — should fail**

- [ ] **Step 5.3: Add the method**

```python
    async def get_org_configuration_changes(
        self, org_id: str, *, timespan: int = 3600, per_page: int = 1000,
    ) -> list[dict]:
        """Fetch the organization's configuration change log.

        `timespan` is in seconds (Meraki supports up to 2678400 = 31 days).
        The endpoint is paginated; Link headers are followed until exhausted.
        """
        return await self._get_paginated(
            f"/organizations/{org_id}/configurationChanges",
            params={"timespan": timespan},
            per_page=per_page,
        )
```

- [ ] **Step 5.4: Run — should pass**

Expected: 20 total tests pass.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_device_misc.py
git commit -m "feat(meraki): get_org_configuration_changes for change-log poller (Plan 1.09)"
```

---

## Completion Checklist

- [ ] 19 device/misc methods + 1 configurationChanges method = 20 new methods
- [ ] 20 passing tests
- [ ] All Tier-1+2 endpoints from `ENDPOINTS` catalog (Plan 1.04) now have a corresponding client method
- [ ] 5 commits
