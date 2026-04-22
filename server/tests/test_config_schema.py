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


def test_config_change_events_table_exists(fresh_db):
    """config_change_events table has expected columns and unique dedup index."""
    assert _table_exists(fresh_db, "config_change_events")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_change_events)")}
    expected = {
        "id", "org_id", "ts", "admin_id", "admin_name", "admin_email",
        "network_id", "network_name", "ssid_number", "ssid_name",
        "page", "label", "old_value", "new_value",
        "client_id", "client_description",
        "raw_json", "fetched_at",
    }
    assert set(cols.keys()) == expected
    assert cols["id"]["pk"] == 1
    assert cols["org_id"]["notnull"] == 1
    assert cols["ts"]["notnull"] == 1
    assert cols["raw_json"]["notnull"] == 1
    assert cols["fetched_at"]["notnull"] == 1


def test_config_change_events_dedup_unique_constraint(fresh_db):
    """Inserting the same (org_id, ts, network_id, label, old_value, new_value) twice fails."""
    insert_sql = """
        INSERT INTO config_change_events
          (org_id, ts, network_id, label, old_value, new_value, raw_json, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    args = ("org1", "2026-04-22T10:00:00Z", "N_1", "VLAN", "10", "20", "{}", "2026-04-22T10:01:00Z")
    fresh_db.execute(insert_sql, args)
    fresh_db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        fresh_db.execute(insert_sql, args)
        fresh_db.commit()


def test_config_sweep_runs_table_exists(fresh_db):
    """config_sweep_runs table has expected columns and defaults."""
    assert _table_exists(fresh_db, "config_sweep_runs")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_sweep_runs)")}
    expected = {
        "id", "org_id", "kind", "status",
        "started_at", "completed_at",
        "total_calls", "completed_calls", "failed_calls", "skipped_calls",
        "error_summary",
    }
    assert set(cols.keys()) == expected
    assert cols["id"]["pk"] == 1
    assert cols["org_id"]["notnull"] == 1
    assert cols["kind"]["notnull"] == 1
    assert cols["status"]["notnull"] == 1


def test_config_sweep_runs_counter_defaults(fresh_db):
    """Inserting with only required fields leaves counters at 0."""
    fresh_db.execute(
        "INSERT INTO config_sweep_runs (org_id, kind, status) VALUES (?, ?, ?)",
        ("org1", "baseline", "queued"),
    )
    fresh_db.commit()
    row = fresh_db.execute(
        "SELECT completed_calls, failed_calls, skipped_calls FROM config_sweep_runs"
    ).fetchone()
    assert row["completed_calls"] == 0
    assert row["failed_calls"] == 0
    assert row["skipped_calls"] == 0
