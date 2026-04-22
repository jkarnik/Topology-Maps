# Plan 1.11 — Storage: Change Events + Sweep Runs

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Complete the storage layer by adding data-access functions for `config_change_events` and `config_sweep_runs`.

**Depends on:** Plan 1.01 (schema).
**Unblocks:** Plan 1.13 (baseline runner), Plan 1.14 (change-log poller), Plan 1.15 (anti-drift sweep).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/store.py` | Modify | Append change-event and sweep-run functions |
| `server/tests/test_config_store_events.py` | Create | Tests for change-event insert/dedup/query |
| `server/tests/test_config_store_sweeps.py` | Create | Tests for sweep-run CRUD + resume |

---

## Task 1: `insert_change_event` with dedup

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_config_store_events.py`:

```python
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
    assert dup is None  # skipped

    count = conn.execute("SELECT COUNT(*) AS n FROM config_change_events").fetchone()["n"]
    assert count == 1


def test_insert_change_event_handles_missing_fields(conn):
    """Events may have null/missing optional fields — must not crash."""
    from server.config_collector.store import insert_change_event

    minimal = {"ts": "2026-04-22T10:00:00Z", "label": "VLAN"}
    event_id = insert_change_event(conn, org_id="o1", event=minimal)
    assert event_id is not None
```

- [ ] **Step 1.2: Run — should fail**

- [ ] **Step 1.3: Implement `insert_change_event`**

Append to `server/config_collector/store.py`:

```python
import json as _json


def insert_change_event(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    event: dict,
) -> Optional[int]:
    """Insert a change-log event; return its row id, or None if it was a duplicate."""
    try:
        cursor = conn.execute(
            """INSERT INTO config_change_events
               (org_id, ts, admin_id, admin_name, admin_email,
                network_id, network_name, ssid_number, ssid_name,
                page, label, old_value, new_value,
                client_id, client_description, raw_json, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                org_id,
                event.get("ts"),
                event.get("adminId"),
                event.get("adminName"),
                event.get("adminEmail"),
                event.get("networkId"),
                event.get("networkName"),
                event.get("ssidNumber"),
                event.get("ssidName"),
                event.get("page"),
                event.get("label"),
                event.get("oldValue"),
                event.get("newValue"),
                event.get("clientId"),
                event.get("clientDescription"),
                _json.dumps(event),
                _now_iso(),
            ),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        # Duplicate — hit the UNIQUE(org_id, ts, network_id, label, old_value, new_value)
        return None
```

- [ ] **Step 1.4: Run — should pass**

Expected: 3 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_events.py
git commit -m "feat(config): insert_change_event with dedup (Plan 1.11)"
```

---

## Task 2: `get_change_events` with filtering

- [ ] **Step 2.1: Write failing test**

Append to `server/tests/test_config_store_events.py`:

```python
def test_get_change_events_newest_first(conn):
    from server.config_collector.store import insert_change_event, get_change_events

    for i, ts in enumerate(["2026-04-22T10:00:00Z", "2026-04-22T11:00:00Z", "2026-04-22T12:00:00Z"]):
        insert_change_event(conn, org_id="o1", event={
            "ts": ts, "label": f"lbl{i}", "networkId": "N_1",
            "oldValue": str(i), "newValue": str(i+1),
        })

    events = get_change_events(conn, org_id="o1", limit=10)
    assert [e["ts"] for e in events] == [
        "2026-04-22T12:00:00Z",
        "2026-04-22T11:00:00Z",
        "2026-04-22T10:00:00Z",
    ]


def test_get_change_events_filter_by_network(conn):
    from server.config_collector.store import insert_change_event, get_change_events

    insert_change_event(conn, org_id="o1", event={"ts": "t1", "label": "x", "networkId": "N_A"})
    insert_change_event(conn, org_id="o1", event={"ts": "t2", "label": "y", "networkId": "N_B"})

    events = get_change_events(conn, org_id="o1", network_id="N_A", limit=10)
    assert len(events) == 1
    assert events[0]["network_id"] == "N_A"
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Implement `get_change_events`**

Append to `server/config_collector/store.py`:

```python
def get_change_events(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    network_id: Optional[str] = None,
    limit: int = 100,
    before_ts: Optional[str] = None,
) -> list[dict]:
    sql = "SELECT * FROM config_change_events WHERE org_id=?"
    params: list = [org_id]
    if network_id is not None:
        sql += " AND network_id=?"
        params.append(network_id)
    if before_ts is not None:
        sql += " AND ts < ?"
        params.append(before_ts)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)

    return [dict(r) for r in conn.execute(sql, params).fetchall()]
```

- [ ] **Step 2.4: Run — should pass**

