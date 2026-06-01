"""Tests for Phase 6 template store functions."""
from __future__ import annotations
import tempfile
from pathlib import Path
import pytest
from server import database
from server.config_collector import store


@pytest.fixture
def conn(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    c = database.get_connection()
    yield c
    c.close()


def _seed_blob(conn, payload: str = '{"ssid": 1}') -> str:
    import hashlib
    h = hashlib.sha256(payload.encode()).hexdigest()
    store.upsert_blob(conn, h, payload, len(payload))
    return h


def _seed_observation(conn, org_id, network_id, config_area, blob_hash):
    store.insert_observation_if_changed(
        conn,
        org_id=org_id,
        entity_type="network",
        entity_id=network_id,
        config_area=config_area,
        sub_key=None,
        hash_hex=blob_hash,
        source_event="baseline",
        change_event_id=None,
        sweep_run_id=None,
        hot_columns={},
    )


def test_create_and_list_template(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)

    tmpl = store.create_template(conn, org_id="org1", name="Standard Retail", network_id="net1", network_name="Store 7")
    assert tmpl["id"] > 0
    assert tmpl["name"] == "Standard Retail"
    assert tmpl["source_network_id"] == "net1"
    assert len(tmpl["areas"]) == 1
    assert tmpl["areas"][0]["config_area"] == "wireless_ssids"
    assert tmpl["areas"][0]["blob_hash"] == h

    templates = store.list_templates(conn, org_id="org1")
    assert len(templates) == 1
    assert templates[0]["id"] == tmpl["id"]


def test_delete_template(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)
    tmpl = store.create_template(conn, org_id="org1", name="T1", network_id="net1", network_name="Store 7")
    store.delete_template(conn, template_id=tmpl["id"])
    assert store.list_templates(conn, org_id="org1") == []
    areas = conn.execute("SELECT * FROM config_template_areas WHERE template_id=?", (tmpl["id"],)).fetchall()
    assert list(areas) == []


def test_get_template_areas(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)
    tmpl = store.create_template(conn, org_id="org1", name="T1", network_id="net1", network_name="Store 7")
    areas = store.get_template_areas(conn, template_id=tmpl["id"])
    assert len(areas) == 1
    assert areas[0]["blob_hash"] == h


def test_delete_nonexistent_template_is_noop(conn):
    store.delete_template(conn, template_id=9999)


def test_get_coverage(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)
    _seed_observation(conn, "org1", "net2", "wireless_ssids", h)
    _seed_observation(conn, "org1", "net1", "appliance_vlans", h)

    coverage = store.get_coverage(conn, org_id="org1")
    areas = {a["config_area"]: a for a in coverage}

    assert areas["wireless_ssids"]["network_count"] == 2
    assert areas["wireless_ssids"]["network_total"] == 2
    assert areas["wireless_ssids"]["missing_networks"] == []

    assert areas["appliance_vlans"]["network_count"] == 1
    assert areas["appliance_vlans"]["network_total"] == 2
    assert len(areas["appliance_vlans"]["missing_networks"]) == 1
    assert areas["appliance_vlans"]["missing_networks"][0]["id"] == "net2"


def _seed_device_observation(conn, org_id, serial, config_area, blob_hash, name=None):
    store.insert_observation_if_changed(
        conn,
        org_id=org_id,
        entity_type="device",
        entity_id=serial,
        config_area=config_area,
        sub_key=None,
        hash_hex=blob_hash,
        source_event="baseline",
        change_event_id=None,
        sweep_run_id=None,
        hot_columns={"name_hint": name} if name else {},
    )


def test_create_device_template(conn):
    h = _seed_blob(conn, '{"ports": [{"id": 1}]}')
    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h, name="Core-SW-01")

    tmpl = store.create_template(
        conn,
        org_id="org1",
        name="Standard Core Switch",
        network_id="net1",
        network_name=None,
        kind="switch",
        device_serial="Q2SW-0001",
        device_name="Core-SW-01",
    )

    assert tmpl["source_device_serial"] == "Q2SW-0001"
    assert tmpl["source_device_name"] == "Core-SW-01"
    assert len(tmpl["areas"]) == 1
    assert tmpl["areas"][0]["config_area"] == "switch_device_ports"


def test_device_template_excludes_network_areas(conn):
    h_net = _seed_blob(conn, '{"ssids": []}')
    h_dev = _seed_blob(conn, '{"ports": []}')
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h_net)
    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h_dev)

    tmpl = store.create_template(
        conn,
        org_id="org1",
        name="Switch Template",
        network_id="net1",
        network_name="Store 1",
        kind="switch",
        device_serial="Q2SW-0001",
        device_name="Core-SW-01",
    )

    area_names = [a["config_area"] for a in tmpl["areas"]]
    assert "switch_device_ports" in area_names
    assert "wireless_ssids" not in area_names


def test_list_devices_for_kind(conn):
    h = _seed_blob(conn)
    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h, name="Core-SW-01")
    _seed_device_observation(conn, "org1", "Q2SW-0002", "switch_device_ports", h, name="Floor-SW-02")
    # AP device — should NOT appear for switch kind
    _seed_device_observation(conn, "org1", "Q2MR-0001", "wireless_device_radio_settings", h, name="AP-01")

    devices = store.list_devices_for_kind(
        conn,
        org_id="org1",
        serials=["Q2SW-0001", "Q2SW-0002", "Q2MR-0001"],
        kind="switch",
    )

    serials = [d["serial"] for d in devices]
    assert "Q2SW-0001" in serials
    assert "Q2SW-0002" in serials
    assert "Q2MR-0001" not in serials


def test_list_devices_for_kind_empty_serials(conn):
    devices = store.list_devices_for_kind(conn, org_id="org1", serials=[], kind="switch")
    assert devices == []


def test_create_device_template_excludes_device_metadata(conn):
    """device_metadata must never appear in template areas."""
    h_ports = _seed_blob(conn, '{"portId": "1", "vlan": 10}')
    h_meta = _seed_blob(conn, '{"serial": "Q2SW-0001", "name": "Core-SW"}')

    _seed_device_observation(conn, "org1", "Q2SW-0001", "switch_device_ports", h_ports)
    _seed_device_observation(conn, "org1", "Q2SW-0001", "device_metadata", h_meta)

    tmpl = store.create_template(
        conn,
        org_id="org1",
        name="No Metadata Template",
        network_id="net1",
        network_name=None,
        kind="switch",
        device_serial="Q2SW-0001",
        device_name="Core-SW",
    )

    area_names = [a["config_area"] for a in tmpl["areas"]]
    assert "device_metadata" not in area_names
    assert "switch_device_ports" in area_names
