"""Tests for MerakiTransformer — L2 and L3 topology conversion."""

import pytest

from server.meraki_transformer import MerakiTransformer
from server.models import DeviceStatus, DeviceType, LinkProtocol


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

APPLIANCE_DEVICE = {
    "serial": "Q2AB-1111-AAAA",
    "productType": "appliance",
    "model": "MX68",
    "lanIp": "10.0.0.1",
    "mac": "aa:bb:cc:dd:ee:01",
}

SWITCH_DEVICE = {
    "serial": "Q2SW-2222-BBBB",
    "productType": "switch",
    "model": "MS225-24P",
    "lanIp": "10.0.0.2",
    "mac": "aa:bb:cc:dd:ee:02",
}

AP_DEVICE = {
    "serial": "Q2AP-3333-CCCC",
    "productType": "wireless",
    "model": "MR46",
    "lanIp": "10.0.0.3",
    "mac": "aa:bb:cc:dd:ee:03",
}

ALL_DEVICES = [APPLIANCE_DEVICE, SWITCH_DEVICE, AP_DEVICE]

ALL_STATUSES = [
    {"serial": "Q2AB-1111-AAAA", "status": "online"},
    {"serial": "Q2SW-2222-BBBB", "status": "offline"},
    {"serial": "Q2AP-3333-CCCC", "status": "alerting"},
]

LINK_LAYER_DATA = [
    {
        "links": [
            {
                "ends": [
                    {
                        "device": {"serial": "Q2AB-1111-AAAA"},
                        "discovered": {"lldp": {"portId": "eth0"}},
                    },
                    {
                        "device": {"serial": "Q2SW-2222-BBBB"},
                        "discovered": {"lldp": {"portId": "1"}},
                    },
                ]
            },
            {
                "ends": [
                    {
                        "device": {"serial": "Q2SW-2222-BBBB"},
                        "discovered": {"cdp": {"portId": "GigabitEthernet1/0/24"}},
                    },
                    {
                        "device": {"serial": "Q2AP-3333-CCCC"},
                        "discovered": {},
                    },
                ]
            },
        ]
    }
]

VLANS_BY_NETWORK = {
    "N_abc123": [
        {
            "id": 1,
            "name": "Management",
            "subnet": "10.0.0.0/24",
            "applianceIp": "10.0.0.1",
            "fixedIpAssignments": {},
        },
        {
            "id": 10,
            "name": "Users",
            "subnet": "10.0.10.0/24",
            "applianceIp": "10.0.10.1",
            "fixedIpAssignments": {"aa:bb:cc:11:22:33": {"ip": "10.0.10.50"}},
        },
        {
            "id": 20,
            "name": "IoT",
            "subnet": "10.0.20.0/24",
            "applianceIp": "10.0.20.1",
            "fixedIpAssignments": {},
        },
    ]
}


# ---------------------------------------------------------------------------
# Device type mapping
# ---------------------------------------------------------------------------


class TestDeviceTypeMapping:
    def test_appliance_maps_to_firewall(self):
        t = MerakiTransformer()
        topo = t.build_l2([APPLIANCE_DEVICE], ALL_STATUSES, [])
        node = next(n for n in topo.nodes if n.id == "Q2AB-1111-AAAA")
        assert node.type == DeviceType.FIREWALL

    def test_switch_maps_to_floor_switch(self):
        t = MerakiTransformer()
        topo = t.build_l2([SWITCH_DEVICE], ALL_STATUSES, [])
        node = next(n for n in topo.nodes if n.id == "Q2SW-2222-BBBB")
        assert node.type == DeviceType.FLOOR_SWITCH

    def test_wireless_maps_to_access_point(self):
        t = MerakiTransformer()
        topo = t.build_l2([AP_DEVICE], ALL_STATUSES, [])
        node = next(n for n in topo.nodes if n.id == "Q2AP-3333-CCCC")
        assert node.type == DeviceType.ACCESS_POINT


# ---------------------------------------------------------------------------
# Status mapping
# ---------------------------------------------------------------------------


class TestStatusMapping:
    def test_online_maps_to_up(self):
        t = MerakiTransformer()
        topo = t.build_l2([APPLIANCE_DEVICE], [{"serial": "Q2AB-1111-AAAA", "status": "online"}], [])
        node = topo.nodes[0]
        assert node.status == DeviceStatus.UP

    def test_offline_maps_to_down(self):
        t = MerakiTransformer()
        topo = t.build_l2([SWITCH_DEVICE], [{"serial": "Q2SW-2222-BBBB", "status": "offline"}], [])
        node = topo.nodes[0]
        assert node.status == DeviceStatus.DOWN

    def test_alerting_maps_to_alerting(self):
        t = MerakiTransformer()
        topo = t.build_l2([AP_DEVICE], [{"serial": "Q2AP-3333-CCCC", "status": "alerting"}], [])
        node = topo.nodes[0]
        assert node.status == DeviceStatus.ALERTING

    def test_dormant_maps_to_down(self):
        t = MerakiTransformer()
        topo = t.build_l2([AP_DEVICE], [{"serial": "Q2AP-3333-CCCC", "status": "dormant"}], [])
        node = topo.nodes[0]
        assert node.status == DeviceStatus.DOWN

    def test_missing_status_defaults_to_down(self):
        """A device with no status entry should default to DOWN."""
        t = MerakiTransformer()
        topo = t.build_l2([APPLIANCE_DEVICE], [], [])
        node = topo.nodes[0]
        assert node.status == DeviceStatus.DOWN


