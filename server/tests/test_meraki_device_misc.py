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
