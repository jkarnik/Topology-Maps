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
