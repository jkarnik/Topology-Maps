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
