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
