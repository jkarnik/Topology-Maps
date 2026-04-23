"""Tests for config_observations data access (Plan 1.10)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        # Seed blobs so FK is satisfied
        c.execute(
            "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
            ("hash1", "{}", 2, "2026-04-22T00:00:00Z"),
        )
        c.execute(
            "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
            ("hash2", '{"a":1}', 7, "2026-04-22T00:00:00Z"),
        )
        c.commit()
        yield c
        c.close()


def test_insert_observation_first_time_writes_row(conn):
    from server.config_collector.store import insert_observation_if_changed

    wrote = insert_observation_if_changed(
        conn,
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None, hash_hex="hash1",
        source_event="baseline", change_event_id=None, sweep_run_id=1,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    assert wrote is True
    rows = conn.execute("SELECT * FROM config_observations").fetchall()
    assert len(rows) == 1


def test_insert_observation_same_hash_skipped(conn):
    from server.config_collector.store import insert_observation_if_changed

    kwargs = dict(
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None, hash_hex="hash1",
        source_event="baseline", change_event_id=None, sweep_run_id=1,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    insert_observation_if_changed(conn, **kwargs)
    wrote = insert_observation_if_changed(conn, **kwargs)
    assert wrote is False
    rows = conn.execute("SELECT * FROM config_observations").fetchall()
    assert len(rows) == 1


def test_insert_observation_different_hash_writes_new(conn):
    from server.config_collector.store import insert_observation_if_changed

    kwargs = dict(
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None,
        source_event="change_log", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    insert_observation_if_changed(conn, hash_hex="hash1", **kwargs)
    wrote = insert_observation_if_changed(conn, hash_hex="hash2", **kwargs)
    assert wrote is True

    rows = conn.execute("SELECT hash FROM config_observations ORDER BY id").fetchall()
    assert [r["hash"] for r in rows] == ["hash1", "hash2"]


def test_anti_drift_confirm_always_writes(conn):
    """For anti_drift_confirm, write even if hash matches — proof-of-life."""
    from server.config_collector.store import insert_observation_if_changed

    kwargs = dict(
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None, hash_hex="hash1",
        change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    insert_observation_if_changed(conn, source_event="baseline", **kwargs)
    wrote = insert_observation_if_changed(conn, source_event="anti_drift_confirm", **kwargs)
    assert wrote is True

    rows = conn.execute("SELECT source_event FROM config_observations ORDER BY id").fetchall()
    assert [r["source_event"] for r in rows] == ["baseline", "anti_drift_confirm"]


def test_get_latest_observation_returns_most_recent(conn):
    from server.config_collector.store import insert_observation_if_changed, get_latest_observation

    base = dict(
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None,
        change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    insert_observation_if_changed(conn, hash_hex="hash1", source_event="baseline", **base)
    insert_observation_if_changed(conn, hash_hex="hash2", source_event="change_log", **base)

    latest = get_latest_observation(
        conn,
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None,
    )
    assert latest["hash"] == "hash2"
    assert latest["source_event"] == "change_log"


def test_get_latest_observation_missing_returns_none(conn):
    from server.config_collector.store import get_latest_observation

    assert get_latest_observation(
        conn, org_id="x", entity_type="network", entity_id="Y",
        config_area="z", sub_key=None,
    ) is None
