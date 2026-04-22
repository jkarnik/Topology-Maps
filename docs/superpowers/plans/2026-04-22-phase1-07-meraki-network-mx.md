# Plan 1.07 — Meraki Client: Network-Generic + MX Endpoints

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Add ~38 methods to `MerakiClient`: 12 network-generic + 26 MX-specific. All use `_get` (no pagination). Methods follow `get_network_<area>(network_id)` naming.

**Depends on:** Plan 1.05.
**Unblocks:** Plan 1.13 (baseline runner).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/meraki_client.py` | Modify | Add ~38 `get_network_*` methods |
| `server/tests/test_meraki_network_mx.py` | Create | respx-mocked tests |

---

## Task 1: Network-generic methods (12)

- [ ] **Step 1.1: Write failing tests**

Create `server/tests/test_meraki_network_mx.py`:

```python
"""Tests for network-generic + MX Meraki client methods (Plan 1.07)."""
from __future__ import annotations

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


@pytest.mark.parametrize("method,path,body", [
    ("get_network_metadata",             "/networks/N_1",                            {"id": "N_1", "name": "Store 1"}),
    ("get_network_settings",             "/networks/N_1/settings",                   {"localStatusPageEnabled": True}),
    ("get_network_group_policies",       "/networks/N_1/groupPolicies",              []),
    ("get_network_syslog_servers",       "/networks/N_1/syslogServers",              {"servers": []}),
    ("get_network_snmp",                 "/networks/N_1/snmp",                       {"access": "none"}),
    ("get_network_traffic_analysis",     "/networks/N_1/trafficAnalysis",            {"mode": "disabled"}),
    ("get_network_netflow",              "/networks/N_1/netflow",                    {"reportingEnabled": False}),
    ("get_network_alerts_settings",      "/networks/N_1/alerts/settings",            {"defaultDestinations": {}}),
    ("get_network_webhooks_http_servers","/networks/N_1/webhooks/httpServers",       []),
    ("get_network_webhooks_payload_templates","/networks/N_1/webhooks/payloadTemplates",[]),
    ("get_network_firmware_upgrades",    "/networks/N_1/firmwareUpgrades",           {"upgradeWindow": {}}),
    ("get_network_floor_plans",          "/networks/N_1/floorPlans",                 []),
])
@pytest.mark.asyncio
async def test_network_generic_methods(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        result = await getattr(client, method)("N_1")
    assert result == body
```

- [ ] **Step 1.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_network_mx.py -v`

Expected: AttributeError.

- [ ] **Step 1.3: Add the 12 methods to `MerakiClient`**

```python
    # --- Plan 1.07: Network-generic endpoints ----------------------------

    async def get_network_metadata(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}")

    async def get_network_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/settings")

    async def get_network_group_policies(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/groupPolicies")

    async def get_network_syslog_servers(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/syslogServers")

    async def get_network_snmp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/snmp")

    async def get_network_traffic_analysis(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/trafficAnalysis")

    async def get_network_netflow(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/netflow")

    async def get_network_alerts_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/alerts/settings")

    async def get_network_webhooks_http_servers(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/webhooks/httpServers")

    async def get_network_webhooks_payload_templates(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/webhooks/payloadTemplates")

    async def get_network_firmware_upgrades(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/firmwareUpgrades")

    async def get_network_floor_plans(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/floorPlans")
```

- [ ] **Step 1.4: Run — should pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_network_mx.py -v`

Expected: 12 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_network_mx.py
git commit -m "feat(meraki): 12 network-generic endpoint methods (Plan 1.07)"
```

---

## Task 2: MX VLAN + ports + firewall methods (13)

- [ ] **Step 2.1: Write failing tests**

Append to `server/tests/test_meraki_network_mx.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_appliance_vlans",                   "/networks/N_1/appliance/vlans",                           []),
    ("get_appliance_vlans_settings",          "/networks/N_1/appliance/vlans/settings",                  {"vlansEnabled": True}),
    ("get_appliance_single_lan",              "/networks/N_1/appliance/singleLan",                       {"subnet": "192.168.1.0/24"}),
    ("get_appliance_ports",                   "/networks/N_1/appliance/ports",                           []),
    ("get_appliance_firewall_l3",             "/networks/N_1/appliance/firewall/l3FirewallRules",        {"rules": []}),
    ("get_appliance_firewall_l7",             "/networks/N_1/appliance/firewall/l7FirewallRules",        {"rules": []}),
    ("get_appliance_firewall_inbound",        "/networks/N_1/appliance/firewall/inboundFirewallRules",   {"rules": []}),
    ("get_appliance_firewall_port_forwarding","/networks/N_1/appliance/firewall/portForwardingRules",    {"rules": []}),
    ("get_appliance_firewall_one_to_one_nat", "/networks/N_1/appliance/firewall/oneToOneNatRules",       {"rules": []}),
    ("get_appliance_firewall_one_to_many_nat","/networks/N_1/appliance/firewall/oneToManyNatRules",      {"rules": []}),
    ("get_appliance_firewall_firewalled_services","/networks/N_1/appliance/firewall/firewalledServices", []),
    ("get_appliance_firewall_settings",       "/networks/N_1/appliance/firewall/settings",               {"spoofingProtection": {}}),
    ("get_appliance_firewall_cellular",       "/networks/N_1/appliance/firewall/cellularFirewallRules",  {"rules": []}),
])
@pytest.mark.asyncio
async def test_mx_vlan_port_firewall(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        result = await getattr(client, method)("N_1")
    assert result == body
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Add the 13 MX methods**

Append to `MerakiClient`:

```python
    # --- Plan 1.07: MX appliance (VLAN / ports / firewall) -----------------

    async def get_appliance_vlans(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/vlans")

    async def get_appliance_vlans_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/vlans/settings")

    async def get_appliance_single_lan(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/singleLan")

    async def get_appliance_ports(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/ports")

    async def get_appliance_firewall_l3(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/l3FirewallRules")

    async def get_appliance_firewall_l7(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/l7FirewallRules")

    async def get_appliance_firewall_inbound(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/inboundFirewallRules")

    async def get_appliance_firewall_port_forwarding(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/portForwardingRules")

    async def get_appliance_firewall_one_to_one_nat(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/oneToOneNatRules")

    async def get_appliance_firewall_one_to_many_nat(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/oneToManyNatRules")

    async def get_appliance_firewall_firewalled_services(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/firewall/firewalledServices")

    async def get_appliance_firewall_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/settings")

    async def get_appliance_firewall_cellular(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/firewall/cellularFirewallRules")
```

- [ ] **Step 2.4: Run — should pass**

Expected: 25 total tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_network_mx.py
git commit -m "feat(meraki): 13 MX VLAN/port/firewall methods (Plan 1.07)"
```

---

## Task 3: MX security + shaping + VPN + routing (13)

- [ ] **Step 3.1: Write failing tests**

Append to `server/tests/test_meraki_network_mx.py`:

```python
@pytest.mark.parametrize("method,path,body", [
    ("get_appliance_content_filtering",       "/networks/N_1/appliance/contentFiltering",                  {"blockedUrlCategories": []}),
    ("get_appliance_security_intrusion",      "/networks/N_1/appliance/security/intrusion",                {"mode": "disabled"}),
    ("get_appliance_security_malware",        "/networks/N_1/appliance/security/malware",                  {"mode": "disabled"}),
    ("get_appliance_traffic_shaping_rules",   "/networks/N_1/appliance/trafficShaping/rules",              {"rules": []}),
    ("get_appliance_uplink_bandwidth",        "/networks/N_1/appliance/trafficShaping/uplinkBandwidth",    {"bandwidthLimits": {}}),
    ("get_appliance_uplink_selection",        "/networks/N_1/appliance/trafficShaping/uplinkSelection",    {"activeActiveAutoVpnEnabled": False}),
    ("get_appliance_custom_performance_classes","/networks/N_1/appliance/trafficShaping/customPerformanceClasses", []),
    ("get_appliance_site_to_site_vpn",        "/networks/N_1/appliance/vpn/siteToSiteVpn",                 {"mode": "none"}),
    ("get_appliance_vpn_bgp",                 "/networks/N_1/appliance/vpn/bgp",                           {"enabled": False}),
    ("get_appliance_static_routes",           "/networks/N_1/appliance/staticRoutes",                      []),
    ("get_appliance_warm_spare",              "/networks/N_1/appliance/warmSpare",                         {"enabled": False}),
    ("get_appliance_connectivity_monitoring", "/networks/N_1/appliance/connectivityMonitoringDestinations", {"destinations": []}),
    ("get_appliance_settings",                "/networks/N_1/appliance/settings",                           {"clientTrackingMethod": "MAC address"}),
])
@pytest.mark.asyncio
async def test_mx_security_shaping_vpn(client, method, path, body):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get(path).mock(return_value=httpx.Response(200, json=body))
        result = await getattr(client, method)("N_1")
    assert result == body
```

- [ ] **Step 3.2: Run — should fail**

- [ ] **Step 3.3: Add the 13 MX methods**

Append to `MerakiClient`:

```python
    # --- Plan 1.07: MX security / shaping / VPN / routing ------------------

    async def get_appliance_content_filtering(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/contentFiltering")

    async def get_appliance_security_intrusion(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/security/intrusion")

    async def get_appliance_security_malware(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/security/malware")

    async def get_appliance_traffic_shaping_rules(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/rules")

    async def get_appliance_uplink_bandwidth(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/uplinkBandwidth")

    async def get_appliance_uplink_selection(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/uplinkSelection")

    async def get_appliance_custom_performance_classes(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/trafficShaping/customPerformanceClasses")

    async def get_appliance_site_to_site_vpn(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/vpn/siteToSiteVpn")

    async def get_appliance_vpn_bgp(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/vpn/bgp")

    async def get_appliance_static_routes(self, network_id: str) -> list[dict]:
        return await self._get(f"/networks/{network_id}/appliance/staticRoutes")

    async def get_appliance_warm_spare(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/warmSpare")

    async def get_appliance_connectivity_monitoring(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/connectivityMonitoringDestinations")

    async def get_appliance_settings(self, network_id: str) -> dict:
        return await self._get(f"/networks/{network_id}/appliance/settings")
```

- [ ] **Step 3.4: Run — should pass**

Expected: 38 total tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_network_mx.py
git commit -m "feat(meraki): 13 MX security/shaping/VPN/routing methods (Plan 1.07)"
```

---

## Completion Checklist

- [ ] 38 `get_network_*` and `get_appliance_*` methods exist
- [ ] 38 passing tests
- [ ] 3 commits