Expected: 5 tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_events.py
git commit -m "feat(config): get_change_events with filtering (Plan 1.11)"
```

---

## Task 3: Sweep run CRUD — create, update_status, complete

- [ ] **Step 3.1: Write failing test**

Create `server/tests/test_config_store_sweeps.py`:

```python
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
```

- [ ] **Step 3.2: Run — should fail**

- [ ] **Step 3.3: Implement sweep CRUD**

Append to `server/config_collector/store.py`:

```python
def create_sweep_run(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    kind: str,
    total_calls: Optional[int] = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO config_sweep_runs (org_id, kind, status, total_calls)
           VALUES (?, ?, 'queued', ?)""",
        (org_id, kind, total_calls),
    )
    conn.commit()
    return cursor.lastrowid


def mark_sweep_running(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE config_sweep_runs SET status='running', started_at=? WHERE id=?",
        (_now_iso(), run_id),
    )
    conn.commit()


def increment_sweep_counters(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    completed: int = 0,
    failed: int = 0,
    skipped: int = 0,
) -> None:
    conn.execute(
        """UPDATE config_sweep_runs SET
             completed_calls = completed_calls + ?,
             failed_calls = failed_calls + ?,
             skipped_calls = skipped_calls + ?
           WHERE id=?""",
        (completed, failed, skipped, run_id),
    )
    conn.commit()


def mark_sweep_complete(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE config_sweep_runs SET status='complete', completed_at=? WHERE id=?",
        (_now_iso(), run_id),
    )
    conn.commit()


def mark_sweep_failed(conn: sqlite3.Connection, run_id: int, *, error_summary: str) -> None:
    conn.execute(
        "UPDATE config_sweep_runs SET status='failed', completed_at=?, error_summary=? WHERE id=?",
        (_now_iso(), error_summary, run_id),
    )
    conn.commit()
```

- [ ] **Step 3.4: Run — should pass**

Expected: 5 tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_sweeps.py
git commit -m "feat(config): sweep run CRUD — create/running/counters/complete/failed (Plan 1.11)"
```

---

## Task 4: Resume helper — list completed entity/area pairs

- [ ] **Step 4.1: Write failing test**

Append to `server/tests/test_config_store_sweeps.py`:

```python
def test_list_completed_entity_areas_for_sweep(conn):
    from server.config_collector.store import (
        create_sweep_run, insert_observation_if_changed,
        list_completed_entity_areas,
    )

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=100)

    # Seed a blob
    conn.execute("INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
                 ("h1", "{}", 2, "t"))
    conn.commit()

    # Two observations under this sweep_run_id
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
```

- [ ] **Step 4.2: Run — should fail**

- [ ] **Step 4.3: Implement `list_completed_entity_areas`**

Append to `server/config_collector/store.py`:

```python
def list_completed_entity_areas(
    conn: sqlite3.Connection,
    *,
    sweep_run_id: int,
) -> set[tuple[str, str, str, Optional[str]]]:
    """Return set of (entity_type, entity_id, config_area, sub_key) tuples with
    at least one observation under this sweep_run_id. Used for resumability."""
    rows = conn.execute(
        """SELECT DISTINCT entity_type, entity_id, config_area, sub_key
           FROM config_observations WHERE sweep_run_id=?""",
        (sweep_run_id,),
    ).fetchall()
    return {(r["entity_type"], r["entity_id"], r["config_area"], r["sub_key"]) for r in rows}
```

- [ ] **Step 4.4: Run — should pass**

Expected: 6 tests pass.

- [ ] **Step 4.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_sweeps.py
git commit -m "feat(config): list_completed_entity_areas for baseline resume (Plan 1.11)"
```

---

## Task 5: `get_active_sweep_run` for idempotency

- [ ] **Step 5.1: Write failing test**

Append to `server/tests/test_config_store_sweeps.py`:

```python
def test_get_active_sweep_run_returns_queued_or_running(conn):
    from server.config_collector.store import create_sweep_run, mark_sweep_running, mark_sweep_complete, get_active_sweep_run

    # No active run yet
    assert get_active_sweep_run(conn, org_id="o1", kind="baseline") is None

    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=10)
    active = get_active_sweep_run(conn, org_id="o1", kind="baseline")
    assert active["id"] == run_id

    mark_sweep_running(conn, run_id)
    active = get_active_sweep_run(conn, org_id="o1", kind="baseline")
    assert active["id"] == run_id
    assert active["status"] == "running"

    # After completion, no longer active
    mark_sweep_complete(conn, run_id)
    assert get_active_sweep_run(conn, org_id="o1", kind="baseline") is None
```

- [ ] **Step 5.2: Run — should fail**

- [ ] **Step 5.3: Implement `get_active_sweep_run`**

Append to `server/config_collector/store.py`:

```python
def get_active_sweep_run(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    kind: str,
) -> Optional[dict]:
    """Return the most recent queued/running sweep of `kind` for `org_id`, or None."""
    row = conn.execute(
        """SELECT * FROM config_sweep_runs
           WHERE org_id=? AND kind=? AND status IN ('queued', 'running')
           ORDER BY id DESC LIMIT 1""",
        (org_id, kind),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 5.4: Run — should pass**

Expected: 7 tests pass.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_sweeps.py
git commit -m "feat(config): get_active_sweep_run for idempotency checks (Plan 1.11)"
```

---

## Completion Checklist

- [ ] Storage API complete: blobs, observations, change events, sweep runs
- [ ] ~15 passing tests across 3 event/sweep test files
- [ ] 5 commits

## What This Unblocks

- Plans 1.13, 1.14, 1.15: collectors write via this full storage API.
- Plan 1.17: REST endpoints for history + change-events consume these readers.
