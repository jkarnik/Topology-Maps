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
