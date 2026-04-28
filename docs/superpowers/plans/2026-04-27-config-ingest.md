# Config Ingest Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `nr_ingest/config_ingest.py` — a script that reads Meraki config snapshots and hash-change events from the local SQLite DB and pushes them to NR as `MerakiConfigSnapshot` and `MerakiConfigChange` custom events.

**Architecture:** Follows the same pattern as `nr_ingest/push_all_devices.py`. A new `config_data_source.py` helper loads `data/topology.db` from the running container (with local fallback). The main script queries `config_observations` + `config_blobs` for snapshots, detects hash changes by comparing consecutive observations, computes diffs via `diff_engine`, and batch-POSTs both event types to the NR Events API. A `.last_config_ingest` marker file tracks the last successful run so change events are not re-pushed.

**Tech Stack:** Python 3.11, `httpx`, `sqlite3` (stdlib), `diff_engine` from `server/config_collector/`, `.env` for NR credentials.

---

## File Map


| Action | File | Responsibility |
|--------|------|---------------|
| Create | `nr_ingest/config_data_source.py` | Load `topology.db` from container or local |
| Create | `nr_ingest/config_ingest.py` | Build events, post to NR, manage marker file |
| Create | `nr_ingest/tests/__init__.py` | Make tests discoverable by pytest |
| Create | `nr_ingest/tests/conftest.py` | Shared `test_db` fixture |
| Create | `nr_ingest/tests/test_config_ingest.py` | All tests for config_ingest |

---

## Task 1: config_data_source.py — topology.db loader

**Files:**
- Create: `nr_ingest/config_data_source.py`
- Create: `nr_ingest/tests/__init__.py`
- Create: `nr_ingest/tests/conftest.py`
- Create: `nr_ingest/tests/test_config_ingest.py` (first test only)

- [ ] **Step 1: Write the failing test**

```python
# nr_ingest/tests/test_config_ingest.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py::test_load_config_db_local_fallback -v
```
Expected: `ImportError: No module named 'config_data_source'`

- [ ] **Step 3: Create `nr_ingest/tests/__init__.py`** (empty file, just `touch` it)

- [ ] **Step 4: Create `nr_ingest/tests/conftest.py`**

```python
# nr_ingest/tests/conftest.py
from __future__ import annotations
import sqlite3
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).parent.parent))

CONFIG_SCHEMA = """
    CREATE TABLE IF NOT EXISTS config_blobs (
        hash TEXT PRIMARY KEY, payload TEXT NOT NULL,
        byte_size INTEGER NOT NULL, first_seen_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS config_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        org_id TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
        config_area TEXT NOT NULL, sub_key TEXT, hash TEXT NOT NULL,
        observed_at TEXT NOT NULL, source_event TEXT NOT NULL,
        change_event_id INTEGER, sweep_run_id INTEGER,
        name_hint TEXT, enabled_hint INTEGER
    );
"""

@pytest.fixture
def test_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(CONFIG_SCHEMA)
    yield conn
    conn.close()
```

- [ ] **Step 5: Write `nr_ingest/config_data_source.py`**

```python
# nr_ingest/config_data_source.py
from __future__ import annotations
import sqlite3
import subprocess
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
_LOCAL_TOPOLOGY_DB = PROJECT_ROOT / "data" / "topology.db"
_CONTAINER = "topologymaps-server-1"
_CONTAINER_DB = "/app/data/topology.db"


def _resolve_topology_db_path() -> Path:
    tmp = Path(tempfile.mktemp(suffix=".db"))
    try:
        result = subprocess.run(
            ["docker", "cp", f"{_CONTAINER}:{_CONTAINER_DB}", str(tmp)],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and tmp.exists():
            print(f"Using topology.db copied from {_CONTAINER}:{_CONTAINER_DB}")
            return tmp
    except Exception:
        pass
    print(f"Container unavailable — using local {_LOCAL_TOPOLOGY_DB}")
    return _LOCAL_TOPOLOGY_DB


def load_config_db() -> sqlite3.Connection:
    path = _resolve_topology_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
```

