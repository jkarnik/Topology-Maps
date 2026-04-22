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
