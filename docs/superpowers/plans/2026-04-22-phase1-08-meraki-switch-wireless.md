# Plan 1.08 — Meraki Client: MS + MR + Per-SSID Endpoints

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Add ~29 methods to `MerakiClient`: 16 MS switch, 5 MR wireless, 8 per-SSID sub-endpoints.

**Depends on:** Plan 1.05.
**Unblocks:** Plan 1.13 (baseline runner).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/meraki_client.py` | Modify | Add ~29 new methods |
| `server/tests/test_meraki_switch_wireless.py` | Create | respx-mocked tests |

---

## Task 1: MS switch methods (16)

- [ ] **Step 1.1: Write failing tests**

Create `server/tests/test_meraki_switch_wireless.py`:

```python
"""Tests for MS switch + MR wireless Meraki client methods (Plan 1.08)."""
from __future__ import annotations

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


@pytest.mark.parametrize("method,path,body", [
    ("get_switch_access_policies",   "/networks/N_1/switch/accessPolicies",                     []),
    ("get_switch_acls",              "/networks/N_1/switch/accessControlLists",                 {"rules": []}),
    ("get_switch_qos_rules",         "/networks/N_1/switch/qosRules",                           []),
    ("get_switch_qos_order",         "/networks/N_1/switch/qosRules/order",                     {"ruleIds": []}),
    ("get_switch_dscp_to_cos",       "/networks/N_1/switch/dscpToCosMappings",                  {"mappings": []}),
    ("get_switch_settings",          "/networks/N_1/switch/settings",                           {"vlan": 1}),
    ("get_switch_stp",               "/networks/N_1/switch/stp",                                {"rstpEnabled": True}),
    ("get_switch_storm_control",     "/networks/N_1/switch/stormControl",                       {"broadcastThreshold": 100}),
    ("get_switch_mtu",               "/networks/N_1/switch/mtu",                                {"defaultMtuSize": 9578}),
    ("get_switch_stacks",            "/networks/N_1/switch/stacks",                             []),
    ("get_switch_port_schedules",    "/networks/N_1/switch/portSchedules",                      []),
    ("get_switch_link_aggregations", "/networks/N_1/switch/linkAggregations",                   []),
    ("get_switch_dhcp_server_policy","/networks/N_1/switch/dhcpServerPolicy",                   {"defaultPolicy": "allow"}),
    ("get_switch_multicast",         "/networks/N_1/switch/routing/multicast",                  {"defaultSettings": {}}),
    ("get_switch_multicast_rps",     "/networks/N_1/switch/routing/multicast/rendezvousPoints", []),
    ("get_switch_ospf",              "/networks/N_1/switch/routing/ospf",                       {"enabled": False}),
])
@pytest.mark.asyncio
async def test_switch_methods(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        assert await getattr(client, method)("N_1") == body
```

- [ ] **Step 1.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_switch_wireless.py -v`

Expected: AttributeError.

- [ ] **Step 1.3: Add the 16 MS methods to `MerakiClient`**

```python
    # --- Plan 1.08: MS switch ---------------------------------------------

    async def get_switch_access_policies(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/accessPolicies")

    async def get_switch_acls(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/accessControlLists")

    async def get_switch_qos_rules(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/qosRules")

    async def get_switch_qos_order(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/qosRules/order")

    async def get_switch_dscp_to_cos(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/dscpToCosMappings")

    async def get_switch_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/settings")

    async def get_switch_stp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/stp")

    async def get_switch_storm_control(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/stormControl")

    async def get_switch_mtu(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/mtu")

    async def get_switch_stacks(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/stacks")

    async def get_switch_port_schedules(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/portSchedules")

    async def get_switch_link_aggregations(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/linkAggregations")

    async def get_switch_dhcp_server_policy(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/dhcpServerPolicy")

    async def get_switch_multicast(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/routing/multicast")

    async def get_switch_multicast_rps(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/switch/routing/multicast/rendezvousPoints")

    async def get_switch_ospf(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/switch/routing/ospf")
```

- [ ] **Step 1.4: Run — should pass**

Expected: 16 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_switch_wireless.py
git commit -m "feat(meraki): 16 MS switch endpoint methods (Plan 1.08)"
```

---

## Task 2: MR wireless network-level methods (5)

- [ ] **Step 2.1: Write failing tests**

Append to `server/tests/test_meraki_switch_wireless.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_wireless_ssids",            "/networks/N_1/wireless/ssids",                    []),
    ("get_wireless_rf_profiles",      "/networks/N_1/wireless/rfProfiles",               []),
    ("get_wireless_settings",         "/networks/N_1/wireless/settings",                 {"meshingEnabled": True}),
    ("get_wireless_bluetooth",        "/networks/N_1/wireless/bluetooth/settings",       {"scanningEnabled": False}),
    ("get_wireless_ap_port_profiles", "/networks/N_1/wireless/ethernet/ports/profiles",  []),
])
@pytest.mark.asyncio
async def test_wireless_network_methods(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        assert await getattr(client, method)("N_1") == body
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Add the 5 MR methods**

Append to `MerakiClient`:

```python
    # --- Plan 1.08: MR wireless (network-level) --------------------------

    async def get_wireless_ssids(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/ssids")

    async def get_wireless_rf_profiles(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/rfProfiles")

    async def get_wireless_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/settings")

    async def get_wireless_bluetooth(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/bluetooth/settings")

    async def get_wireless_ap_port_profiles(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/ethernet/ports/profiles")
```

- [ ] **Step 2.4: Run — should pass**

Expected: 21 total tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_switch_wireless.py
git commit -m "feat(meraki): 5 MR wireless network-level methods (Plan 1.08)"
```

---

## Task 3: Per-SSID sub-endpoint methods (8)

Per-SSID methods take `(network_id, ssid_number)`.

- [ ] **Step 3.1: Write failing tests**

Append to `server/tests/test_meraki_switch_wireless.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_wireless_ssid_l3_firewall",             "/networks/N_1/wireless/ssids/3/firewall/l3FirewallRules",    {"rules": []}),
    ("get_wireless_ssid_l7_firewall",             "/networks/N_1/wireless/ssids/3/firewall/l7FirewallRules",    {"rules": []}),
    ("get_wireless_ssid_traffic_shaping",         "/networks/N_1/wireless/ssids/3/trafficShaping/rules",        {"rules": []}),
    ("get_wireless_ssid_splash",                  "/networks/N_1/wireless/ssids/3/splash/settings",             {"splashPage": "None"}),
    ("get_wireless_ssid_schedules",               "/networks/N_1/wireless/ssids/3/schedules",                   {"enabled": False}),
    ("get_wireless_ssid_vpn",                     "/networks/N_1/wireless/ssids/3/vpn",                         {"concentrator": None}),
    ("get_wireless_ssid_device_type_policies",    "/networks/N_1/wireless/ssids/3/deviceTypeGroupPolicies",     {"enabled": False}),
    ("get_wireless_ssid_identity_psks",           "/networks/N_1/wireless/ssids/3/identityPsks",                []),
])
@pytest.mark.asyncio
async def test_per_ssid_methods(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        assert await getattr(client, method)("N_1", 3) == body
```

- [ ] **Step 3.2: Run — should fail**

- [ ] **Step 3.3: Add the 8 per-SSID methods**

Append to `MerakiClient`:

```python
    # --- Plan 1.08: Per-SSID sub-endpoints --------------------------------

    async def get_wireless_ssid_l3_firewall(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/firewall/l3FirewallRules")

    async def get_wireless_ssid_l7_firewall(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/firewall/l7FirewallRules")

    async def get_wireless_ssid_traffic_shaping(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/trafficShaping/rules")

    async def get_wireless_ssid_splash(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/splash/settings")

    async def get_wireless_ssid_schedules(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/schedules")

    async def get_wireless_ssid_vpn(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/vpn")

    async def get_wireless_ssid_device_type_policies(self, network_id: str, ssid_number: int) -> dict:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/deviceTypeGroupPolicies")

    async def get_wireless_ssid_identity_psks(self, network_id: str, ssid_number: int) -> list[dict]:
        return await self._get(f"/networks/{network_id}/wireless/ssids/{ssid_number}/identityPsks")
```

- [ ] **Step 3.4: Run — should pass**

Expected: 29 total tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_switch_wireless.py
git commit -m "feat(meraki): 8 per-SSID sub-endpoint methods (Plan 1.08)"
```

---

## Completion Checklist

- [ ] 29 new methods total (16 MS + 5 MR network + 8 per-SSID)
- [ ] 29 passing tests
- [ ] 3 commits
