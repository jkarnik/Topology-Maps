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
