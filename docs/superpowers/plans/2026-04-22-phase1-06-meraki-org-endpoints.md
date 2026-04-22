# Plan 1.06 — Meraki Client: Organization-Level Endpoints

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Add 18 organization-level getter methods to `MerakiClient`, one per `ORG_ENDPOINTS` entry from Plan 1.04. Each method delegates to `_get` or `_get_paginated` based on the spec's `paginated` flag and returns the parsed JSON body.

**Architecture:** Methods follow a uniform naming convention: `get_org_<area>(org_id) -> list | dict`. The 18 endpoints are chunked into 3 groups (admins/access, policy/templates/adaptive, inventory/licensing) so each group ships as one task with one commit.

**Depends on:** Plan 1.05 (pagination helper).
**Unblocks:** Plan 1.13 (baseline runner uses these methods via the catalog).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/meraki_client.py` | Modify | Add 18 `get_org_*` methods |
| `server/tests/test_meraki_org_endpoints.py` | Create | respx-mocked unit tests per method |

---

## Task 1: Admin / access / policy methods (6 methods)

- [ ] **Step 1.1: Write the failing test**

Create `server/tests/test_meraki_org_endpoints.py`:

```python
"""Tests for org-level Meraki client methods (Plan 1.06)."""
from __future__ import annotations

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


@pytest.mark.asyncio
async def test_get_org_admins(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/admins").mock(
            return_value=httpx.Response(200, json=[{"id": "a1", "name": "Alice"}])
        )
        assert await client.get_org_admins("123") == [{"id": "a1", "name": "Alice"}]


