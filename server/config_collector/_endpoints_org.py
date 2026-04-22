"""Org-level endpoint definitions (Plan 1.04)."""
from __future__ import annotations

from server.config_collector.endpoints_catalog import EndpointSpec

ORG_ENDPOINTS: tuple[EndpointSpec, ...] = (
    EndpointSpec("org_admins",                        "org", "/organizations/{org_id}/admins",                          (), 1, False),
    EndpointSpec("org_saml_roles",                    "org", "/organizations/{org_id}/samlRoles",                       (), 1, False),
    EndpointSpec("org_saml",                          "org", "/organizations/{org_id}/saml",                            (), 1, False),
    EndpointSpec("org_login_security",                "org", "/organizations/{org_id}/loginSecurity",                   (), 1, False),
    EndpointSpec("org_policy_objects",                "org", "/organizations/{org_id}/policyObjects",                   (), 1, True),
    EndpointSpec("org_policy_object_groups",          "org", "/organizations/{org_id}/policyObjects/groups",            (), 1, True),
    EndpointSpec("org_config_templates",              "org", "/organizations/{org_id}/configTemplates",                 (), 1, False),
    EndpointSpec("org_adaptive_policy_settings",      "org", "/organizations/{org_id}/adaptivePolicy/settings",         (), 2, False),
    EndpointSpec("org_adaptive_policy_acls",          "org", "/organizations/{org_id}/adaptivePolicy/acls",             (), 2, False),
    EndpointSpec("org_adaptive_policy_groups",        "org", "/organizations/{org_id}/adaptivePolicy/groups",           (), 2, False),
    EndpointSpec("org_adaptive_policy_policies",      "org", "/organizations/{org_id}/adaptivePolicy/policies",         (), 2, False),
    EndpointSpec("org_appliance_vpn_third_party_peers","org", "/organizations/{org_id}/appliance/vpn/thirdPartyVPNPeers",(), 1, False),
    EndpointSpec("org_appliance_vpn_firewall",        "org", "/organizations/{org_id}/appliance/vpn/vpnFirewallRules",  (), 1, False),
    EndpointSpec("org_snmp",                          "org", "/organizations/{org_id}/snmp",                            (), 2, False),
    EndpointSpec("org_alerts_profiles",               "org", "/organizations/{org_id}/alerts/profiles",                 (), 2, False),
    EndpointSpec("org_inventory_devices",             "org", "/organizations/{org_id}/inventory/devices",               (), 2, True),
    EndpointSpec("org_licenses_per_device",           "org", "/organizations/{org_id}/licenses",                        (), 2, True),
    EndpointSpec("org_licenses_coterm",               "org", "/organizations/{org_id}/licensing/coterm/licenses",       (), 2, True),
)
