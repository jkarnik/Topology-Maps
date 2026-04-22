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
