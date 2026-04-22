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
