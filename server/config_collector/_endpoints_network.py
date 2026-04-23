"""Network-level endpoint definitions (Plan 1.04).

Organized by product family for readability. All definitions feed into
NETWORK_ENDPOINTS at the bottom of the file.
"""
from __future__ import annotations

from server.config_collector.endpoints_catalog import EndpointSpec

# ---------------------------------------------------------------------------
# Generic (always applies)
# ---------------------------------------------------------------------------

_GENERIC: tuple[EndpointSpec, ...] = (
    EndpointSpec("network_metadata",            "network", "/networks/{network_id}",                    (), 1, False),
    EndpointSpec("network_settings",            "network", "/networks/{network_id}/settings",           (), 1, False),
    EndpointSpec("network_group_policies",      "network", "/networks/{network_id}/groupPolicies",      (), 1, False),
    EndpointSpec("network_syslog_servers",      "network", "/networks/{network_id}/syslogServers",      (), 1, False),
    EndpointSpec("network_snmp",                "network", "/networks/{network_id}/snmp",               (), 2, False),
    EndpointSpec("network_traffic_analysis",    "network", "/networks/{network_id}/trafficAnalysis",    (), 2, False),
    EndpointSpec("network_netflow",             "network", "/networks/{network_id}/netflow",            (), 2, False),
    EndpointSpec("network_alerts_settings",     "network", "/networks/{network_id}/alerts/settings",    (), 2, False),
    EndpointSpec("network_webhooks_http_servers","network","/networks/{network_id}/webhooks/httpServers",(), 2, False),
    EndpointSpec("network_webhooks_payload_templates","network","/networks/{network_id}/webhooks/payloadTemplates",(), 2, False),
    EndpointSpec("network_firmware_upgrades",   "network", "/networks/{network_id}/firmwareUpgrades",   (), 2, False),
    EndpointSpec("network_floor_plans",         "network", "/networks/{network_id}/floorPlans",         (), 2, False),
)

# ---------------------------------------------------------------------------
# MX — appliance
# ---------------------------------------------------------------------------

