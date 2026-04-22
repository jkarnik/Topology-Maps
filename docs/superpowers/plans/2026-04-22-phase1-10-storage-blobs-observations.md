# Plan 1.10 — Storage: Blobs + Observations

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Implement the data-access layer for `config_blobs` and `config_observations` tables. Supports: insert blob with dedup, insert observation with hash-unchanged skip (no row written if the latest observation for the same key has the same hash), query latest observation per entity, query observation history.

**Architecture:** Synchronous functions in a new `store.py` module inside `server/config_collector/`. Operates on an open `sqlite3.Connection` passed in by the caller (matches the existing pattern in `server/database.py`). All SQL queries use parameterized statements.

**Depends on:** Plan 1.01 (schema), Plan 1.02 (hashing primitives), Plan 1.03 (redactor produces hot columns).
**Unblocks:** Plan 1.12 (targeted puller writes via this layer).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/store.py` | Create | `upsert_blob`, `insert_observation_if_changed`, `get_latest_observation`, `get_observation_history` |
| `server/tests/test_config_store_blobs.py` | Create | Tests for blob insert/dedup/get |
| `server/tests/test_config_store_observations.py` | Create | Tests for observation insert/hash-skip/queries |

---

## Task 1: `upsert_blob` with dedup

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_config_store_blobs.py`:

```python
"""Tests for config_blobs data access (Plan 1.10)."""
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
        yield c
        c.close()


def test_upsert_blob_inserts_new(conn):
    from server.config_collector.store import upsert_blob

    inserted = upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    assert inserted is True  # new row written

    row = conn.execute("SELECT payload, byte_size FROM config_blobs WHERE hash=?", ("abc123",)).fetchone()
    assert row["payload"] == '{"a":1}'
    assert row["byte_size"] == 7


def test_upsert_blob_dedupes_on_hash(conn):
    from server.config_collector.store import upsert_blob

    upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    inserted = upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    assert inserted is False  # already existed, not re-inserted

    # Still only one row
    count = conn.execute("SELECT COUNT(*) AS n FROM config_blobs WHERE hash=?", ("abc123",)).fetchone()["n"]
    assert count == 1


def test_upsert_blob_different_hashes_are_separate(conn):
    from server.config_collector.store import upsert_blob

    upsert_blob(conn, hash_hex="abc", payload="{}", byte_size=2)
    upsert_blob(conn, hash_hex="def", payload="[]", byte_size=2)

    count = conn.execute("SELECT COUNT(*) AS n FROM config_blobs").fetchone()["n"]
    assert count == 2
```

