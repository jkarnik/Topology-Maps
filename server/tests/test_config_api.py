"""Tests for config REST API (Plan 1.17)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch):
    """Build a minimal FastAPI app with the config router mounted."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        database.get_connection().close()

        from fastapi import FastAPI
        from server.routes import config as config_routes
        app = FastAPI()
        app.include_router(config_routes.router)
        yield app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_orgs_empty(client):
    resp = client.get("/api/config/orgs")
    assert resp.status_code == 200
    assert resp.json() == []


from unittest.mock import AsyncMock, patch


def test_status_empty_org(client):
    resp = client.get("/api/config/orgs/o1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["baseline_state"] == "none"
    assert body["active_sweep"] is None


def test_baseline_trigger_returns_run_id(client):
    with patch("server.routes.config._get_meraki_client") as gc, \
         patch("server.routes.config.run_baseline", new=AsyncMock(return_value=42)):
        gc.return_value = object()
        resp = client.post("/api/config/orgs/o1/baseline")
    assert resp.status_code == 200
    assert resp.json()["sweep_run_id"] == 42


def test_sweep_trigger_returns_run_id(client):
    with patch("server.routes.config._get_meraki_client") as gc, \
         patch("server.routes.config.run_anti_drift_sweep", new=AsyncMock(return_value=99)):
        gc.return_value = object()
        resp = client.post("/api/config/orgs/o1/sweep")
    assert resp.status_code == 200
    assert resp.json()["sweep_run_id"] == 99


def test_refresh_trigger_validates_entity_type(client):
    resp = client.post("/api/config/orgs/o1/refresh", json={
        "entity_type": "bogus", "entity_id": "x",
    })
    assert resp.status_code == 400


def test_get_entity_returns_404_if_missing(client):
    resp = client.get("/api/config/entities/network/N_MISSING?org_id=o1")
    assert resp.status_code == 404


def test_get_blob_returns_404_if_missing(client):
    resp = client.get("/api/config/blobs/does-not-exist")
    assert resp.status_code == 404


def test_list_change_events_empty(client):
    resp = client.get("/api/config/change-events?org_id=o1")
    assert resp.status_code == 200
    assert resp.json() == {"events": [], "has_more": False, "next_cursor": None}
