"""Tests for config_change_events data access (Plan 1.11)."""
from __future__ import annotations

import json
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


def _sample_event():
    return {
        "ts": "2026-04-22T10:00:00Z",
        "adminId": "a1", "adminName": "Alice", "adminEmail": "a@b.com",
        "networkId": "N_1", "networkName": "Store 1",
        "ssidNumber": 3, "ssidName": "Guest",
        "page": "Wireless > Access Control", "label": "Bandwidth limit",
        "oldValue": "11", "newValue": "24",
        "clientId": None, "clientDescription": None,
    }


def test_insert_change_event_writes_row_returns_id(conn):
    from server.config_collector.store import insert_change_event

    ev = _sample_event()
    event_id = insert_change_event(conn, org_id="o1", event=ev)
    assert event_id is not None

    row = conn.execute("SELECT * FROM config_change_events WHERE id=?", (event_id,)).fetchone()
    assert row["org_id"] == "o1"
    assert row["ts"] == "2026-04-22T10:00:00Z"
    assert row["label"] == "Bandwidth limit"
    assert row["ssid_number"] == 3
    assert json.loads(row["raw_json"]) == ev


def test_insert_change_event_dedupes_duplicate(conn):
    from server.config_collector.store import insert_change_event

    ev = _sample_event()
    first = insert_change_event(conn, org_id="o1", event=ev)
    dup = insert_change_event(conn, org_id="o1", event=ev)
    assert first is not None
    assert dup is None

    count = conn.execute("SELECT COUNT(*) AS n FROM config_change_events").fetchone()["n"]
    assert count == 1


def test_insert_change_event_handles_missing_fields(conn):
    """Events may have null/missing optional fields — must not crash."""
    from server.config_collector.store import insert_change_event

    minimal = {"ts": "2026-04-22T10:00:00Z", "label": "VLAN"}
    event_id = insert_change_event(conn, org_id="o1", event=minimal)
    assert event_id is not None
