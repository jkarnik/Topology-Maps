from __future__ import annotations
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_data_source import load_config_db
import config_data_source as _cds
from config_ingest import build_snapshot_events
from config_ingest import build_change_events, _compute_change_summary, read_marker, write_marker, parse_since
from config_ingest import post_events_batch, chunked, query_nr_last_push, query_nr_snapshot_hashes, filter_new_snapshots
import httpx
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
    assert ev["from_payload"] == '[{"portId":"1","enabled":true}]'
    assert ev["to_payload"] == '[{"portId":"1","enabled":false}]'


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


def test_compute_change_summary_secret():
    from config_collector.diff_engine import DiffResult, SecretChanged
    result = DiffResult(
        shape="object",
        changes=[SecretChanged(key="password_hash")],
        unchanged_count=0,
    )
    summary = _compute_change_summary(result)
    assert "secret rotated" in summary


def test_build_change_events_same_hash_no_event(test_db):
    """Two observations with identical hashes must not produce a change event."""
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("h1", '{"mode":"access"}', 14, "2026-01-01"))
    _insert_obs(test_db, hash_="h1", ts="2026-01-01T00:00:00")
    _insert_obs(test_db, hash_="h1", ts="2026-01-02T00:00:00")
    events = build_change_events(test_db, since_ts=None)
    assert events == []


def test_marker_round_trip(tmp_path):
    path = tmp_path / ".last_config_ingest"
    write_marker("2026-01-15T10:00:00Z", marker_path=path)
    assert read_marker(marker_path=path) == "2026-01-15T10:00:00Z"


def test_marker_read_missing(tmp_path):
    path = tmp_path / ".last_config_ingest"
    assert read_marker(marker_path=path) is None


def test_parse_since_hours():
    ts = parse_since("2h")
    now = datetime.now(timezone.utc)
    delta = now - datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert 1.9 * 3600 < delta.total_seconds() < 2.1 * 3600


def test_parse_since_minutes():
    ts = parse_since("30m")
    now = datetime.now(timezone.utc)
    delta = now - datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert 28 * 60 < delta.total_seconds() < 32 * 60


def test_parse_since_none():
    assert parse_since(None) is None


def test_parse_since_uppercase():
    ts = parse_since("2H")
    now = datetime.now(timezone.utc)
    delta = now - datetime.fromisoformat(ts.replace("Z", "+00:00"))
    assert 1.9 * 3600 < delta.total_seconds() < 2.1 * 3600


def test_parse_since_zero_raises():
    import pytest
    with pytest.raises(ValueError, match="must be > 0"):
        parse_since("0h")


def test_post_events_batch_success(monkeypatch):
    posted = []

    class FakeResp:
        status_code = 200
        text = '{"success":true}'

    def mock_post(url, *, headers, json, timeout):
        posted.append(json)
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    result = post_events_batch(
        "https://insights.example.com/events",
        {"Api-Key": "x"},
        [{"eventType": "Foo", "val": 1}, {"eventType": "Foo", "val": 2}],
    )
    assert result is True
    assert len(posted) == 1
    assert len(posted[0]) == 2


def test_post_events_batch_failure(monkeypatch):
    class FakeResp:
        status_code = 403
        text = "Forbidden"

    monkeypatch.setattr(httpx, "post", lambda *a, **kw: FakeResp())
    result = post_events_batch("https://x.com/e", {}, [{"eventType": "Foo"}])
    assert result is False


def test_chunked():
    batches = list(chunked(list(range(10)), 3))
    assert batches == [[0, 1, 2], [3, 4, 5], [6, 7, 8], [9]]


def test_query_nr_snapshot_hashes_returns_dict(monkeypatch):
    """Returns {(entity_id, config_area): hash} from NR facet results."""
    def mock_post(url, *, headers, json, timeout):
        class FakeResp:
            status_code = 200
            def json(self):
                return {"data": {"actor": {"account": {"nrql": {"results": [
                    {"latest.config_hash": "abc", "facet": ["Q2XX-1", "switch_ports"]},
                    {"latest.config_hash": "def", "facet": ["Q2XX-1", "vlans"]},
                    {"latest.config_hash": "ghi", "facet": ["N_abc", "ssids"]},
                ]}}}}}
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    result = query_nr_snapshot_hashes("12345", "NRAK-fake")
    assert result == {
        ("Q2XX-1", "switch_ports"): "abc",
        ("Q2XX-1", "vlans"): "def",
        ("N_abc", "ssids"): "ghi",
    }


def test_query_nr_snapshot_hashes_returns_empty_on_no_results(monkeypatch):
    """Returns empty dict when NR has no snapshot events."""
    def mock_post(url, *, headers, json, timeout):
        class FakeResp:
            status_code = 200
            def json(self):
                return {"data": {"actor": {"account": {"nrql": {"results": []}}}}}
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    assert query_nr_snapshot_hashes("12345", "NRAK-fake") == {}