_MX: tuple[EndpointSpec, ...] = (
    EndpointSpec("appliance_vlans",                    "network", "/networks/{network_id}/appliance/vlans",                           ("appliance",), 1, False),
    EndpointSpec("appliance_vlans_settings",           "network", "/networks/{network_id}/appliance/vlans/settings",                  ("appliance",), 1, False),
    EndpointSpec("appliance_single_lan",               "network", "/networks/{network_id}/appliance/singleLan",                       ("appliance",), 1, False),
    EndpointSpec("appliance_ports",                    "network", "/networks/{network_id}/appliance/ports",                           ("appliance",), 1, False),
    EndpointSpec("appliance_firewall_l3",              "network", "/networks/{network_id}/appliance/firewall/l3FirewallRules",        ("appliance",), 1, False),
    EndpointSpec("appliance_firewall_l7",              "network", "/networks/{network_id}/appliance/firewall/l7FirewallRules",        ("appliance",), 1, False),
    EndpointSpec("appliance_firewall_inbound",         "network", "/networks/{network_id}/appliance/firewall/inboundFirewallRules",   ("appliance",), 1, False),
    EndpointSpec("appliance_firewall_port_forwarding", "network", "/networks/{network_id}/appliance/firewall/portForwardingRules",    ("appliance",), 1, False),
    EndpointSpec("appliance_firewall_one_to_one_nat",  "network", "/networks/{network_id}/appliance/firewall/oneToOneNatRules",       ("appliance",), 1, False),
    EndpointSpec("appliance_firewall_one_to_many_nat", "network", "/networks/{network_id}/appliance/firewall/oneToManyNatRules",      ("appliance",), 2, False),
    EndpointSpec("appliance_firewall_firewalled_services","network","/networks/{network_id}/appliance/firewall/firewalledServices",   ("appliance",), 2, False),
    EndpointSpec("appliance_firewall_settings",        "network", "/networks/{network_id}/appliance/firewall/settings",               ("appliance",), 2, False),
    EndpointSpec("appliance_firewall_cellular",        "network", "/networks/{network_id}/appliance/firewall/cellularFirewallRules",  ("appliance",), 2, False),
    EndpointSpec("appliance_content_filtering",        "network", "/networks/{network_id}/appliance/contentFiltering",                ("appliance",), 1, False),
    EndpointSpec("appliance_security_intrusion",       "network", "/networks/{network_id}/appliance/security/intrusion",              ("appliance",), 1, False),
    EndpointSpec("appliance_security_malware",         "network", "/networks/{network_id}/appliance/security/malware",                ("appliance",), 1, False),
    EndpointSpec("appliance_traffic_shaping_rules",    "network", "/networks/{network_id}/appliance/trafficShaping/rules",            ("appliance",), 1, False),
    EndpointSpec("appliance_uplink_bandwidth",         "network", "/networks/{network_id}/appliance/trafficShaping/uplinkBandwidth",  ("appliance",), 1, False),
    EndpointSpec("appliance_uplink_selection",         "network", "/networks/{network_id}/appliance/trafficShaping/uplinkSelection",  ("appliance",), 1, False),
    EndpointSpec("appliance_custom_performance_classes","network","/networks/{network_id}/appliance/trafficShaping/customPerformanceClasses",("appliance",), 2, False),
    EndpointSpec("appliance_site_to_site_vpn",         "network", "/networks/{network_id}/appliance/vpn/siteToSiteVpn",               ("appliance",), 1, False),
    EndpointSpec("appliance_vpn_bgp",                  "network", "/networks/{network_id}/appliance/vpn/bgp",                         ("appliance",), 2, False),
    EndpointSpec("appliance_static_routes",            "network", "/networks/{network_id}/appliance/staticRoutes",                    ("appliance",), 1, False),
    EndpointSpec("appliance_warm_spare",               "network", "/networks/{network_id}/appliance/warmSpare",                       ("appliance",), 1, False),
    EndpointSpec("appliance_connectivity_monitoring",  "network", "/networks/{network_id}/appliance/connectivityMonitoringDestinations",("appliance",), 2, False),
    EndpointSpec("appliance_settings",                 "network", "/networks/{network_id}/appliance/settings",                        ("appliance",), 2, False),
)

# ---------------------------------------------------------------------------
# MS — switch
# ---------------------------------------------------------------------------

_MS: tuple[EndpointSpec, ...] = (
    EndpointSpec("switch_access_policies",      "network", "/networks/{network_id}/switch/accessPolicies",                ("switch",), 1, False),
    EndpointSpec("switch_acls",                 "network", "/networks/{network_id}/switch/accessControlLists",            ("switch",), 1, False),
    EndpointSpec("switch_qos_rules",            "network", "/networks/{network_id}/switch/qosRules",                      ("switch",), 1, False),
    EndpointSpec("switch_qos_order",            "network", "/networks/{network_id}/switch/qosRules/order",                ("switch",), 1, False),
    EndpointSpec("switch_dscp_to_cos",          "network", "/networks/{network_id}/switch/dscpToCosMappings",             ("switch",), 2, False),
    EndpointSpec("switch_settings",             "network", "/networks/{network_id}/switch/settings",                      ("switch",), 2, False),
    EndpointSpec("switch_stp",                  "network", "/networks/{network_id}/switch/stp",                           ("switch",), 1, False),
    EndpointSpec("switch_storm_control",        "network", "/networks/{network_id}/switch/stormControl",                  ("switch",), 2, False),
    EndpointSpec("switch_mtu",                  "network", "/networks/{network_id}/switch/mtu",                           ("switch",), 2, False),
    EndpointSpec("switch_stacks",               "network", "/networks/{network_id}/switch/stacks",                        ("switch",), 1, False),
    EndpointSpec("switch_port_schedules",       "network", "/networks/{network_id}/switch/portSchedules",                 ("switch",), 2, False),
    EndpointSpec("switch_link_aggregations",    "network", "/networks/{network_id}/switch/linkAggregations",              ("switch",), 1, False),
    EndpointSpec("switch_dhcp_server_policy",   "network", "/networks/{network_id}/switch/dhcpServerPolicy",              ("switch",), 1, False),
    EndpointSpec("switch_multicast",            "network", "/networks/{network_id}/switch/routing/multicast",             ("switch",), 2, False),
    EndpointSpec("switch_multicast_rps",        "network", "/networks/{network_id}/switch/routing/multicast/rendezvousPoints",("switch",),2, False),
    EndpointSpec("switch_ospf",                 "network", "/networks/{network_id}/switch/routing/ospf",                  ("switch",), 2, False),
)

