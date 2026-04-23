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
