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


def test_template_scores(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    # Create template from net1
    tmpl = client.post("/api/config/templates", json={"org_id": "org1", "name": "T1", "network_id": "net1"}).json()
    resp = client.get(f"/api/config/templates/{tmpl['id']}/scores?org_id=org1")
    assert resp.status_code == 200
    scores = {s["network_id"]: s for s in resp.json()["scores"]}
    assert scores["net1"]["score_pct"] == 100
    assert scores["net2"]["score_pct"] < 100