# ---------------------------------------------------------------------------
# MR — wireless
# ---------------------------------------------------------------------------

_MR: tuple[EndpointSpec, ...] = (
    EndpointSpec("wireless_ssids",              "network", "/networks/{network_id}/wireless/ssids",                       ("wireless",), 1, False),
    EndpointSpec("wireless_rf_profiles",        "network", "/networks/{network_id}/wireless/rfProfiles",                  ("wireless",), 1, False),
    EndpointSpec("wireless_settings",           "network", "/networks/{network_id}/wireless/settings",                    ("wireless",), 1, False),
    EndpointSpec("wireless_bluetooth",          "network", "/networks/{network_id}/wireless/bluetooth/settings",          ("wireless",), 2, False),
    EndpointSpec("wireless_ap_port_profiles",   "network", "/networks/{network_id}/wireless/ethernet/ports/profiles",     ("wireless",), 2, False),
)

# ---------------------------------------------------------------------------
# Per-SSID sub-endpoints (ssid scope)
# ---------------------------------------------------------------------------

_PER_SSID: tuple[EndpointSpec, ...] = (
    EndpointSpec("wireless_ssid_l3_firewall",   "ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/firewall/l3FirewallRules", ("wireless",), 1, False),
    EndpointSpec("wireless_ssid_l7_firewall",   "ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/firewall/l7FirewallRules", ("wireless",), 1, False),
    EndpointSpec("wireless_ssid_traffic_shaping","ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/trafficShaping/rules",    ("wireless",), 1, False),
    EndpointSpec("wireless_ssid_splash",        "ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/splash/settings",          ("wireless",), 2, False),
    EndpointSpec("wireless_ssid_schedules",     "ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/schedules",                ("wireless",), 2, False),
    EndpointSpec("wireless_ssid_vpn",           "ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/vpn",                      ("wireless",), 2, False),
    EndpointSpec("wireless_ssid_device_type_policies","ssid","/networks/{network_id}/wireless/ssids/{ssid_number}/deviceTypeGroupPolicies",("wireless",),2, False),
    EndpointSpec("wireless_ssid_identity_psks", "ssid", "/networks/{network_id}/wireless/ssids/{ssid_number}/identityPsks",             ("wireless",), 2, False),
)

# ---------------------------------------------------------------------------
# MV / MG / SM
# ---------------------------------------------------------------------------

_MV_MG_SM: tuple[EndpointSpec, ...] = (
    EndpointSpec("camera_quality_retention",    "network", "/networks/{network_id}/camera/qualityRetentionProfiles",     ("camera",), 2, False),
    EndpointSpec("camera_schedules",            "network", "/networks/{network_id}/camera/schedules",                    ("camera",), 2, False),
    EndpointSpec("cellular_dhcp",               "network", "/networks/{network_id}/cellularGateway/dhcp",                ("cellularGateway",), 2, False),
    EndpointSpec("cellular_subnet_pool",        "network", "/networks/{network_id}/cellularGateway/subnetPool",          ("cellularGateway",), 2, False),
    EndpointSpec("cellular_uplink",             "network", "/networks/{network_id}/cellularGateway/uplink",              ("cellularGateway",), 2, False),
    EndpointSpec("cellular_connectivity_monitoring","network","/networks/{network_id}/cellularGateway/connectivityMonitoringDestinations",("cellularGateway",),2, False),
    EndpointSpec("sm_profiles",                 "network", "/networks/{network_id}/sm/profiles",                         ("systemsManager",), 2, False),
)

# Aggregate
NETWORK_ENDPOINTS: tuple[EndpointSpec, ...] = _GENERIC + _MX + _MS + _MR + _PER_SSID + _MV_MG_SM
