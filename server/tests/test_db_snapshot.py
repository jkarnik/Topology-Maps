"""Tests for db.py schema and migration."""
from __future__ import annotations

import pytest


@pytest.fixture
def patched_db(monkeypatch, tmp_path):
    """Fresh isolated db.py pointing at a temp file."""
    import server.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(db_mod, "_connection", None)
    db_mod.init_db()
    yield db_mod
    db_mod.close_db()
    monkeypatch.setattr(db_mod, "_connection", None)


def test_orgs_table_exists(patched_db):
    conn = patched_db._conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "orgs" in tables


def test_networks_has_org_id_column(patched_db):
    conn = patched_db._conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(networks)").fetchall()}
    assert "org_id" in cols


def test_schema_version_is_3(patched_db):
    assert patched_db.meta_get("schema_version") == "3"


def test_save_snapshot_upserts_org(patched_db):
    patched_db.save_snapshot({
        "version": 3,
        "orgId": "537758",
        "orgName": "New Relic",
        "networks": [{"id": "N_1", "name": "London", "productTypes": ["switch"]}],
        "selectedNetwork": None,
        "topology": {},
        "lastUpdated": None,
    })
    row = patched_db._conn().execute(
        "SELECT id, name FROM orgs WHERE id = '537758'"
    ).fetchone()
    assert row is not None
    assert row[1] == "New Relic"


def test_save_snapshot_sets_org_id_on_networks(patched_db):
    patched_db.save_snapshot({
        "version": 3,
        "orgId": "537758",
        "orgName": "New Relic",
        "networks": [{"id": "N_1", "name": "London", "productTypes": ["switch"]}],
        "selectedNetwork": None,
        "topology": {},
        "lastUpdated": None,
    })
    row = patched_db._conn().execute(
        "SELECT org_id FROM networks WHERE id = 'N_1'"
    ).fetchone()
    assert row[0] == "537758"


def test_load_snapshot_returns_org_id(patched_db):
    patched_db.save_snapshot({
        "version": 3,
        "orgId": "537758",
        "orgName": "New Relic",
        "networks": [{"id": "N_1", "name": "London", "productTypes": ["switch"]}],
        "selectedNetwork": None,
        "topology": {
            "N_1": {
                "l2": {"nodes": [], "edges": []},
                "l3": {"subnets": [], "routes": []},
                "deviceDetails": {},
            }
        },
        "lastUpdated": None,
    })
    result = patched_db.load_snapshot()
    assert result is not None
    assert result["orgId"] == "537758"


def test_save_snapshot_without_org_id_still_works(patched_db):
    """Backwards compatibility: callers that omit orgId must not break."""
    patched_db.save_snapshot({
        "version": 2,
        "orgName": "New Relic",
        "networks": [{"id": "N_2", "name": "Paris", "productTypes": []}],
        "selectedNetwork": None,
        "topology": {
            "N_2": {
                "l2": {"nodes": [], "edges": []},
                "l3": {"subnets": [], "routes": []},
                "deviceDetails": {},
            }
        },
        "lastUpdated": None,
    })
    result = patched_db.load_snapshot()
    assert result is not None
    assert result.get("orgId") is None