def test_query_nr_snapshot_hashes_returns_empty_on_error(monkeypatch):
    """Returns empty dict on HTTP error or exception — caller treats all snapshots as new."""
    def mock_post(url, *, headers, json, timeout):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(httpx, "post", mock_post)
    assert query_nr_snapshot_hashes("12345", "NRAK-fake") == {}


def test_filter_new_snapshots_removes_unchanged():
    """Snapshots whose hash already matches NR are filtered out."""
    events = [
        {"entity_id": "A", "config_area": "vlans", "config_hash": "h1"},
        {"entity_id": "B", "config_area": "vlans", "config_hash": "h2"},
    ]
    nr_hashes = {("A", "vlans"): "h1", ("B", "vlans"): "h2"}
    assert filter_new_snapshots(events, nr_hashes) == []


def test_filter_new_snapshots_keeps_changed_hash():
    """Snapshot with a different hash than NR is kept."""
    events = [{"entity_id": "A", "config_area": "vlans", "config_hash": "h2"}]
    nr_hashes = {("A", "vlans"): "h1"}
    assert filter_new_snapshots(events, nr_hashes) == events


def test_filter_new_snapshots_keeps_new_entity():
    """Snapshot for an entity/area not yet in NR is kept."""
    events = [{"entity_id": "NEW", "config_area": "switch_ports", "config_hash": "h1"}]
    assert filter_new_snapshots(events, {}) == events


def test_filter_new_snapshots_empty_nr_hashes_keeps_all():
    """When NR hash query failed (empty dict), all snapshots are pushed."""
    events = [
        {"entity_id": "A", "config_area": "vlans", "config_hash": "h1"},
        {"entity_id": "B", "config_area": "vlans", "config_hash": "h2"},
    ]
    assert filter_new_snapshots(events, {}) == events


def test_query_nr_last_push_returns_iso_on_success(monkeypatch):
    """Returns an ISO timestamp string when NR has snapshot events."""
    import config_ingest as ci

    # Use a known epoch ms and verify the round-trip conversion
    from datetime import timezone as tz
    known_dt = datetime(2026, 4, 28, 0, 0, 0, tzinfo=tz.utc)
    ts_ms = int(known_dt.timestamp() * 1000)

    def mock_post(url, *, headers, json, timeout):
        class FakeResp:
            status_code = 200
            def json(self):
                return {"data": {"actor": {"account": {"nrql": {"results": [{"max.timestamp": ts_ms}]}}}}}
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    result = query_nr_last_push("12345", "NRAK-fake")
    assert result == known_dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_query_nr_last_push_returns_none_when_no_results(monkeypatch):
    """Returns None when NR has no snapshot events (empty results list)."""
    def mock_post(url, *, headers, json, timeout):
        class FakeResp:
            status_code = 200
            def json(self):
                return {"data": {"actor": {"account": {"nrql": {"results": []}}}}}
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    assert query_nr_last_push("12345", "NRAK-fake") is None


def test_query_nr_last_push_returns_none_on_http_error(monkeypatch):
    """Returns None when NerdGraph returns a non-200 status."""
    def mock_post(url, *, headers, json, timeout):
        class FakeResp:
            status_code = 403
            def json(self):
                return {}
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    assert query_nr_last_push("12345", "NRAK-fake") is None


def test_query_nr_last_push_returns_none_on_exception(monkeypatch):
    """Returns None when the HTTP call raises (network error, timeout, etc.)."""
    def mock_post(url, *, headers, json, timeout):
        raise httpx.ConnectError("unreachable")

    monkeypatch.setattr(httpx, "post", mock_post)
    assert query_nr_last_push("12345", "NRAK-fake") is None


def test_main_pushes_snapshot_and_change_events(test_db, tmp_path, monkeypatch):
    """main() posts both event types and writes the marker file."""
    import config_ingest as ci
    monkeypatch.setattr(ci, "query_nr_last_push", lambda *a: None)
    monkeypatch.setattr(ci, "query_nr_snapshot_hashes", lambda *a: {})

    # Seed DB with one observation (snapshot only — no prior obs so no change event)
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("h1", '{"mode":"access"}', 14, "2026-01-01T00:00:00"))
    test_db.execute(
        "INSERT INTO config_observations "
        "(org_id, entity_type, entity_id, config_area, sub_key, hash, "
        "observed_at, source_event, sweep_run_id, name_hint) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("org1", "device", "Q2XX", "switch_ports", None,
         "h1", "2026-01-01T00:00:00", "baseline", 1, "Main Switch"),
    )
    test_db.commit()

    posted_events = []

    class FakeResp:
        status_code = 200
        text = "{}"

    def mock_post(url, *, headers, json, timeout):
        posted_events.extend(json)
        return FakeResp()

    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(ci, "load_config_db", lambda: test_db)
    monkeypatch.setenv("NR_LICENSE_KEY", "fake")
    monkeypatch.setenv("NR_ACCOUNT_ID", "12345")

    marker = tmp_path / ".last_config_ingest"
    result = ci.main(since_override=None, marker_path=marker)

    assert result == 0
    assert any(e["eventType"] == "MerakiConfigSnapshot" for e in posted_events)
    assert marker.exists()
    ts = marker.read_text().strip()
    datetime.fromisoformat(ts.replace("Z", "+00:00"))  # raises ValueError if malformed