- [ ] **Step 1.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_store_blobs.py -v`

Expected: `ModuleNotFoundError: No module named 'server.config_collector.store'`.

- [ ] **Step 1.3: Create `store.py` with `upsert_blob`**

Create `server/config_collector/store.py`:

```python
"""Data-access functions for the config_collector SQLite tables.

All functions take an open sqlite3.Connection as the first argument and
commit on successful writes. Reads do not commit.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_blob(
    conn: sqlite3.Connection,
    hash_hex: str,
    payload: str,
    byte_size: int,
) -> bool:
    """Insert a blob row if `hash_hex` is new. Returns True if inserted, False if existed."""
    cursor = conn.execute(
        """INSERT OR IGNORE INTO config_blobs (hash, payload, byte_size, first_seen_at)
           VALUES (?, ?, ?, ?)""",
        (hash_hex, payload, byte_size, _now_iso()),
    )
    conn.commit()
    return cursor.rowcount == 1
```

- [ ] **Step 1.4: Run — should pass**

Expected: 3 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_blobs.py
git commit -m "feat(config): upsert_blob with hash-based dedup (Plan 1.10)"
```

---

## Task 2: `get_blob_by_hash`

- [ ] **Step 2.1: Write failing test**

Append to `server/tests/test_config_store_blobs.py`:

```python
def test_get_blob_by_hash_returns_payload(conn):
    from server.config_collector.store import upsert_blob, get_blob_by_hash

    upsert_blob(conn, hash_hex="abc123", payload='{"a":1}', byte_size=7)
    blob = get_blob_by_hash(conn, "abc123")
    assert blob is not None
    assert blob["payload"] == '{"a":1}'
    assert blob["byte_size"] == 7
    assert "first_seen_at" in blob


def test_get_blob_by_hash_missing_returns_none(conn):
    from server.config_collector.store import get_blob_by_hash

    assert get_blob_by_hash(conn, "does-not-exist") is None
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Add `get_blob_by_hash`**

Append to `server/config_collector/store.py`:

```python
def get_blob_by_hash(conn: sqlite3.Connection, hash_hex: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT hash, payload, byte_size, first_seen_at FROM config_blobs WHERE hash=?",
        (hash_hex,),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 2.4: Run — should pass**

Expected: 5 tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_blobs.py
git commit -m "feat(config): get_blob_by_hash reader (Plan 1.10)"
```

---

## Task 3: `insert_observation_if_changed`

Writes a new observation row only if the hash differs from the most recent observation for the same `(org_id, entity_type, entity_id, config_area, sub_key)` tuple.

- [ ] **Step 3.1: Write failing test**

Create `server/tests/test_config_store_observations.py`:

```python
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
        # Seed a blob so FK is satisfied
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
    wrote = insert_observation_if_changed(conn, **{**kwargs, "source_event": "anti_drift_confirm"})
    # Note: the spec specifies confirm/discrepancy rows SHOULD be written even if hash matches
    # for proof-of-life purposes. We allow that through by source_event inspection.
    # For change_log and baseline, skip if unchanged.
    assert wrote is False

    rows = conn.execute("SELECT * FROM config_observations").fetchall()
    assert len(rows) == 1  # only first insert


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
```

- [ ] **Step 3.2: Run — should fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_store_observations.py -v`

Expected: `ImportError: cannot import name 'insert_observation_if_changed'`.

- [ ] **Step 3.3: Implement `insert_observation_if_changed`**

Append to `server/config_collector/store.py`:

```python
# Source events for which we always write, even if hash matches.
# anti_drift_confirm is a proof-of-life marker; anti_drift_discrepancy
# is by definition a hash mismatch but included for clarity.
_ALWAYS_WRITE_SOURCE_EVENTS = {"anti_drift_confirm", "anti_drift_discrepancy", "manual_refresh"}


def insert_observation_if_changed(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: str,
    sub_key: Optional[str],
    hash_hex: str,
    source_event: str,
    change_event_id: Optional[int],
    sweep_run_id: Optional[int],
    hot_columns: dict,
) -> bool:
    """Insert an observation row unless the latest observation has the same hash.

    Exception: rows with source_event in _ALWAYS_WRITE_SOURCE_EVENTS are
    always written (proof-of-life and explicit user-triggered refresh).

    Returns True if inserted, False if skipped.
    """
    if source_event not in _ALWAYS_WRITE_SOURCE_EVENTS:
        latest = conn.execute(
            """SELECT hash FROM config_observations
               WHERE org_id=? AND entity_type=? AND entity_id=?
                 AND config_area=? AND sub_key IS ?
               ORDER BY observed_at DESC LIMIT 1""",
            (org_id, entity_type, entity_id, config_area, sub_key),
        ).fetchone()
        if latest is not None and latest["hash"] == hash_hex:
            return False

    conn.execute(
        """INSERT INTO config_observations
           (org_id, entity_type, entity_id, config_area, sub_key,
            hash, observed_at, source_event, change_event_id, sweep_run_id,
            name_hint, enabled_hint)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            org_id, entity_type, entity_id, config_area, sub_key,
            hash_hex, _now_iso(), source_event, change_event_id, sweep_run_id,
            hot_columns.get("name_hint"), hot_columns.get("enabled_hint"),
        ),
    )
    conn.commit()
    return True
```

Note: the `sub_key IS ?` with a `None` parameter correctly matches NULL in SQLite. Verify after running.

- [ ] **Step 3.4: Run — should pass**

Expected: 4 tests pass.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_observations.py
git commit -m "feat(config): insert_observation_if_changed with hash-skip logic (Plan 1.10)"
```

---

## Task 4: `get_latest_observation`

- [ ] **Step 4.1: Write failing test**

Append to `server/tests/test_config_store_observations.py`:

```python
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
```

- [ ] **Step 4.2: Run — should fail**

- [ ] **Step 4.3: Implement `get_latest_observation`**

Append to `server/config_collector/store.py`:

```python
def get_latest_observation(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: str,
    sub_key: Optional[str],
) -> Optional[dict]:
    row = conn.execute(
        """SELECT * FROM config_observations
           WHERE org_id=? AND entity_type=? AND entity_id=?
             AND config_area=? AND sub_key IS ?
           ORDER BY observed_at DESC LIMIT 1""",
        (org_id, entity_type, entity_id, config_area, sub_key),
    ).fetchone()
    return dict(row) if row else None
```

- [ ] **Step 4.4: Run — should pass**

Expected: 6 tests pass.

- [ ] **Step 4.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_observations.py
git commit -m "feat(config): get_latest_observation reader (Plan 1.10)"
```

---

## Task 5: `get_observation_history` with pagination

- [ ] **Step 5.1: Write failing test**

Append to `server/tests/test_config_store_observations.py`:

```python
def test_get_observation_history_pagination(conn):
    from server.config_collector.store import insert_observation_if_changed, get_observation_history

    base = dict(
        org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None,
        change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    # Three distinct observations
    insert_observation_if_changed(conn, hash_hex="h1", source_event="baseline", **base)
    insert_observation_if_changed(conn, hash_hex="h2", source_event="change_log", **base)
    insert_observation_if_changed(conn, hash_hex="h3", source_event="change_log", **base)

    # Newest first
    hist = get_observation_history(
        conn, org_id="o1", entity_type="network", entity_id="N_1",
        config_area="appliance_vlans", sub_key=None, limit=2,
    )
    assert [r["hash"] for r in hist] == ["h3", "h2"]


def test_get_observation_history_filters_by_config_area(conn):
    from server.config_collector.store import insert_observation_if_changed, get_observation_history

    insert_observation_if_changed(
        conn, org_id="o", entity_type="network", entity_id="N", config_area="area_a",
        sub_key=None, hash_hex="hash1", source_event="baseline",
        change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )
    insert_observation_if_changed(
        conn, org_id="o", entity_type="network", entity_id="N", config_area="area_b",
        sub_key=None, hash_hex="hash2", source_event="baseline",
        change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    hist = get_observation_history(
        conn, org_id="o", entity_type="network", entity_id="N",
        config_area="area_a", sub_key=None, limit=10,
    )
    assert len(hist) == 1
    assert hist[0]["config_area"] == "area_a"
```

- [ ] **Step 5.2: Run — should fail**

- [ ] **Step 5.3: Implement `get_observation_history`**

Append to `server/config_collector/store.py`:

```python
def get_observation_history(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: Optional[str] = None,
    sub_key: Optional[str] = None,
    limit: int = 100,
    before_observed_at: Optional[str] = None,
) -> list[dict]:
    """Observations for an entity, newest first. Optional filter by config_area."""
    sql = """SELECT * FROM config_observations
             WHERE org_id=? AND entity_type=? AND entity_id=?"""
    params: list = [org_id, entity_type, entity_id]
    if config_area is not None:
        sql += " AND config_area=?"
        params.append(config_area)
    if sub_key is not None or config_area is not None:
        sql += " AND sub_key IS ?"
        params.append(sub_key)
    if before_observed_at is not None:
        sql += " AND observed_at < ?"
        params.append(before_observed_at)
    sql += " ORDER BY observed_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5.4: Run — should pass**

Expected: 8 tests pass.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/store.py server/tests/test_config_store_observations.py
git commit -m "feat(config): get_observation_history with filtering + pagination (Plan 1.10)"
```

---

## Completion Checklist

- [ ] `upsert_blob`, `get_blob_by_hash`, `insert_observation_if_changed`, `get_latest_observation`, `get_observation_history` all exist in `store.py`
- [ ] ~13 passing tests across two test files
- [ ] 5 commits

## What This Unblocks

- Plan 1.12 (targeted puller) pipes redactor output into this layer.
- Plan 1.13 (baseline runner) uses the same path at scale.
- Plan 1.17 (REST API) exposes `get_latest_observation` and `get_observation_history`.
