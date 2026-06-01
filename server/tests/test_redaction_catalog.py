"""Tests for the redaction catalog (Plan 1.03)."""
from __future__ import annotations

from server.config_collector.redaction_catalog import NORMALIZATION_PATHS, REDACTION_PATHS


def test_catalog_is_a_dict():
    assert isinstance(REDACTION_PATHS, dict)


def test_catalog_has_expected_core_areas():
    """The spec mandates these config_area keys carry secrets."""
    expected = {
        "wireless_ssids",
        "wireless_ssid_identity_psks",
        "appliance_site_to_site_vpn",
        "network_snmp",
        "org_snmp",
        "network_webhooks_http_servers",
    }
    missing = expected - REDACTION_PATHS.keys()
    assert not missing, f"Catalog missing entries: {missing}"


def test_catalog_values_are_non_empty_path_lists():
    for area, paths in REDACTION_PATHS.items():
        assert isinstance(paths, list), f"{area}: paths must be a list"
        assert len(paths) > 0, f"{area}: must have at least one path"
        for p in paths:
            assert isinstance(p, str) and p, f"{area}: path must be a non-empty string"


def test_normalization_paths_is_dict_of_lists():
    assert isinstance(NORMALIZATION_PATHS, dict)
    for area, paths in NORMALIZATION_PATHS.items():
        assert isinstance(area, str), f"{area!r} key is not a str"
        assert isinstance(paths, list), f"{area!r} value is not a list"
        assert len(paths) > 0, f"{area!r} must have at least one path"
        for p in paths:
            assert isinstance(p, str) and p, f"path {p!r} in {area!r} must be a non-empty string"


def test_normalization_paths_covers_expected_areas():
    expected = {
        "device_management_interface",
        "switch_device_ports",
        "switch_device_warm_spare",
        "switch_device_routing_interfaces",
        "switch_device_routing_static_routes",
        "wireless_device_bluetooth",
    }
    assert expected == set(NORMALIZATION_PATHS.keys())