def test_main_skips_unchanged_snapshots(test_db, tmp_path, monkeypatch):
    """main() does not push snapshots whose hash already matches NR."""
    import config_ingest as ci

    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)",
                    ("h1", '{"mode":"access"}', 14, "2026-01-01T00:00:00"))
    test_db.execute(
        "INSERT INTO config_observations "
        "(org_id, entity_type, entity_id, config_area, sub_key, hash, "
        "observed_at, source_event, sweep_run_id, name_hint) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("org1", "device", "Q2XX", "switch_ports", None,
         "h1", "2026-01-01T00:00:00", "baseline", 1, "Switch"),
    )
    test_db.commit()

    # NR already has this exact hash — snapshot should be skipped
    monkeypatch.setattr(ci, "query_nr_last_push", lambda *a: None)
    monkeypatch.setattr(ci, "query_nr_snapshot_hashes", lambda *a: {("Q2XX", "switch_ports"): "h1"})

    posted_events = []

    class FakeResp:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(httpx, "post", lambda url, *, headers, json, timeout: (posted_events.extend(json), FakeResp())[1])
    monkeypatch.setattr(ci, "load_config_db", lambda: test_db)
    monkeypatch.setenv("NR_LICENSE_KEY", "fake")
    monkeypatch.setenv("NR_ACCOUNT_ID", "12345")
    monkeypatch.setenv("NR_USER_API_KEY", "NRAK-fake")

    result = ci.main(since_override=None, marker_path=tmp_path / ".marker")
    assert result == 0
    assert not any(e["eventType"] == "MerakiConfigSnapshot" for e in posted_events)


def test_main_uses_nr_timestamp_over_marker(test_db, tmp_path, monkeypatch):
    """main() uses NR last-push timestamp to filter change events, ignoring older marker."""
    import config_ingest as ci

    # Seed two observations so a change event exists at 2026-01-02
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h1", '{}', 2, "2026-01-01"))
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h2", '{"x":1}', 8, "2026-01-02"))
    _insert_obs(test_db, hash_="h1", ts="2026-01-01T00:00:00")
    _insert_obs(test_db, hash_="h2", ts="2026-01-02T00:00:00")

    # NR reports last push was after the change — so no change events should be pushed
    monkeypatch.setattr(ci, "query_nr_last_push", lambda *a: "2026-01-03T00:00:00Z")
    monkeypatch.setattr(ci, "query_nr_snapshot_hashes", lambda *a: {})
    # Marker is older than NR timestamp — NR should win
    marker = tmp_path / ".last_config_ingest"
    write_marker("2026-01-01T00:00:00Z", marker_path=marker)

    posted_events = []

    class FakeResp:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(httpx, "post", lambda url, *, headers, json, timeout: (posted_events.extend(json), FakeResp())[1])
    monkeypatch.setattr(ci, "load_config_db", lambda: test_db)
    monkeypatch.setenv("NR_LICENSE_KEY", "fake")
    monkeypatch.setenv("NR_ACCOUNT_ID", "12345")
    monkeypatch.setenv("NR_USER_API_KEY", "NRAK-fake")

    result = ci.main(since_override=None, marker_path=marker)
    assert result == 0
    assert not any(e["eventType"] == "MerakiConfigChange" for e in posted_events)


def test_main_falls_back_to_marker_when_nr_unavailable(test_db, tmp_path, monkeypatch):
    """main() falls back to the marker file when NR query returns None."""
    import config_ingest as ci

    # Change event at 2026-01-02
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h1", '{}', 2, "2026-01-01"))
    test_db.execute("INSERT INTO config_blobs VALUES (?,?,?,?)", ("h2", '{"x":1}', 8, "2026-01-02"))
    _insert_obs(test_db, hash_="h1", ts="2026-01-01T00:00:00")
    _insert_obs(test_db, hash_="h2", ts="2026-01-02T00:00:00")

    # NR query unavailable
    monkeypatch.setattr(ci, "query_nr_last_push", lambda *a: None)
    monkeypatch.setattr(ci, "query_nr_snapshot_hashes", lambda *a: {})
    # Marker is before the change — change event should be included
    marker = tmp_path / ".last_config_ingest"
    write_marker("2026-01-01T12:00:00Z", marker_path=marker)

    posted_events = []

    class FakeResp:
        status_code = 200
        text = "{}"

    monkeypatch.setattr(httpx, "post", lambda url, *, headers, json, timeout: (posted_events.extend(json), FakeResp())[1])
    monkeypatch.setattr(ci, "load_config_db", lambda: test_db)
    monkeypatch.setenv("NR_LICENSE_KEY", "fake")
    monkeypatch.setenv("NR_ACCOUNT_ID", "12345")
    monkeypatch.setenv("NR_USER_API_KEY", "NRAK-fake")

    result = ci.main(since_override=None, marker_path=marker)
    assert result == 0
    assert any(e["eventType"] == "MerakiConfigChange" for e in posted_events)