- [ ] **Step 6: Run test to verify it passes**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py::test_load_config_db_local_fallback -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add nr_ingest/config_data_source.py nr_ingest/tests/__init__.py nr_ingest/tests/conftest.py nr_ingest/tests/test_config_ingest.py
git commit -m "feat(nr_ingest): add config_data_source loader for topology.db"
```

---

## Task 2: build_snapshot_events() — MerakiConfigSnapshot builder

**Files:**
- Create: `nr_ingest/config_ingest.py` (snapshot builder only)
- Modify: `nr_ingest/tests/test_config_ingest.py` (append snapshot tests)

- [ ] **Step 1: Write the failing tests**

Append to `nr_ingest/tests/test_config_ingest.py`:

```python
from config_ingest import build_snapshot_events


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "snapshot" -v
```
Expected: `ImportError: cannot import name 'build_snapshot_events'`

- [ ] **Step 3: Create `nr_ingest/config_ingest.py`**

```python
# nr_ingest/config_ingest.py
"""Push Meraki config data from topology.db to New Relic as custom events.

Usage:
    python3 nr_ingest/config_ingest.py              # push all data
    python3 nr_ingest/config_ingest.py --since 2h   # only changes in last 2 hours
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx

_DIR = Path(__file__).parent
_PROJECT_ROOT = _DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT / "server"))

from config_collector.diff_engine import compute_diff  # noqa: E402

_ENV_FILE = _PROJECT_ROOT / ".env"
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

NR_EVENT_API = "https://insights-collector.newrelic.com/v1/accounts/{account_id}/events"
MARKER_FILE = _DIR / "data" / ".last_config_ingest"


def build_snapshot_events(conn: sqlite3.Connection) -> list[dict]:
    """Return one MerakiConfigSnapshot event per (entity, config_area), latest only."""
    sql = """
        SELECT
            o.org_id, o.entity_type, o.entity_id, o.config_area, o.sub_key,
            o.hash AS config_hash, o.observed_at, o.sweep_run_id,
            COALESCE(o.name_hint, '') AS entity_name,
            b.payload AS config_json
        FROM config_observations o
        JOIN config_blobs b ON b.hash = o.hash
        WHERE o.id = (
            SELECT id FROM config_observations i
            WHERE i.org_id = o.org_id AND i.entity_type = o.entity_type
              AND i.entity_id = o.entity_id AND i.config_area = o.config_area
              AND i.sub_key IS o.sub_key
            ORDER BY i.observed_at DESC LIMIT 1
        )
        ORDER BY o.entity_type, o.entity_id, o.config_area
    """
    return [
        {
            "eventType": "MerakiConfigSnapshot",
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "config_area": row["config_area"],
            "sub_key": row["sub_key"] or "",
            "config_hash": row["config_hash"],
            "config_json": row["config_json"],
            "org_id": row["org_id"],
            "network_id": "",
            "sweep_run_id": row["sweep_run_id"] or 0,
            "tags.source": "topology-maps-app",
        }
        for row in conn.execute(sql).fetchall()
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "snapshot" -v
```
Expected: 3 PASSes

- [ ] **Step 5: Commit**

```bash
git add nr_ingest/config_ingest.py nr_ingest/tests/test_config_ingest.py
git commit -m "feat(nr_ingest): add build_snapshot_events for MerakiConfigSnapshot"
```

---

## Task 3: build_change_events() — MerakiConfigChange builder

**Files:**
- Modify: `nr_ingest/config_ingest.py` (append build_change_events + helpers)
- Modify: `nr_ingest/tests/test_config_ingest.py` (append change tests)

- [ ] **Step 1: Write the failing tests**

Append to `nr_ingest/tests/test_config_ingest.py`:

```python
from config_ingest import build_change_events, _compute_change_summary


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
    from config_collector.diff_engine import DiffResult, RowAdded, RowRemoved, FieldChanged
    result = DiffResult(
        shape="array",
        changes=[RowAdded(identity="1", row={}), RowAdded(identity="2", row={}),
                 RowRemoved(identity="3", row={})],
        unchanged_count=5,
    )
    summary = _compute_change_summary(result)
    assert "2 added" in summary
    assert "1 removed" in summary
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "change" -v
```
Expected: `ImportError: cannot import name 'build_change_events'`

- [ ] **Step 3: Append to `nr_ingest/config_ingest.py`**

```python
def _compute_change_summary(diff_result) -> str:
    """Summarise a DiffResult as 'N added, M removed, K changed'."""
    from config_collector.diff_engine import RowAdded, RowRemoved, RowChanged, FieldChanged, FieldAdded, FieldRemoved
    added = sum(1 for c in diff_result.changes if isinstance(c, (RowAdded, FieldAdded)))
    removed = sum(1 for c in diff_result.changes if isinstance(c, (RowRemoved, FieldRemoved)))
    changed = sum(1 for c in diff_result.changes if isinstance(c, (RowChanged, FieldChanged)))
    parts = []
    if added:
        parts.append(f"{added} added")
    if removed:
        parts.append(f"{removed} removed")
    if changed:
        parts.append(f"{changed} changed")
    return ", ".join(parts) if parts else "no changes"


def _serialize_diff(diff_result) -> str:
    """Serialize DiffResult.changes to JSON (dataclasses → dicts)."""
    import dataclasses
    changes = []
    for c in diff_result.changes:
        d = dataclasses.asdict(c)
        changes.append(d)
    return json.dumps(changes)


def build_change_events(conn: sqlite3.Connection, since_ts: Optional[str]) -> list[dict]:
    """Return MerakiConfigChange events for hash changes detected after since_ts."""
    sql = """
        SELECT
            a.org_id, a.entity_type, a.entity_id, a.config_area, a.sub_key,
            COALESCE(a.name_hint, '') AS entity_name,
            a.hash AS to_hash, a.observed_at AS detected_at,
            prev.hash AS from_hash,
            b_new.payload AS to_payload, b_old.payload AS from_payload
        FROM config_observations a
        LEFT JOIN config_observations prev ON (
            prev.org_id = a.org_id AND prev.entity_type = a.entity_type
            AND prev.entity_id = a.entity_id AND prev.config_area = a.config_area
            AND prev.sub_key IS a.sub_key
            AND prev.id = (
                SELECT id FROM config_observations x
                WHERE x.org_id = a.org_id AND x.entity_type = a.entity_type
                  AND x.entity_id = a.entity_id AND x.config_area = a.config_area
                  AND x.sub_key IS a.sub_key AND x.observed_at < a.observed_at
                ORDER BY x.observed_at DESC LIMIT 1
            )
        )
        JOIN config_blobs b_new ON b_new.hash = a.hash
        LEFT JOIN config_blobs b_old ON b_old.hash = prev.hash
        WHERE prev.hash IS NOT NULL
          AND prev.hash != a.hash
          AND (? IS NULL OR a.observed_at > ?)
        ORDER BY a.observed_at
    """
    rows = conn.execute(sql, (since_ts, since_ts)).fetchall()
    events = []
    for row in rows:
        try:
            blob_from = json.loads(row["from_payload"])
            blob_to = json.loads(row["to_payload"])
            diff = compute_diff(blob_from, blob_to)
            diff_json = _serialize_diff(diff)
            summary = _compute_change_summary(diff)
        except Exception:
            diff_json = "[]"
            summary = "diff unavailable"
        events.append({
            "eventType": "MerakiConfigChange",
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "entity_name": row["entity_name"],
            "config_area": row["config_area"],
            "sub_key": row["sub_key"] or "",
            "from_hash": row["from_hash"],
            "to_hash": row["to_hash"],
            "diff_json": diff_json,
            "change_summary": summary,
            "detected_at": row["detected_at"],
            "org_id": row["org_id"],
            "network_id": "",
            "tags.source": "topology-maps-app",
        })
    return events
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "change" -v
```
Expected: 4 PASSes

- [ ] **Step 5: Commit**

```bash
git add nr_ingest/config_ingest.py nr_ingest/tests/test_config_ingest.py
git commit -m "feat(nr_ingest): add build_change_events for MerakiConfigChange"
```

---

## Task 4: Marker file + --since flag

**Files:**
- Modify: `nr_ingest/config_ingest.py` (append marker helpers + parse_since)
- Modify: `nr_ingest/tests/test_config_ingest.py` (append marker tests)

- [ ] **Step 1: Write the failing tests**

Append to `nr_ingest/tests/test_config_ingest.py`:

```python
from config_ingest import read_marker, write_marker, parse_since


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "marker or since" -v
```
Expected: `ImportError: cannot import name 'read_marker'`

- [ ] **Step 3: Append to `nr_ingest/config_ingest.py`**

```python
def read_marker(marker_path: Path = MARKER_FILE) -> Optional[str]:
    """Return last successful ingest timestamp, or None if no marker exists."""
    if marker_path.exists():
        return marker_path.read_text().strip() or None
    return None


def write_marker(ts: str, marker_path: Path = MARKER_FILE) -> None:
    """Record a successful ingest timestamp."""
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    marker_path.write_text(ts)


def parse_since(since_str: Optional[str]) -> Optional[str]:
    """Convert a duration string like '2h' or '30m' to an ISO timestamp."""
    if since_str is None:
        return None
    m = re.fullmatch(r"(\d+)([hm])", since_str.strip())
    if not m:
        raise ValueError(f"Invalid --since format: {since_str!r}. Use e.g. '2h' or '30m'.")
    value, unit = int(m.group(1)), m.group(2)
    delta = timedelta(hours=value) if unit == "h" else timedelta(minutes=value)
    cutoff = datetime.now(timezone.utc) - delta
    return cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "marker or since" -v
```
Expected: 5 PASSes

- [ ] **Step 5: Commit**

```bash
git add nr_ingest/config_ingest.py nr_ingest/tests/test_config_ingest.py
git commit -m "feat(nr_ingest): add marker file helpers and --since flag parser"
```

---

## Task 5: post_events_batch() + main() — wire it all together

**Files:**
- Modify: `nr_ingest/config_ingest.py` (append post_events_batch + main)
- Modify: `nr_ingest/tests/test_config_ingest.py` (append main tests)

- [ ] **Step 1: Write the failing tests**

Append to `nr_ingest/tests/test_config_ingest.py`:

```python
from config_ingest import post_events_batch, chunked


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


def test_main_pushes_snapshot_and_change_events(test_db, tmp_path, monkeypatch):
    """main() posts both event types and writes the marker file."""
    import config_ingest as ci

    # Seed DB with one observation (snapshot only, no change since no prior)
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

    marker = tmp_path / ".last_config_ingest"
    result = ci.main(since_override=None, marker_path=marker)

    assert result == 0
    assert any(e["eventType"] == "MerakiConfigSnapshot" for e in posted_events)
    assert marker.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python3 -m pytest nr_ingest/tests/test_config_ingest.py -k "batch or chunked or main" -v
```
Expected: `ImportError: cannot import name 'post_events_batch'`

- [ ] **Step 3: Append to `nr_ingest/config_ingest.py`**

```python
def chunked(lst: list, size: int):
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


def post_events_batch(url: str, headers: dict, events: list[dict]) -> bool:
    resp = httpx.post(url, headers=headers, json=events, timeout=30.0)
    if resp.status_code != 200:
        print(f"  FAILED {resp.status_code}: {resp.text}")
        return False
    return True


def main(
    since_override: Optional[str] = None,
    marker_path: Path = MARKER_FILE,
) -> int:
    license_key = os.environ["NR_LICENSE_KEY"]
    account_id = os.environ["NR_ACCOUNT_ID"]
    url = NR_EVENT_API.format(account_id=account_id)
    headers = {"Api-Key": license_key, "Content-Type": "application/json"}

    from config_data_source import load_config_db
    conn = load_config_db()

    since_ts = since_override if since_override else read_marker(marker_path=marker_path)

    snapshot_events = build_snapshot_events(conn)
    change_events = build_change_events(conn, since_ts=since_ts)
    all_events = snapshot_events + change_events

    print(f"Snapshot events:  {len(snapshot_events)}")
    print(f"Change events:    {len(change_events)}")
    print(f"Total to push:    {len(all_events)}")

    if not all_events:
        print("Nothing to push.")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        write_marker(now, marker_path=marker_path)
        return 0

    total_sent = 0
    for batch_num, batch in enumerate(chunked(all_events, 500), start=1):
        print(f"Batch {batch_num}: posting {len(batch)} events...")
        if not post_events_batch(url, headers, batch):
            print("Aborting — batch failed.")
            return 1
        total_sent += len(batch)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write_marker(now, marker_path=marker_path)
    print(f"\nAll {total_sent} events accepted. Marker updated: {now}")
    return 0


if __name__ == "__main__":
    import sys as _sys

    parser = argparse.ArgumentParser(description="Push Meraki config events to New Relic")
    parser.add_argument("--since", metavar="DURATION",
                        help="Override since-timestamp, e.g. '2h' or '30m'")
    args = parser.parse_args()

    since = parse_since(args.since) if args.since else None
    _sys.exit(main(since_override=since))
```

Also add `import argparse` near the top of the file (in the existing imports section).

- [ ] **Step 4: Run all tests to verify they pass**

```bash
python3 -m pytest nr_ingest/tests/ -v
```
Expected: All tests PASS (≥12 tests)

- [ ] **Step 5: Run the full backend test suite to check for regressions**

```bash
python3 -m pytest -v 2>&1 | tail -20
```
Expected: All existing server tests still pass.

- [ ] **Step 6: Commit**

```bash
git add nr_ingest/config_ingest.py nr_ingest/tests/test_config_ingest.py
git commit -m "feat(nr_ingest): complete config_ingest.py with main() and NR posting"
```

---

## Spec Coverage Self-Check

| Spec requirement | Covered by |
|---|---|
| `MerakiConfigSnapshot` event with all fields | Task 2 |
| `MerakiConfigChange` event with `from_hash`, `to_hash`, `diff_json`, `change_summary` | Task 3 |
| Container copy preferred, local fallback | Task 1 (`config_data_source.py`) |
| `.last_config_ingest` marker file | Task 4 |
| `--since 2h` flag | Task 4 (`parse_since`) |
| Batch POST to `insights-collector.newrelic.com` | Task 5 |
| `NR_LICENSE_KEY` and `NR_ACCOUNT_ID` from `.env` | Task 5 (`main()`) |
| `tags.source = 'topology-maps-app'` | Tasks 2, 3 |

