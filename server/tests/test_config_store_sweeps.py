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
