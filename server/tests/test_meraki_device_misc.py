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