# ---------------------------------------------------------------------------
# Edge creation from link-layer data
# ---------------------------------------------------------------------------


class TestEdgeCreation:
    def test_edges_created_from_link_layer(self):
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, LINK_LAYER_DATA)
        assert len(topo.edges) == 2

    def test_edge_source_and_target(self):
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, LINK_LAYER_DATA)
        serials = {frozenset({e.source, e.target}) for e in topo.edges}
        assert frozenset({"Q2AB-1111-AAAA", "Q2SW-2222-BBBB"}) in serials
        assert frozenset({"Q2SW-2222-BBBB", "Q2AP-3333-CCCC"}) in serials

    def test_lldp_port_ids_captured(self):
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, LINK_LAYER_DATA)
        edge = next(
            e for e in topo.edges
            if frozenset({e.source, e.target}) == frozenset({"Q2AB-1111-AAAA", "Q2SW-2222-BBBB"})
        )
        ports = {edge.source_port, edge.target_port}
        assert "eth0" in ports
        assert "1" in ports

    def test_cdp_port_id_captured_when_no_lldp(self):
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, LINK_LAYER_DATA)
        edge = next(
            e for e in topo.edges
            if frozenset({e.source, e.target}) == frozenset({"Q2SW-2222-BBBB", "Q2AP-3333-CCCC"})
        )
        ports = {edge.source_port, edge.target_port}
        assert "GigabitEthernet1/0/24" in ports

    def test_protocol_is_lldp(self):
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, LINK_LAYER_DATA)
        for edge in topo.edges:
            assert edge.protocol == LinkProtocol.LLDP

    def test_no_edges_when_no_link_layer_data(self):
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, [])
        assert topo.edges == []

    def test_duplicate_links_deduplicated(self):
        """If the API returns the same link twice (mirrored), we emit only one edge."""
        duplicate_link_data = [
            {
                "links": [
                    {
                        "ends": [
                            {"device": {"serial": "Q2AB-1111-AAAA"}, "discovered": {"lldp": {"portId": "eth0"}}},
                            {"device": {"serial": "Q2SW-2222-BBBB"}, "discovered": {"lldp": {"portId": "1"}}},
                        ]
                    },
                    {
                        "ends": [
                            {"device": {"serial": "Q2SW-2222-BBBB"}, "discovered": {"lldp": {"portId": "1"}}},
                            {"device": {"serial": "Q2AB-1111-AAAA"}, "discovered": {"lldp": {"portId": "eth0"}}},
                        ]
                    },
                ]
            }
        ]
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, duplicate_link_data)
        assert len(topo.edges) == 1

    def test_link_missing_serial_skipped(self):
        bad_link_data = [
            {
                "links": [
                    {
                        "ends": [
                            {"device": {}, "discovered": {}},  # no serial
                            {"device": {"serial": "Q2SW-2222-BBBB"}, "discovered": {}},
                        ]
                    }
                ]
            }
        ]
        t = MerakiTransformer()
        topo = t.build_l2(ALL_DEVICES, ALL_STATUSES, bad_link_data)
        assert topo.edges == []


# ---------------------------------------------------------------------------
# VLAN to subnet mapping (L3)
# ---------------------------------------------------------------------------


class TestVlanToSubnet:
    def test_subnets_created_from_vlans(self):
        t = MerakiTransformer()
        l3 = t.build_l3(VLANS_BY_NETWORK, ALL_DEVICES)
        assert len(l3.subnets) == 3

    def test_subnet_fields(self):
        t = MerakiTransformer()
        l3 = t.build_l3(VLANS_BY_NETWORK, ALL_DEVICES)
        mgmt = next(s for s in l3.subnets if s.vlan == 1)
        assert mgmt.id == "vlan-1"
        assert mgmt.name == "Management"
        assert mgmt.cidr == "10.0.0.0/24"
        assert mgmt.gateway == "10.0.0.1"

    def test_device_count_from_fixed_ip_assignments(self):
        t = MerakiTransformer()
        l3 = t.build_l3(VLANS_BY_NETWORK, ALL_DEVICES)
        users = next(s for s in l3.subnets if s.vlan == 10)
        assert users.device_count == 1

    def test_inter_vlan_routes_created(self):
        t = MerakiTransformer()
        l3 = t.build_l3(VLANS_BY_NETWORK, ALL_DEVICES)
        # 3 subnets → 3 choose 2 = 3 routes
        assert len(l3.routes) == 3

    def test_routes_via_appliance(self):
        t = MerakiTransformer()
        l3 = t.build_l3(VLANS_BY_NETWORK, ALL_DEVICES)
        for route in l3.routes:
            assert route.via == "Q2AB-1111-AAAA"

    def test_no_routes_when_single_vlan(self):
        single_vlan = {
            "N_abc123": [
                {"id": 1, "name": "Management", "subnet": "10.0.0.0/24", "applianceIp": "10.0.0.1"}
            ]
        }
        t = MerakiTransformer()
        l3 = t.build_l3(single_vlan, ALL_DEVICES)
        assert l3.routes == []

    def test_no_routes_when_no_appliance(self):
        non_appliance_devices = [SWITCH_DEVICE, AP_DEVICE]
        t = MerakiTransformer()
        l3 = t.build_l3(VLANS_BY_NETWORK, non_appliance_devices)
        assert l3.routes == []

    def test_empty_vlans_yields_empty_topology(self):
        t = MerakiTransformer()
        l3 = t.build_l3({}, ALL_DEVICES)
        assert l3.subnets == []
        assert l3.routes == []
