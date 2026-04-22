# Plan 1.04 — Endpoints Catalog

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution guideline (user directive):** Before executing ANY task below, evaluate whether that task can be split further into smaller, independently executable subtasks. Prefer doing less per turn over doing more. Commit frequently.

**Goal:** Build a single source of truth for every Tier-1 and Tier-2 Meraki config endpoint. Each entry carries: URL template, scope (org/network/device), product-type filter, canonical `config_area` key, whether the endpoint paginates, and any event-to-endpoints mapping rules. No HTTP calls, no state — pure data plus small helpers.

**Architecture:** One module `endpoints_catalog.py` exposing: (1) `ENDPOINTS` — a list of `EndpointSpec` dataclasses for every tier 1+2 endpoint; (2) `expand_for_org(orgs, networks, devices, enabled_ssids)` — enumerates concrete URLs the scanner must fetch; (3) `event_to_endpoints(event)` — maps a Meraki change-log event onto the set of affected endpoints. Splitting endpoints by level (org / network / device) across separate source files keeps each file focused; a single top-level `ENDPOINTS` list aggregates them.

**Tech Stack:** Python 3.9+, stdlib `dataclasses`, pytest.

**Spec reference:** [docs/superpowers/specs/2026-04-22-config-collection-phase1-design.md — Scope: Config Endpoints to Collect](../specs/2026-04-22-config-collection-phase1-design.md#scope-config-endpoints-to-collect)

**Depends on:** None (no code deps — pure data).

**Unblocks:** Plan 1.13 (baseline runner — iterates `ENDPOINTS`), Plan 1.14 (change-log poller — uses `event_to_endpoints`).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/endpoints_catalog.py` | Create | `EndpointSpec` dataclass, top-level `ENDPOINTS` list, `expand_for_org()`, `event_to_endpoints()` |
| `server/config_collector/_endpoints_org.py` | Create | Org-level endpoint definitions (~18) |
| `server/config_collector/_endpoints_network.py` | Create | Network-level endpoints (generic + MX + MS + MR + per-SSID + MV/MG/SM) |
| `server/config_collector/_endpoints_device.py` | Create | Device-level endpoints |
| `server/tests/test_endpoints_catalog.py` | Create | Catalog sanity tests (all areas have specs, product filters valid, URL templates resolvable) |
| `server/tests/test_endpoints_expand.py` | Create | `expand_for_org()` produces correct URL sets under various org compositions |
| `server/tests/test_endpoints_event_map.py` | Create | `event_to_endpoints()` maps change-log events correctly |

Rationale for the split: endpoint definitions are ~55 rows of data. Keeping them in one file makes it hard to find anything; splitting by level (org/network/device) is how humans already think about them (matches the spec's structure).

---

## Task 1: `EndpointSpec` dataclass

Define the shape every endpoint row will fill.

**Files:**
- Create: `server/config_collector/endpoints_catalog.py`
- Create: `server/tests/test_endpoints_catalog.py`

- [ ] **Step 1.1: Write the failing test**

Create `server/tests/test_endpoints_catalog.py`:

```python
"""Tests for the endpoints catalog (Plan 1.04)."""
from __future__ import annotations

import pytest

from server.config_collector.endpoints_catalog import EndpointSpec


def test_endpoint_spec_required_fields():
    spec = EndpointSpec(
        config_area="appliance_vlans",
        scope="network",
        url_template="/networks/{network_id}/appliance/vlans",
        product_filter=("appliance",),
        tier=1,
        paginated=False,
    )
    assert spec.config_area == "appliance_vlans"
    assert spec.scope == "network"
    assert spec.product_filter == ("appliance",)
    assert spec.paginated is False


def test_endpoint_spec_org_scope_has_no_product_filter():
    """Org-scoped specs typically have no product filter (product_filter=())."""
    spec = EndpointSpec(
        config_area="org_admins",
        scope="org",
        url_template="/organizations/{org_id}/admins",
        product_filter=(),
        tier=1,
        paginated=True,
    )
    assert spec.scope == "org"
    assert spec.product_filter == ()


def test_endpoint_spec_is_frozen():
    """Specs must be immutable so nobody accidentally mutates the global list."""
    spec = EndpointSpec(
        config_area="x", scope="org", url_template="/x",
        product_filter=(), tier=1, paginated=False,
    )
    with pytest.raises((AttributeError, Exception)):
        spec.tier = 2  # type: ignore
```

- [ ] **Step 1.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: `FAILED` — `ModuleNotFoundError`.

- [ ] **Step 1.3: Create the dataclass**

Create `server/config_collector/endpoints_catalog.py`:

```python
"""Single source of truth for Tier 1+2 Meraki config endpoints.

Every entry in `ENDPOINTS` represents one GET endpoint the collector
pulls. The scanner uses this catalog to enumerate URLs during a
baseline or anti-drift sweep. The change-log poller uses
`event_to_endpoints()` to map a change event to the endpoints it
affects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Scope = Literal["org", "network", "device", "ssid"]


@dataclass(frozen=True)
class EndpointSpec:
    """One Meraki config endpoint.

    Fields
    ------
    config_area   : stable canonical key used as config_observations.config_area
    scope         : 'org' | 'network' | 'device' | 'ssid'
    url_template  : relative URL with {org_id}/{network_id}/{serial}/{ssid_number} placeholders
    product_filter: tuple of Meraki product-type strings; () means no filter
    tier          : 1 or 2 (informational; both are collected in Phase 1)
    paginated     : True if response requires Link-header pagination
    """
    config_area: str
    scope: Scope
    url_template: str
    product_filter: tuple[str, ...]
    tier: int
    paginated: bool
```

- [ ] **Step 1.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: All 3 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/endpoints_catalog.py server/tests/test_endpoints_catalog.py
git commit -m "feat(config): EndpointSpec dataclass for endpoints catalog (Plan 1.04)"
```

---

## Task 2: Org-level endpoint definitions

**Files:**
- Create: `server/config_collector/_endpoints_org.py`
- Modify: `server/config_collector/endpoints_catalog.py` (import + append to ENDPOINTS)
- Modify: `server/tests/test_endpoints_catalog.py`

- [ ] **Step 2.1: Write the failing test**

Append to `server/tests/test_endpoints_catalog.py`:

```python
from server.config_collector.endpoints_catalog import ENDPOINTS


def test_org_endpoints_include_all_spec_entries():
    """All org-level entries from the spec are in the catalog."""
    org_specs = [e for e in ENDPOINTS if e.scope == "org"]
    areas = {e.config_area for e in org_specs}
    expected = {
        "org_admins", "org_saml_roles", "org_saml",
        "org_login_security", "org_policy_objects", "org_policy_object_groups",
        "org_config_templates",
        "org_adaptive_policy_settings", "org_adaptive_policy_acls",
        "org_adaptive_policy_groups", "org_adaptive_policy_policies",
        "org_appliance_vpn_third_party_peers", "org_appliance_vpn_firewall",
        "org_snmp", "org_alerts_profiles",
        "org_inventory_devices", "org_licenses_per_device", "org_licenses_coterm",
    }
    missing = expected - areas
    assert not missing, f"Missing org areas: {missing}"


def test_paginated_endpoints_include_configuration_changes_peers():
    """configurationChanges endpoint is NOT in ENDPOINTS — it's polled separately.
    But inventory/devices IS in ENDPOINTS and should be paginated."""
    by_area = {e.config_area: e for e in ENDPOINTS}
    assert by_area["org_inventory_devices"].paginated is True
    assert by_area["org_admins"].paginated is False
```

- [ ] **Step 2.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: `ImportError: cannot import name 'ENDPOINTS'`.

- [ ] **Step 2.3: Create the org endpoints module**

Create `server/config_collector/_endpoints_org.py`:

```python
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
```

- [ ] **Step 2.4: Add the aggregate `ENDPOINTS` tuple in the catalog module**

Append to `server/config_collector/endpoints_catalog.py`:

```python
from server.config_collector._endpoints_org import ORG_ENDPOINTS

# Aggregate list of every endpoint the collector knows about.
# More tuples will be added in subsequent tasks (_endpoints_network, _endpoints_device).
ENDPOINTS: tuple[EndpointSpec, ...] = ORG_ENDPOINTS
```

- [ ] **Step 2.5: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: All 5 tests pass.

- [ ] **Step 2.6: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/_endpoints_org.py server/config_collector/endpoints_catalog.py server/tests/test_endpoints_catalog.py
git commit -m "feat(config): add 18 org-level endpoint specs to catalog (Plan 1.04)"
```

---

## Task 3: Network-level endpoint definitions

Network-level is the largest chunk (~60 entries across generic, MX, MS, MR, per-SSID, MV, MG, SM). Consolidated into one module for readability since the executing agent may choose to split into per-product files during implementation — that is a valid "split smaller" move.

**Files:**
- Create: `server/config_collector/_endpoints_network.py`
- Modify: `server/config_collector/endpoints_catalog.py`
- Modify: `server/tests/test_endpoints_catalog.py`

- [ ] **Step 3.1: Write the failing test**

Append to `server/tests/test_endpoints_catalog.py`:

```python
def test_network_endpoints_cover_spec_tiers():
    """Network scope contains the canonical Tier-1 areas from the spec."""
    net_specs = [e for e in ENDPOINTS if e.scope == "network"]
    areas = {e.config_area for e in net_specs}
    tier1_expected = {
        # Generic
        "network_metadata", "network_settings", "network_group_policies",
        "network_syslog_servers",
        # MX
        "appliance_vlans", "appliance_vlans_settings", "appliance_single_lan",
        "appliance_ports", "appliance_firewall_l3", "appliance_firewall_l7",
        "appliance_firewall_inbound", "appliance_firewall_port_forwarding",
        "appliance_firewall_one_to_one_nat", "appliance_content_filtering",
        "appliance_security_intrusion", "appliance_security_malware",
        "appliance_traffic_shaping_rules", "appliance_uplink_bandwidth",
        "appliance_uplink_selection", "appliance_site_to_site_vpn",
        "appliance_static_routes", "appliance_warm_spare",
        # MS
        "switch_access_policies", "switch_acls", "switch_qos_rules",
        "switch_qos_order", "switch_stp", "switch_stacks",
        "switch_link_aggregations", "switch_dhcp_server_policy",
        # MR
        "wireless_ssids", "wireless_rf_profiles", "wireless_settings",
        # Per-SSID
        "wireless_ssid_l3_firewall", "wireless_ssid_l7_firewall",
        "wireless_ssid_traffic_shaping",
    }
    missing = tier1_expected - areas
    assert not missing, f"Tier-1 network areas missing: {missing}"


def test_ssid_scope_has_number_placeholder():
    """Per-SSID specs use ssid scope and reference {ssid_number}."""
    ssid_specs = [e for e in ENDPOINTS if e.scope == "ssid"]
    assert len(ssid_specs) >= 5, "expected at least 5 per-SSID sub-endpoints"
    for s in ssid_specs:
        assert "{ssid_number}" in s.url_template
        assert "wireless" in s.product_filter or s.product_filter == ("wireless",)
```

- [ ] **Step 3.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: `AssertionError: Tier-1 network areas missing: {...}`.

- [ ] **Step 3.3: Create the network endpoints module**

Create `server/config_collector/_endpoints_network.py`:

```python
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
# Per-SSID sub-endpoints (ssid scope; enumerated against enabled SSIDs + reactive catch)
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
# MV / MG / SM — secondary product families
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
```

- [ ] **Step 3.4: Wire NETWORK_ENDPOINTS into the catalog**

In `server/config_collector/endpoints_catalog.py`, update the `ENDPOINTS` assignment:

```python
from server.config_collector._endpoints_org import ORG_ENDPOINTS
from server.config_collector._endpoints_network import NETWORK_ENDPOINTS

ENDPOINTS: tuple[EndpointSpec, ...] = ORG_ENDPOINTS + NETWORK_ENDPOINTS
```

- [ ] **Step 3.5: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: All 7 tests pass.

- [ ] **Step 3.6: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/_endpoints_network.py server/config_collector/endpoints_catalog.py server/tests/test_endpoints_catalog.py
git commit -m "feat(config): add network-level and per-SSID endpoint specs (Plan 1.04)"
```

---

## Task 4: Device-level endpoint definitions

**Files:**
- Create: `server/config_collector/_endpoints_device.py`
- Modify: `server/config_collector/endpoints_catalog.py`
- Modify: `server/tests/test_endpoints_catalog.py`

- [ ] **Step 4.1: Write the failing test**

Append to `server/tests/test_endpoints_catalog.py`:

```python
def test_device_endpoints_cover_spec():
    """All device-level areas from the spec are in the catalog."""
    dev_specs = [e for e in ENDPOINTS if e.scope == "device"]
    areas = {e.config_area for e in dev_specs}
    expected = {
        "device_metadata",
        "device_management_interface",
        "switch_device_ports",
        "switch_device_routing_interfaces",
        "switch_device_routing_static_routes",
        "switch_device_warm_spare",
        "wireless_device_radio_settings",
        "wireless_device_bluetooth",
        "appliance_device_uplinks",
        "camera_device_quality_retention",
        "camera_device_video_settings",
        "camera_device_sense",
    }
    missing = expected - areas
    assert not missing, f"Missing device areas: {missing}"


def test_device_specs_include_serial_placeholder():
    """Device-scope URL templates all reference {serial}."""
    for e in ENDPOINTS:
        if e.scope == "device":
            assert "{serial}" in e.url_template, f"{e.config_area}: missing {{serial}}"
```

- [ ] **Step 4.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: `AssertionError: Missing device areas: {...}`.

- [ ] **Step 4.3: Create the device endpoints module**

Create `server/config_collector/_endpoints_device.py`:

```python
"""Device-level endpoint definitions (Plan 1.04)."""
from __future__ import annotations

from server.config_collector.endpoints_catalog import EndpointSpec

DEVICE_ENDPOINTS: tuple[EndpointSpec, ...] = (
    # All products
    EndpointSpec("device_metadata",                "device", "/devices/{serial}",                         (), 1, False),
    EndpointSpec("device_management_interface",    "device", "/devices/{serial}/managementInterface",     (), 1, False),
    # MS
    EndpointSpec("switch_device_ports",            "device", "/devices/{serial}/switch/ports",             ("switch",),    1, False),
    EndpointSpec("switch_device_routing_interfaces","device","/devices/{serial}/switch/routing/interfaces",("switch",),    2, False),
    EndpointSpec("switch_device_routing_static_routes","device","/devices/{serial}/switch/routing/staticRoutes",("switch",),2, False),
    EndpointSpec("switch_device_warm_spare",       "device", "/devices/{serial}/switch/warmSpare",          ("switch",),    2, False),
    # MR
    EndpointSpec("wireless_device_radio_settings", "device", "/devices/{serial}/wireless/radio/settings",   ("wireless",),  1, False),
    EndpointSpec("wireless_device_bluetooth",      "device", "/devices/{serial}/wireless/bluetooth/settings",("wireless",), 2, False),
    # MX
    EndpointSpec("appliance_device_uplinks",       "device", "/devices/{serial}/appliance/uplinks/settings",("appliance",), 1, False),
    # MV
    EndpointSpec("camera_device_quality_retention","device", "/devices/{serial}/camera/qualityAndRetention",("camera",),    2, False),
    EndpointSpec("camera_device_video_settings",   "device", "/devices/{serial}/camera/videoSettings",      ("camera",),    2, False),
    EndpointSpec("camera_device_sense",            "device", "/devices/{serial}/camera/sense",              ("camera",),    2, False),
)
```

- [ ] **Step 4.4: Wire DEVICE_ENDPOINTS into the catalog**

In `server/config_collector/endpoints_catalog.py`:

```python
from server.config_collector._endpoints_org import ORG_ENDPOINTS
from server.config_collector._endpoints_network import NETWORK_ENDPOINTS
from server.config_collector._endpoints_device import DEVICE_ENDPOINTS

ENDPOINTS: tuple[EndpointSpec, ...] = ORG_ENDPOINTS + NETWORK_ENDPOINTS + DEVICE_ENDPOINTS
```

- [ ] **Step 4.5: Run the tests**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_catalog.py -v`

Expected: All 9 tests pass.

- [ ] **Step 4.6: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/_endpoints_device.py server/config_collector/endpoints_catalog.py server/tests/test_endpoints_catalog.py
git commit -m "feat(config): add device-level endpoint specs (Plan 1.04)"
```

---

## Task 5: `expand_for_org()` URL enumeration

Given the catalog plus a description of an org's composition (list of networks, devices, enabled-SSID tuples), produce concrete URLs the scanner should fetch. Applies product-type and SSID-enabled filters.

**Files:**
- Modify: `server/config_collector/endpoints_catalog.py`
- Create: `server/tests/test_endpoints_expand.py`

- [ ] **Step 5.1: Write the failing test**

Create `server/tests/test_endpoints_expand.py`:

```python
"""Tests for expand_for_org() URL enumeration (Plan 1.04)."""
from __future__ import annotations

from server.config_collector.endpoints_catalog import expand_for_org


def test_org_only_yields_org_urls():
    urls = list(expand_for_org(
        org_id="123",
        networks=[],
        devices_by_network={},
        enabled_ssids_by_network={},
    ))
    # Every URL is org-scoped
    assert all("/organizations/123/" in u["url"] for u in urls)
    # config_area carried through
    assert any(u["config_area"] == "org_admins" for u in urls)


def test_network_product_filter_skips_non_matching():
    """A network of productTypes=['wireless'] doesn't pull MX/MS endpoints."""
    urls = list(expand_for_org(
        org_id="123",
        networks=[{"id": "N_W", "productTypes": ["wireless"]}],
        devices_by_network={"N_W": []},
        enabled_ssids_by_network={"N_W": []},
    ))
    areas = {u["config_area"] for u in urls}
    # MR endpoints included
    assert "wireless_ssids" in areas
    # MX endpoints NOT included (network doesn't have appliance)
    assert "appliance_vlans" not in areas
    # Generic network endpoints ARE included
    assert "network_metadata" in areas


def test_per_ssid_expands_enabled_only():
    """Enabled SSIDs get per-ssid URL expansion; disabled ones are skipped."""
    urls = list(expand_for_org(
        org_id="123",
        networks=[{"id": "N_W", "productTypes": ["wireless"]}],
        devices_by_network={"N_W": []},
        enabled_ssids_by_network={"N_W": [0, 3]},  # SSIDs 0 and 3 enabled
    ))
    ssid_l3_urls = [u for u in urls if u["config_area"] == "wireless_ssid_l3_firewall"]
    assert len(ssid_l3_urls) == 2  # one per enabled SSID
    assert any("/ssids/0/" in u["url"] for u in ssid_l3_urls)
    assert any("/ssids/3/" in u["url"] for u in ssid_l3_urls)
    # No URL for disabled SSID 1
    assert not any("/ssids/1/" in u["url"] for u in ssid_l3_urls)


def test_device_filter_skips_wrong_product():
    """Device-level endpoints only pull for matching product types."""
    urls = list(expand_for_org(
        org_id="123",
        networks=[{"id": "N_MIX", "productTypes": ["switch", "wireless"]}],
        devices_by_network={
            "N_MIX": [
                {"serial": "Q2SW-0001", "productType": "switch"},
                {"serial": "Q2MR-0001", "productType": "wireless"},
            ],
        },
        enabled_ssids_by_network={"N_MIX": []},
    ))
    port_urls = [u for u in urls if u["config_area"] == "switch_device_ports"]
    assert len(port_urls) == 1
    assert "/devices/Q2SW-0001/" in port_urls[0]["url"]

    radio_urls = [u for u in urls if u["config_area"] == "wireless_device_radio_settings"]
    assert len(radio_urls) == 1
    assert "/devices/Q2MR-0001/" in radio_urls[0]["url"]
```

- [ ] **Step 5.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_expand.py -v`

Expected: `ImportError: cannot import name 'expand_for_org'`.

- [ ] **Step 5.3: Implement `expand_for_org()`**

Append to `server/config_collector/endpoints_catalog.py`:

```python
from typing import Iterator


def _network_matches(spec: EndpointSpec, network: dict) -> bool:
    """Product-type filter check for a network-scoped endpoint."""
    if not spec.product_filter:
        return True
    return any(p in (network.get("productTypes") or []) for p in spec.product_filter)


def _device_matches(spec: EndpointSpec, device: dict) -> bool:
    if not spec.product_filter:
        return True
    return device.get("productType") in spec.product_filter


def expand_for_org(
    org_id: str,
    networks: list[dict],
    devices_by_network: dict[str, list[dict]],
    enabled_ssids_by_network: dict[str, list[int]],
) -> Iterator[dict]:
    """Yield concrete URL jobs the scanner must fetch.

    Each yielded dict has keys:
      - url         : relative URL with placeholders resolved
      - config_area : canonical key for config_observations
      - scope       : 'org' | 'network' | 'device' | 'ssid'
      - entity_type : storage-layer entity_type
      - entity_id   : storage-layer entity_id
      - sub_key     : optional (e.g. ssid_number as str)
      - paginated   : bool
    """
    for spec in ENDPOINTS:
        if spec.scope == "org":
            yield {
                "url": spec.url_template.format(org_id=org_id),
                "config_area": spec.config_area,
                "scope": "org",
                "entity_type": "org",
                "entity_id": org_id,
                "sub_key": None,
                "paginated": spec.paginated,
            }

        elif spec.scope == "network":
            for net in networks:
                if not _network_matches(spec, net):
                    continue
                yield {
                    "url": spec.url_template.format(network_id=net["id"]),
                    "config_area": spec.config_area,
                    "scope": "network",
                    "entity_type": "network",
                    "entity_id": net["id"],
                    "sub_key": None,
                    "paginated": spec.paginated,
                }

        elif spec.scope == "ssid":
            for net in networks:
                if "wireless" not in (net.get("productTypes") or []):
                    continue
                for n in enabled_ssids_by_network.get(net["id"], []):
                    yield {
                        "url": spec.url_template.format(network_id=net["id"], ssid_number=n),
                        "config_area": spec.config_area,
                        "scope": "ssid",
                        "entity_type": "ssid",
                        "entity_id": f"{net['id']}:{n}",
                        "sub_key": str(n),
                        "paginated": spec.paginated,
                    }

        elif spec.scope == "device":
            for net in networks:
                for dev in devices_by_network.get(net["id"], []):
                    if not _device_matches(spec, dev):
                        continue
                    yield {
                        "url": spec.url_template.format(serial=dev["serial"]),
                        "config_area": spec.config_area,
                        "scope": "device",
                        "entity_type": "device",
                        "entity_id": dev["serial"],
                        "sub_key": None,
                        "paginated": spec.paginated,
                    }
```

- [ ] **Step 5.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_expand.py -v`

Expected: All 4 tests pass.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/endpoints_catalog.py server/tests/test_endpoints_expand.py
git commit -m "feat(config): expand_for_org URL enumeration with product + SSID filtering (Plan 1.04)"
```

---

## Task 6: `event_to_endpoints()` — change-log event mapping

Maps a Meraki change-log event onto the config_areas it affects, so the poller can issue targeted re-pulls.

**Files:**
- Modify: `server/config_collector/endpoints_catalog.py`
- Create: `server/tests/test_endpoints_event_map.py`

- [ ] **Step 6.1: Write the failing test**

Create `server/tests/test_endpoints_event_map.py`:

```python
"""Tests for event_to_endpoints() change-log mapping (Plan 1.04)."""
from __future__ import annotations

from server.config_collector.endpoints_catalog import event_to_endpoints


def test_vlan_event_maps_to_appliance_vlans():
    event = {
        "page": "Security & SD-WAN > Addressing & VLANs",
        "label": "VLAN",
        "networkId": "N_1",
    }
    areas = event_to_endpoints(event)
    assert "appliance_vlans" in areas


def test_l3_firewall_event_maps_correctly():
    event = {
        "page": "Security & SD-WAN > Firewall",
        "label": "L3 firewall rule",
        "networkId": "N_1",
    }
    areas = event_to_endpoints(event)
    assert "appliance_firewall_l3" in areas


def test_ssid_event_maps_to_ssid_and_per_ssid_subendpoints():
    """An event on a specific SSID triggers the SSIDs list plus per-SSID sub-endpoints."""
    event = {
        "page": "Wireless > Access Control",
        "label": "Bandwidth limit",
        "networkId": "N_W",
        "ssidNumber": 3,
    }
    areas = event_to_endpoints(event)
    assert "wireless_ssids" in areas
    assert "wireless_ssid_traffic_shaping" in areas
    # Reactive catch: also pull firewall sub-endpoints for SSID 3
    assert "wireless_ssid_l3_firewall" in areas
    assert "wireless_ssid_l7_firewall" in areas


def test_unknown_page_returns_empty():
    """Unmapped events don't raise; they just produce no pulls (logged elsewhere)."""
    event = {
        "page": "Some Unknown Dashboard Page",
        "label": "Fancy Feature",
        "networkId": "N_1",
    }
    assert event_to_endpoints(event) == set()
```

- [ ] **Step 6.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_event_map.py -v`

Expected: `ImportError: cannot import name 'event_to_endpoints'`.

- [ ] **Step 6.3: Implement `event_to_endpoints()`**

Append to `server/config_collector/endpoints_catalog.py`:

```python
# Dashboard page-prefix → set of config_areas to re-pull.
# More entries will be added as real Meraki pages are observed; the
# poller logs WARN on unmapped pages so the gap is visible.
_PAGE_PREFIX_MAP: dict[str, set[str]] = {
    "Security & SD-WAN > Addressing & VLANs": {
        "appliance_vlans", "appliance_vlans_settings", "appliance_single_lan",
    },
    "Security & SD-WAN > Firewall": {
        "appliance_firewall_l3", "appliance_firewall_l7",
        "appliance_firewall_inbound", "appliance_firewall_port_forwarding",
        "appliance_firewall_one_to_one_nat", "appliance_firewall_one_to_many_nat",
    },
    "Security & SD-WAN > Content filtering": {"appliance_content_filtering"},
    "Security & SD-WAN > Threat protection": {"appliance_security_intrusion", "appliance_security_malware"},
    "Security & SD-WAN > SD-WAN & traffic shaping": {
        "appliance_traffic_shaping_rules", "appliance_uplink_bandwidth", "appliance_uplink_selection",
    },
    "Security & SD-WAN > Site-to-site VPN": {"appliance_site_to_site_vpn", "appliance_vpn_bgp"},
    "Security & SD-WAN > Static routes": {"appliance_static_routes"},
    "Switch > Switch settings": {"switch_settings", "switch_stp", "switch_mtu"},
    "Switch > ACL": {"switch_acls"},
    "Switch > Access policies": {"switch_access_policies"},
    "Switch > QoS": {"switch_qos_rules", "switch_qos_order", "switch_dscp_to_cos"},
    "Switch > Stacks": {"switch_stacks"},
    "Switch > Link aggregation": {"switch_link_aggregations"},
    "Switch > DHCP servers & ARP": {"switch_dhcp_server_policy"},
    "Wireless > SSIDs": {"wireless_ssids"},
    "Wireless > Access Control": {"wireless_ssids", "wireless_ssid_traffic_shaping"},
    "Wireless > Firewall & traffic shaping": {
        "wireless_ssid_l3_firewall", "wireless_ssid_l7_firewall", "wireless_ssid_traffic_shaping",
    },
    "Wireless > RF profiles": {"wireless_rf_profiles"},
    "Network-wide > General": {"network_metadata", "network_settings"},
    "Network-wide > Alerts": {"network_alerts_settings"},
    "Network-wide > Group policies": {"network_group_policies"},
    "Organization > Administrators": {"org_admins", "org_saml_roles"},
    "Organization > Configuration templates": {"org_config_templates"},
    "Organization > Policy objects": {"org_policy_objects", "org_policy_object_groups"},
}

_PER_SSID_SUBAREAS: set[str] = {
    "wireless_ssid_l3_firewall",
    "wireless_ssid_l7_firewall",
    "wireless_ssid_traffic_shaping",
    "wireless_ssid_splash",
    "wireless_ssid_schedules",
    "wireless_ssid_vpn",
    "wireless_ssid_device_type_policies",
    "wireless_ssid_identity_psks",
}


def event_to_endpoints(event: dict) -> set[str]:
    """Map a Meraki change-log event to the set of config_areas to re-pull.

    Uses the event's `page` string as the primary key. If the event references
    a specific SSID (ssidNumber set), expands to include per-SSID sub-endpoints
    even if the change was only to an SSID-level setting — the reactive catch
    required by the spec.

    Returns an empty set for events with no known mapping; callers log these.
    """
    page = event.get("page") or ""
    areas: set[str] = set()
    for prefix, mapped in _PAGE_PREFIX_MAP.items():
        if page.startswith(prefix):
            areas |= mapped
            break

    # Reactive catch: any event with ssidNumber triggers per-SSID pulls
    if event.get("ssidNumber") is not None:
        areas |= {"wireless_ssids"} | _PER_SSID_SUBAREAS

    return areas
```

- [ ] **Step 6.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_endpoints_event_map.py -v`

Expected: All 4 tests pass.

- [ ] **Step 6.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/endpoints_catalog.py server/tests/test_endpoints_event_map.py
git commit -m "feat(config): event_to_endpoints change-log → config_area mapping (Plan 1.04)"
```

---

## Completion Checklist

- [ ] `server/config_collector/endpoints_catalog.py` + `_endpoints_org.py` + `_endpoints_network.py` + `_endpoints_device.py` exist
- [ ] `pytest server/tests/test_endpoints_catalog.py server/tests/test_endpoints_expand.py server/tests/test_endpoints_event_map.py -v` passes (~15 tests)
- [ ] Full test suite still green
- [ ] 6 commits on the branch

## What This Plan Unblocks

- Plan 1.13 (baseline runner) — iterates `expand_for_org()` output.
- Plan 1.14 (change-log poller) — uses `event_to_endpoints()`.
- Plans 1.05–1.09 (Meraki client extensions) — the client methods can be generated/cross-checked against `ENDPOINTS`.

## Out of Scope

- The actual Meraki API client methods (Plans 1.05–1.09).
- Dynamic discovery of networks/devices from the Dashboard API (that's where `expand_for_org()` input comes from — Plan 1.13 fetches it).
- Adding new `_PAGE_PREFIX_MAP` entries as real Meraki pages are observed in production — done reactively via WARN logs from Plan 1.14.



