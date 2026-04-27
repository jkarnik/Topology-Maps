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
