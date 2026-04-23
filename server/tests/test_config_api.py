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
