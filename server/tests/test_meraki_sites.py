"""Tests for MerakiTransformer.build_sites — world map landing aggregation."""

import pytest

from server.meraki_transformer import MerakiTransformer
from server.models import HealthBucket


@pytest.fixture
def transformer():
    return MerakiTransformer()


NETWORKS = [
    {"id": "N_1", "name": "Dallas DC"},
    {"id": "N_2", "name": "Warehouse B"},
]


def test_resolves_location_from_first_device_with_coords(transformer):
    devices = [
        {"serial": "S1", "networkId": "N_1", "lat": None, "lng": None},
        {"serial": "S2", "networkId": "N_1", "lat": 32.78, "lng": -96.80},
    ]
    sites = transformer.build_sites(NETWORKS, devices, [])
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.mapped is True
    assert dallas.lat == 32.78
    assert dallas.lng == -96.80


def test_network_with_no_coords_is_unmapped(transformer):
    devices = [{"serial": "S1", "networkId": "N_2", "lat": None, "lng": None}]
    sites = transformer.build_sites(NETWORKS, devices, [])
    warehouse = next(s for s in sites if s.network_id == "N_2")
    assert warehouse.mapped is False
    assert warehouse.lat is None
    assert warehouse.lng is None


def test_device_count_includes_all_statuses(transformer):
    devices = [
        {"serial": "S1", "networkId": "N_1", "lat": 1.0, "lng": 2.0},
        {"serial": "S2", "networkId": "N_1", "lat": None, "lng": None},
        {"serial": "S3", "networkId": "N_1", "lat": None, "lng": None},
    ]
    sites = transformer.build_sites(NETWORKS, devices, [])
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.device_count == 3


@pytest.mark.parametrize(
    "statuses,expected_bucket,expected_pct",
    [
        (["online", "online", "online", "online"], HealthBucket.GREEN, 0.0),
        (["online", "online", "online", "alerting"], HealthBucket.YELLOW, 0.25),
        (["online", "online", "alerting", "offline"], HealthBucket.ORANGE, 0.5),
        (["offline", "offline", "offline", "online"], HealthBucket.RED, 0.75),
    ],
)
def test_health_bucket_thresholds(transformer, statuses, expected_bucket, expected_pct):
    devices = [
        {"serial": f"S{i}", "networkId": "N_1", "lat": None, "lng": None}
        for i in range(len(statuses))
    ]
    availabilities = [
        {"serial": f"S{i}", "status": status} for i, status in enumerate(statuses)
    ]
    sites = transformer.build_sites(NETWORKS, devices, availabilities)
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.health_bucket == expected_bucket
    assert dallas.unhealthy_pct == pytest.approx(expected_pct)


def test_dormant_devices_excluded_from_denominator(transformer):
    devices = [
        {"serial": "S1", "networkId": "N_1", "lat": None, "lng": None},
        {"serial": "S2", "networkId": "N_1", "lat": None, "lng": None},
    ]
    availabilities = [
        {"serial": "S1", "status": "online"},
        {"serial": "S2", "status": "dormant"},
    ]
    sites = transformer.build_sites(NETWORKS, devices, availabilities)
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.unhealthy_pct == 0.0
    assert dallas.health_bucket == HealthBucket.GREEN


def test_no_availability_data_is_unknown_not_green(transformer):
    devices = [{"serial": "S1", "networkId": "N_1", "lat": None, "lng": None}]
    sites = transformer.build_sites(NETWORKS, devices, [])
    dallas = next(s for s in sites if s.network_id == "N_1")
    assert dallas.health_bucket == HealthBucket.UNKNOWN
    assert dallas.unhealthy_pct is None


def test_network_with_zero_devices(transformer):
    sites = transformer.build_sites(NETWORKS, [], [])
    warehouse = next(s for s in sites if s.network_id == "N_2")
    assert warehouse.device_count == 0
    assert warehouse.mapped is False
    assert warehouse.health_bucket == HealthBucket.UNKNOWN


def test_empty_networks_returns_empty_list(transformer):
    assert transformer.build_sites([], [{"serial": "S1", "networkId": "N_1"}], []) == []