@pytest.mark.asyncio
async def test_get_org_saml_roles(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/samlRoles").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_saml_roles("123") == []


@pytest.mark.asyncio
async def test_get_org_saml(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/saml").mock(return_value=httpx.Response(200, json={"enabled": False}))
        assert await client.get_org_saml("123") == {"enabled": False}


@pytest.mark.asyncio
async def test_get_org_login_security(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/loginSecurity").mock(return_value=httpx.Response(200, json={"enforcePasswordExpiration": True}))
        result = await client.get_org_login_security("123")
    assert result["enforcePasswordExpiration"] is True


@pytest.mark.asyncio
async def test_get_org_policy_objects_paginated(client):
    """policyObjects is paginated — client should follow Link headers."""
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/policyObjects").mock(
            return_value=httpx.Response(200, json=[{"id": "p1"}])
        )
        result = await client.get_org_policy_objects("123")
    assert result == [{"id": "p1"}]


@pytest.mark.asyncio
async def test_get_org_policy_object_groups_paginated(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/policyObjects/groups").mock(
            return_value=httpx.Response(200, json=[])
        )
        assert await client.get_org_policy_object_groups("123") == []
```

- [ ] **Step 1.2: Run to verify failure**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_org_endpoints.py -v`

Expected: `AttributeError: 'MerakiClient' object has no attribute 'get_org_admins'`.

- [ ] **Step 1.3: Add the 6 methods**

In `server/meraki_client.py`, append to the `MerakiClient` class (before `async def close`):

```python
    # --- Plan 1.06: Organization-level endpoints (access/policy) -----------

    async def get_org_admins(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/admins")

    async def get_org_saml_roles(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/samlRoles")

    async def get_org_saml(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/saml")

    async def get_org_login_security(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/loginSecurity")

    async def get_org_policy_objects(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/policyObjects")

    async def get_org_policy_object_groups(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/policyObjects/groups")
```

- [ ] **Step 1.4: Run — should pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_org_endpoints.py -v`

Expected: 6 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_org_endpoints.py
git commit -m "feat(meraki): get_org_admins/saml/policy methods (Plan 1.06)"
```

---

## Task 2: Config templates + adaptive policy (5 methods)

- [ ] **Step 2.1: Write failing tests**

Append to `server/tests/test_meraki_org_endpoints.py`:

```python
@pytest.mark.asyncio
async def test_get_org_config_templates(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/configTemplates").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_config_templates("123") == []


@pytest.mark.asyncio
async def test_get_org_adaptive_policy_settings(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/adaptivePolicy/settings").mock(return_value=httpx.Response(200, json={"enabledNetworks": []}))
        assert "enabledNetworks" in await client.get_org_adaptive_policy_settings("123")


@pytest.mark.asyncio
async def test_get_org_adaptive_policy_acls(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/adaptivePolicy/acls").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_adaptive_policy_acls("123") == []


@pytest.mark.asyncio
async def test_get_org_adaptive_policy_groups(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/adaptivePolicy/groups").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_adaptive_policy_groups("123") == []


@pytest.mark.asyncio
async def test_get_org_adaptive_policy_policies(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/adaptivePolicy/policies").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_adaptive_policy_policies("123") == []
```

- [ ] **Step 2.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_org_endpoints.py -v`

Expected: AttributeError for new methods.

- [ ] **Step 2.3: Add the 5 methods**

Append to `MerakiClient` in `server/meraki_client.py`:

```python
    async def get_org_config_templates(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/configTemplates")

    async def get_org_adaptive_policy_settings(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/settings")

    async def get_org_adaptive_policy_acls(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/acls")

    async def get_org_adaptive_policy_groups(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/groups")

    async def get_org_adaptive_policy_policies(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/adaptivePolicy/policies")
```

- [ ] **Step 2.4: Run — should pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_org_endpoints.py -v`

Expected: 11 tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_org_endpoints.py
git commit -m "feat(meraki): config templates + adaptive policy methods (Plan 1.06)"
```

---

## Task 3: VPN + SNMP + alerts + inventory + licensing (7 methods)

- [ ] **Step 3.1: Write failing tests**

Append to `server/tests/test_meraki_org_endpoints.py`:

```python
@pytest.mark.asyncio
async def test_get_org_appliance_vpn_third_party_peers(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/appliance/vpn/thirdPartyVPNPeers").mock(return_value=httpx.Response(200, json={"peers": []}))
        assert await client.get_org_appliance_vpn_third_party_peers("123") == {"peers": []}


@pytest.mark.asyncio
async def test_get_org_appliance_vpn_firewall(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/appliance/vpn/vpnFirewallRules").mock(return_value=httpx.Response(200, json={"rules": []}))
        assert await client.get_org_appliance_vpn_firewall("123") == {"rules": []}


@pytest.mark.asyncio
async def test_get_org_snmp(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/snmp").mock(return_value=httpx.Response(200, json={"v2cEnabled": False}))
        assert "v2cEnabled" in await client.get_org_snmp("123")


@pytest.mark.asyncio
async def test_get_org_alerts_profiles(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/alerts/profiles").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_alerts_profiles("123") == []


@pytest.mark.asyncio
async def test_get_org_inventory_devices(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/inventory/devices").mock(return_value=httpx.Response(200, json=[{"serial": "Q2AB"}]))
        assert await client.get_org_inventory_devices("123") == [{"serial": "Q2AB"}]


@pytest.mark.asyncio
async def test_get_org_licenses_per_device(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/licenses").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_licenses_per_device("123") == []


@pytest.mark.asyncio
async def test_get_org_licenses_coterm(client):
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/123/licensing/coterm/licenses").mock(return_value=httpx.Response(200, json=[]))
        assert await client.get_org_licenses_coterm("123") == []
```

- [ ] **Step 3.2: Run — should fail**

Expected: AttributeError for new methods.

- [ ] **Step 3.3: Add the 7 methods**

Append to `MerakiClient`:

```python
    async def get_org_appliance_vpn_third_party_peers(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/appliance/vpn/thirdPartyVPNPeers")

    async def get_org_appliance_vpn_firewall(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/appliance/vpn/vpnFirewallRules")

    async def get_org_snmp(self, org_id: str) -> dict:
        return await self._get(f"/organizations/{org_id}/snmp")

    async def get_org_alerts_profiles(self, org_id: str) -> list[dict]:
        return await self._get(f"/organizations/{org_id}/alerts/profiles")

    async def get_org_inventory_devices(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/inventory/devices")

    async def get_org_licenses_per_device(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/licenses")

    async def get_org_licenses_coterm(self, org_id: str) -> list[dict]:
        return await self._get_paginated(f"/organizations/{org_id}/licensing/coterm/licenses")
```

- [ ] **Step 3.4: Run — should pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_meraki_org_endpoints.py -v`

Expected: 18 tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/meraki_client.py server/tests/test_meraki_org_endpoints.py
git commit -m "feat(meraki): VPN + SNMP + alerts + inventory + licensing org methods (Plan 1.06)"
```

---

## Completion Checklist

- [ ] 18 `get_org_*` methods exist on `MerakiClient`
- [ ] 18 passing tests in `server/tests/test_meraki_org_endpoints.py`
- [ ] Paginated endpoints (policy objects, inventory, licensing) use `_get_paginated`
- [ ] Full test suite green
- [ ] 3 commits
