"""Tests for config-collection schema migration (Plan 1.01)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Fresh SQLite DB for a single test; auto-cleaned."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        # Patch DB_PATH so get_connection() uses the temp DB
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        conn = database.get_connection()
        yield conn
        conn.close()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def test_scaffolding_loads():
    """Sanity check: test file imports and helpers resolve."""
    assert _table_exists is not None
    assert _index_exists is not None


def test_config_blobs_table_exists(fresh_db):
    """config_blobs table is created with the expected columns."""
    assert _table_exists(fresh_db, "config_blobs")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_blobs)")}
    assert set(cols.keys()) == {"hash", "payload", "byte_size", "first_seen_at"}
    assert cols["hash"]["pk"] == 1                  # hash is PRIMARY KEY
    assert cols["hash"]["notnull"] == 0             # PK implies NOT NULL; PRAGMA reports 0 for text PK
    assert cols["payload"]["notnull"] == 1
    assert cols["byte_size"]["notnull"] == 1
    assert cols["first_seen_at"]["notnull"] == 1
    assert cols["byte_size"]["type"].upper() == "INTEGER"


def test_config_observations_table_exists(fresh_db):
    """config_observations table has expected columns, types, and FKs."""
    assert _table_exists(fresh_db, "config_observations")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_observations)")}
    expected = {
        "id", "org_id", "entity_type", "entity_id", "config_area", "sub_key",
        "hash", "observed_at", "source_event", "change_event_id", "sweep_run_id",
        "name_hint", "enabled_hint",
    }
    assert set(cols.keys()) == expected

    # Primary key is auto-incrementing id
    assert cols["id"]["pk"] == 1
    assert cols["id"]["type"].upper() == "INTEGER"

    # Required fields
    for required in ("org_id", "entity_type", "entity_id", "config_area", "hash", "observed_at", "source_event"):
        assert cols[required]["notnull"] == 1, f"{required} must be NOT NULL"

    # Optional fields
    for optional in ("sub_key", "change_event_id", "sweep_run_id", "name_hint", "enabled_hint"):
        assert cols[optional]["notnull"] == 0, f"{optional} must be nullable"
