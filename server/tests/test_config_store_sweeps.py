"""Tests for config_sweep_runs data access (Plan 1.11)."""
from __future__ import annotations

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
        yield c
        c.close()


def test_create_sweep_run_returns_id(conn):
    from server.config_collector.store import create_sweep_run

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=100)
    assert isinstance(run_id, int)
    row = conn.execute("SELECT * FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "queued"
    assert row["total_calls"] == 100


def test_mark_sweep_running_sets_timestamp(conn):
    from server.config_collector.store import create_sweep_run, mark_sweep_running

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=10)
    mark_sweep_running(conn, run_id)

    row = conn.execute("SELECT status, started_at FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "running"
    assert row["started_at"] is not None


def test_increment_sweep_counters(conn):
    from server.config_collector.store import create_sweep_run, increment_sweep_counters

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=10)
    increment_sweep_counters(conn, run_id, completed=3, failed=1, skipped=2)
    increment_sweep_counters(conn, run_id, completed=2, failed=0, skipped=1)

    row = conn.execute("SELECT completed_calls, failed_calls, skipped_calls FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["completed_calls"] == 5
    assert row["failed_calls"] == 1
    assert row["skipped_calls"] == 3


def test_mark_sweep_complete(conn):
    from server.config_collector.store import create_sweep_run, mark_sweep_complete

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=10)
    mark_sweep_complete(conn, run_id)
    row = conn.execute("SELECT status, completed_at FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "complete"
    assert row["completed_at"] is not None


def test_mark_sweep_failed_stores_error_summary(conn):
    from server.config_collector.store import create_sweep_run, mark_sweep_failed

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=10)
    mark_sweep_failed(conn, run_id, error_summary="rate limit exhausted")
    row = conn.execute("SELECT status, error_summary FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "failed"
    assert row["error_summary"] == "rate limit exhausted"


def test_list_completed_entity_areas_for_sweep(conn):
    from server.config_collector.store import (
        create_sweep_run, insert_observation_if_changed,
        list_completed_entity_areas,
    )

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=100)

    conn.execute("INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
                 ("h1", "{}", 2, "t"))
    conn.commit()

    insert_observation_if_changed(
        conn, org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None, hash_hex="h1",
        source_event="baseline", change_event_id=None, sweep_run_id=run_id,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    insert_observation_if_changed(
        conn, org_id="o1", entity_type="device", entity_id="Q2-A",
        config_area="switch_device_ports", sub_key=None, hash_hex="h1",
        source_event="baseline", change_event_id=None, sweep_run_id=run_id,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    done = list_completed_entity_areas(conn, sweep_run_id=run_id)
    assert ("network", "N_1", "appliance_vlans", None) in done
    assert ("device", "Q2-A", "switch_device_ports", None) in done
    assert len(done) == 2


def test_get_active_sweep_run_returns_queued_or_running(conn):
    from server.config_collector.store import create_sweep_run, mark_sweep_running, mark_sweep_complete, get_active_sweep_run

    assert get_active_sweep_run(conn, org_id="o1", kind="baseline") is None

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=10)
    active = get_active_sweep_run(conn, org_id="o1", kind="baseline")
    assert active["id"] == run_id

    mark_sweep_running(conn, run_id)
    active = get_active_sweep_run(conn, org_id="o1", kind="baseline")
    assert active["id"] == run_id
    assert active["status"] == "running"

    mark_sweep_complete(conn, run_id)
    assert get_active_sweep_run(conn, org_id="o1", kind="baseline") is None
