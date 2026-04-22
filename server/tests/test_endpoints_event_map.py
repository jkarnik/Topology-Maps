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
