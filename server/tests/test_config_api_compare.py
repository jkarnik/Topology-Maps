"""Tests for Phase 6 compare/coverage/template API endpoints."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server import database
from server.config_collector import store


@pytest.fixture
def app(monkeypatch, tmp_path):
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.get_connection().close()
    from fastapi import FastAPI
    from server.routes import config as config_routes
    import importlib
    importlib.reload(config_routes)
    app = FastAPI()
    app.include_router(config_routes.router)
    yield app


@pytest.fixture
def client(app):
    return TestClient(app)


def _seed(monkeypatch, tmp_path):
    """Returns a seeded (conn, h1, h2) tuple for use in tests."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    payload_a = json.dumps({"ssid": 1})
    payload_b = json.dumps({"ssid": 2})
    import hashlib
    h1 = hashlib.sha256(payload_a.encode()).hexdigest()
    h2 = hashlib.sha256(payload_b.encode()).hexdigest()
    store.upsert_blob(conn, h1, payload_a, len(payload_a))
    store.upsert_blob(conn, h2, payload_b, len(payload_b))
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net1", config_area="wireless_ssids", sub_key=None, hash_hex=h1,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={"name_hint": "Store 7"})
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net2", config_area="wireless_ssids", sub_key=None, hash_hex=h2,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={"name_hint": "Store 42"})
    conn.close()
    return h1, h2


