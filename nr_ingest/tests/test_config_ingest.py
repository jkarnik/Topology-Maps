from __future__ import annotations
import sqlite3
import subprocess
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_data_source import load_config_db
import config_data_source as _cds
from config_ingest import build_snapshot_events
from config_ingest import build_change_events, _compute_change_summary
import json


def test_load_config_db_local_fallback(tmp_path, monkeypatch):
    db_path = tmp_path / "topology.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE config_observations (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: type("R", (), {"returncode": 1})())
    monkeypatch.setattr(_cds, "_LOCAL_TOPOLOGY_DB", db_path)

    conn = load_config_db()
    assert conn is not None
    conn.close()


def test_build_snapshot_events_basic(test_db):
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("abc123", '{"mode":"access"}', 14, "2026-01-01T00:00:00"))
    test_db.execute(
        "INSERT INTO config_observations "
        "(org_id, entity_type, entity_id, config_area, sub_key, hash, "
        "observed_at, source_event, sweep_run_id, name_hint) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("org1", "device", "Q2XX-1234", "switch_ports", None,
         "abc123", "2026-01-01T00:00:00", "baseline", 1, "Main Switch"),
    )
    test_db.commit()
    events = build_snapshot_events(test_db)
    assert len(events) == 1
    ev = events[0]
    assert ev["eventType"] == "MerakiConfigSnapshot"
    assert ev["entity_type"] == "device"
    assert ev["entity_id"] == "Q2XX-1234"
    assert ev["entity_name"] == "Main Switch"
    assert ev["config_area"] == "switch_ports"
    assert ev["config_hash"] == "abc123"
    assert ev["config_json"] == '{"mode":"access"}'
    assert ev["org_id"] == "org1"
    assert ev["tags.source"] == "topology-maps-app"
    assert ev["sweep_run_id"] == 1
    assert ev["sub_key"] == ""
    assert ev["network_id"] == ""


def test_build_snapshot_events_dedupes_to_latest(test_db):
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h1", '{"v":1}', 7, "2026-01-01"))
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h2", '{"v":2}', 7, "2026-01-02"))
    for hash_, ts in [("h1", "2026-01-01T00:00:00"), ("h2", "2026-01-02T00:00:00")]:
        test_db.execute(
            "INSERT INTO config_observations "
            "(org_id, entity_type, entity_id, config_area, sub_key, hash, observed_at, source_event) "
            "VALUES (?,?,?,?,?,?,?,?)",
            ("org1", "device", "AAAA", "vlans", None, hash_, ts, "baseline"),
        )
    test_db.commit()
    events = build_snapshot_events(test_db)
    assert len(events) == 1
    assert events[0]["config_hash"] == "h2"


def test_build_snapshot_events_empty_db(test_db):
    assert build_snapshot_events(test_db) == []


def _insert_obs(conn, *, org_id="org1", entity_type="device", entity_id="Q2XX",
                config_area="switch_ports", sub_key=None, hash_="h1",
                ts="2026-01-01T00:00:00", name_hint="Switch A"):
    conn.execute(
        "INSERT INTO config_observations "
        "(org_id, entity_type, entity_id, config_area, sub_key, hash, "
        "observed_at, source_event, name_hint) VALUES (?,?,?,?,?,?,?,?,?)",
        (org_id, entity_type, entity_id, config_area, sub_key, hash_, ts, "baseline", name_hint),
    )
    conn.commit()


def test_build_change_events_detects_hash_diff(test_db):
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("h1", '[{"portId":"1","enabled":true}]', 25, "2026-01-01"))
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("h2", '[{"portId":"1","enabled":false}]', 26, "2026-01-02"))
    _insert_obs(test_db, hash_="h1", ts="2026-01-01T00:00:00")
    _insert_obs(test_db, hash_="h2", ts="2026-01-02T00:00:00")

    events = build_change_events(test_db, since_ts=None)
    assert len(events) == 1
    ev = events[0]
    assert ev["eventType"] == "MerakiConfigChange"
    assert ev["from_hash"] == "h1"
    assert ev["to_hash"] == "h2"
    assert ev["entity_id"] == "Q2XX"
    assert ev["config_area"] == "switch_ports"
    assert ev["org_id"] == "org1"
    assert ev["tags.source"] == "topology-maps-app"
    diff = json.loads(ev["diff_json"])
    assert isinstance(diff, list)
    assert len(diff) > 0
    assert ev["change_summary"] != ""


def test_build_change_events_no_previous_obs_excluded(test_db):
    """First observation for an entity/area is not a change event."""
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("h1", '{}', 2, "2026-01-01"))
    _insert_obs(test_db, hash_="h1", ts="2026-01-01T00:00:00")

    events = build_change_events(test_db, since_ts=None)
    assert events == []


def test_build_change_events_since_ts_filters(test_db):
    """Only observations newer than since_ts produce change events."""
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h1", '{}', 2, "2026-01-01"))
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h2", '{"x":1}', 8, "2026-01-02"))
    _insert_obs(test_db, hash_="h1", ts="2026-01-01T00:00:00")
    _insert_obs(test_db, hash_="h2", ts="2026-01-02T00:00:00")

    events = build_change_events(test_db, since_ts="2026-01-03T00:00:00")
    assert events == []

    events2 = build_change_events(test_db, since_ts="2026-01-01T12:00:00")
    assert len(events2) == 1


def test_compute_change_summary():
    from config_collector.diff_engine import DiffResult, RowAdded, RowRemoved
    result = DiffResult(
        shape="array",
        changes=[RowAdded(identity="1", row={}), RowAdded(identity="2", row={}),
                 RowRemoved(identity="3", row={})],
        unchanged_count=5,
    )
    summary = _compute_change_summary(result)
    assert "2 added" in summary
    assert "1 removed" in summary
