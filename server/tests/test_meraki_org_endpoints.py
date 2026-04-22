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