def test_list_templates_empty(client):
    resp = client.get("/api/config/templates?org_id=org1")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_delete_template(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    resp = client.post("/api/config/templates", json={"org_id": "org1", "name": "Standard Retail", "network_id": "net1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Standard Retail"
    assert len(body["areas"]) == 1
    tmpl_id = body["id"]

    resp = client.get("/api/config/templates?org_id=org1")
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/config/templates/{tmpl_id}")
    assert resp.status_code == 200
    assert client.get("/api/config/templates?org_id=org1").json() == []


def test_compare_networks(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    resp = client.get("/api/config/compare/networks?org_id=org1&network_a=net1&network_b=net2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["differing_areas"] == 1
    assert body["areas"][0]["status"] == "differs"


def test_coverage(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    resp = client.get("/api/config/coverage?org_id=org1")
    assert resp.status_code == 200
    areas = resp.json()["areas"]
    assert len(areas) == 1
    assert areas[0]["config_area"] == "wireless_ssids"
    assert areas[0]["network_count"] == 2


def test_compare_networks_mixed_sub_keys(client, monkeypatch, tmp_path):
    """Regression: sorting fails when same config_area has sub_key=None in one network
    and a non-null sub_key in the other."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib
    p = '{"x": 1}'
    h = hashlib.sha256(p.encode()).hexdigest()
    store.upsert_blob(conn, h, p, len(p))
    # net1: appliance_vlans with sub_key=None
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net1", config_area="appliance_vlans", sub_key=None, hash_hex=h,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={})
    # net2: appliance_vlans with a non-null sub_key
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net2", config_area="appliance_vlans", sub_key="10", hash_hex=h,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={})
    conn.close()

    resp = client.get("/api/config/compare/networks?org_id=org1&network_a=net1&network_b=net2")
    assert resp.status_code == 200


def test_compare_networks_blob_with_string_list(client, monkeypatch, tmp_path):
    """Regression: compute_diff crashes when a blob has a top-level list of strings.
    is_array detection must require list-of-dicts, not any list."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib
    # Blob whose top-level value is a list of strings (e.g. Meraki tags)
    payload_a = json.dumps({"tags": ["tag1", "tag2"], "name": "net1"})
    payload_b = json.dumps({"tags": ["tag1", "tag3"], "name": "net1"})
    h1 = hashlib.sha256(payload_a.encode()).hexdigest()
    h2 = hashlib.sha256(payload_b.encode()).hexdigest()
    store.upsert_blob(conn, h1, payload_a, len(payload_a))
    store.upsert_blob(conn, h2, payload_b, len(payload_b))
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net1", config_area="network_settings", sub_key=None, hash_hex=h1,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={})
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net2", config_area="network_settings", sub_key=None, hash_hex=h2,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={})
    conn.close()

    resp = client.get("/api/config/compare/networks?org_id=org1&network_a=net1&network_b=net2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["areas"][0]["status"] == "differs"


def test_template_scores(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    # Create template from net1
    tmpl = client.post("/api/config/templates", json={"org_id": "org1", "name": "T1", "network_id": "net1"}).json()
    resp = client.get(f"/api/config/templates/{tmpl['id']}/scores?org_id=org1")
    assert resp.status_code == 200
    scores = {s["network_id"]: s for s in resp.json()["scores"]}
    assert scores["net1"]["score_pct"] == 100
    assert scores["net2"]["score_pct"] < 100


def test_devices_for_template_no_meraki(client, monkeypatch, tmp_path):
    """With Meraki unconfigured, falls back to all org devices of matching kind."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib, json as j
    payload = j.dumps({"ports": []})
    h = hashlib.sha256(payload.encode()).hexdigest()
    store.upsert_blob(conn, h, payload, len(payload))
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-0001",
        config_area="switch_device_ports", sub_key=None, hash_hex=h,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Core-SW-01"},
    )
    conn.close()

    resp = client.get("/api/config/devices-for-template?org_id=org1&network_id=net1&kind=switch")
    assert resp.status_code == 200
    data = resp.json()
    serials = [d["serial"] for d in data["devices"]]
    assert "Q2SW-0001" in serials
    assert data["network_filter_unavailable"] is True


def test_create_device_template_via_api(client, monkeypatch, tmp_path):
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib, json as j
    payload = j.dumps({"ports": [{"id": 1}]})
    h = hashlib.sha256(payload.encode()).hexdigest()
    store.upsert_blob(conn, h, payload, len(payload))
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-0001",
        config_area="switch_device_ports", sub_key=None, hash_hex=h,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Core-SW-01"},
    )
    conn.close()

    resp = client.post("/api/config/templates", json={
        "org_id": "org1",
        "name": "Standard Switch",
        "network_id": "net1",
        "kind": "switch",
        "device_serial": "Q2SW-0001",
        "device_name": "Core-SW-01",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_device_serial"] == "Q2SW-0001"
    assert data["source_device_name"] == "Core-SW-01"
    assert any(a["config_area"] == "switch_device_ports" for a in data["areas"])


def test_device_template_scores(client, monkeypatch, tmp_path):
    """Device template scores return networks-keyed response with per-device scores."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    import hashlib, json as j

    payload_gold = j.dumps({"portId": "1", "enabled": True})
    payload_drift = j.dumps({"portId": "1", "enabled": False})
    h_gold = hashlib.sha256(payload_gold.encode()).hexdigest()
    h_drift = hashlib.sha256(payload_drift.encode()).hexdigest()
    store.upsert_blob(conn, h_gold, payload_gold, len(payload_gold))
    store.upsert_blob(conn, h_drift, payload_drift, len(payload_drift))

    # Golden device
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-GOLD",
        config_area="switch_device_ports", sub_key=None, hash_hex=h_gold,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Golden-SW"},
    )
    # Another device that drifted
    store.insert_observation_if_changed(
        conn, org_id="org1", entity_type="device", entity_id="Q2SW-DRIFT",
        config_area="switch_device_ports", sub_key=None, hash_hex=h_drift,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": "Drift-SW"},
    )
    conn.close()

    # Create device template
    resp = client.post("/api/config/templates", json={
        "org_id": "org1", "name": "Golden Switch", "network_id": "net1",
        "kind": "switch", "device_serial": "Q2SW-GOLD", "device_name": "Golden-SW",
    })
    tmpl_id = resp.json()["id"]

    # Get scores
    resp = client.get(f"/api/config/templates/{tmpl_id}/scores?org_id=org1")
    assert resp.status_code == 200
    data = resp.json()

    assert "networks" in data
    assert "scores" not in data

    # Unknown-network bucket holds both devices (no Meraki configured)
    all_devices = [d for n in data["networks"] for d in n["devices"]]
    serials = [d["serial"] for d in all_devices]
    assert "Q2SW-GOLD" in serials
    assert "Q2SW-DRIFT" in serials

    gold = next(d for d in all_devices if d["serial"] == "Q2SW-GOLD")
    drift = next(d for d in all_devices if d["serial"] == "Q2SW-DRIFT")
    assert gold["score_pct"] == 100
    assert drift["score_pct"] < 100
