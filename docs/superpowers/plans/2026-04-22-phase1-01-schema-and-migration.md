# Plan 1.01 — Schema & Migration

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution guideline (user directive):** Before executing ANY task below, evaluate whether that task can be split further into smaller, independently executable subtasks. Prefer doing less per turn over doing more. Commit frequently. If a tool call threatens to time out, break it into smaller operations.

**Goal:** Add four new SQLite tables (`config_blobs`, `config_observations`, `config_change_events`, `config_sweep_runs`) and their indexes to the existing database, with idempotent migration and a verification test.

**Architecture:** Extend the existing `server/database.py` `_create_tables()` function. Uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` so migration is naturally idempotent and safe to run on existing topology DBs. All new tables follow the patterns established by the existing `devices`, `edges`, `topology_snapshots`, and `connection_history` tables.

**Tech Stack:** Python 3.9+, sqlite3 (stdlib), pytest, pytest-asyncio.

**Spec reference:** [docs/superpowers/specs/2026-04-22-config-collection-phase1-design.md — Storage Schema section](../specs/2026-04-22-config-collection-phase1-design.md#storage-schema)

**Depends on:** None. This is a foundation plan — start here.

**Unblocks:** Plan 1.10 (storage: blobs + observations), Plan 1.11 (storage: events + sweep runs).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/database.py` | Modify | Extend `_create_tables()` with four new `CREATE TABLE IF NOT EXISTS` blocks and their indexes |
| `server/tests/test_config_schema.py` | Create | Migration verification tests: tables exist, indexes exist, FKs configured, idempotent re-run |

No new modules are created in this plan. Keeping the schema extension colocated with existing schema is the simpler option and follows the established pattern in this repo.

---

## Task 1: Set up test file scaffolding

**Files:**
- Create: `server/tests/test_config_schema.py`

- [ ] **Step 1.1: Create the test file with imports and fixtures**

Create `server/tests/test_config_schema.py`:

```python
"""Tests for config-collection schema migration (Plan 1.01)."""
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def fresh_db(monkeypatch):
    """Fresh SQLite DB for a single test; auto-cleaned."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        # Patch DB_PATH so get_connection() uses the temp DB
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        conn = database.get_connection()
        yield conn
        conn.close()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def test_scaffolding_loads():
    """Sanity check: test file imports and helpers resolve."""
    assert _table_exists is not None
    assert _index_exists is not None
```

- [ ] **Step 1.2: Run the sanity test to verify scaffolding works**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_scaffolding_loads -v`

Expected: `PASSED`. If it fails, check that `server/tests/__init__.py` exists (it does in this repo) and that `pytest` is runnable.

- [ ] **Step 1.3: Commit scaffolding**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_config_schema.py
git commit -m "test: scaffolding for config schema migration tests (Plan 1.01)"
```

---

## Task 2: Add `config_blobs` table

Content-addressed blob store. One row per unique redacted payload, keyed by its SHA-256 hash. Enables deduplication across observations.

**Files:**
- Modify: `server/database.py` (extend `_create_tables()`)
- Test: `server/tests/test_config_schema.py` (append new test)

- [ ] **Step 2.1: Write the failing test**

Append to `server/tests/test_config_schema.py`:

```python
def test_config_blobs_table_exists(fresh_db):
    """config_blobs table is created with the expected columns."""
    assert _table_exists(fresh_db, "config_blobs")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_blobs)")}
    assert set(cols.keys()) == {"hash", "payload", "byte_size", "first_seen_at"}
    assert cols["hash"]["pk"] == 1                  # hash is PRIMARY KEY
    assert cols["hash"]["notnull"] == 0             # PK implies NOT NULL; PRAGMA reports 0 for text PK
    assert cols["payload"]["notnull"] == 1
    assert cols["byte_size"]["notnull"] == 1
    assert cols["first_seen_at"]["notnull"] == 1
    assert cols["byte_size"]["type"].upper() == "INTEGER"
```

- [ ] **Step 2.2: Run the test to verify it fails**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_blobs_table_exists -v`

Expected: `FAILED` — `config_blobs` does not yet exist, so `_table_exists` returns `False`.

- [ ] **Step 2.3: Add the table to `_create_tables()`**

In `server/database.py`, locate the final closing `"""` of the `executescript` call inside `_create_tables()` (currently at the line after the existing `CREATE INDEX IF NOT EXISTS idx_connection_history_device …` index). Insert these lines **before** the closing `"""`:

```sql
        CREATE TABLE IF NOT EXISTS config_blobs (
            hash TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            byte_size INTEGER NOT NULL,
            first_seen_at TEXT NOT NULL
        );
```

Note the 8-space indentation to match the existing executescript content.

- [ ] **Step 2.4: Run the test to verify it passes**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_blobs_table_exists -v`

Expected: `PASSED`.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/database.py server/tests/test_config_schema.py
git commit -m "feat(schema): add config_blobs table (Plan 1.01)"
```

---

## Task 3: Add `config_observations` table

Every observation writes one row here. Points at a blob via `hash`. Carries denormalized hot columns (`name_hint`, `enabled_hint`) populated at insert time by the redactor in a later plan.

**Files:**
- Modify: `server/database.py`
- Test: `server/tests/test_config_schema.py`

- [ ] **Step 3.1: Write the failing test**

Append to `server/tests/test_config_schema.py`:

```python
def test_config_observations_table_exists(fresh_db):
    """config_observations table has expected columns, types, and FKs."""
    assert _table_exists(fresh_db, "config_observations")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_observations)")}
    expected = {
        "id", "org_id", "entity_type", "entity_id", "config_area", "sub_key",
        "hash", "observed_at", "source_event", "change_event_id", "sweep_run_id",
        "name_hint", "enabled_hint",
    }
    assert set(cols.keys()) == expected

    # Primary key is auto-incrementing id
    assert cols["id"]["pk"] == 1
    assert cols["id"]["type"].upper() == "INTEGER"

    # Required fields
    for required in ("org_id", "entity_type", "entity_id", "config_area", "hash", "observed_at", "source_event"):
        assert cols[required]["notnull"] == 1, f"{required} must be NOT NULL"

    # Optional fields
    for optional in ("sub_key", "change_event_id", "sweep_run_id", "name_hint", "enabled_hint"):
        assert cols[optional]["notnull"] == 0, f"{optional} must be nullable"
```

- [ ] **Step 3.2: Run the test to verify it fails**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_observations_table_exists -v`

Expected: `FAILED` — table does not yet exist.

- [ ] **Step 3.3: Add the table to `_create_tables()`**

In `server/database.py`, insert after the `config_blobs` table block (still inside the `executescript`):

```sql
        CREATE TABLE IF NOT EXISTS config_observations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            config_area TEXT NOT NULL,
            sub_key TEXT,
            hash TEXT NOT NULL REFERENCES config_blobs(hash),
            observed_at TEXT NOT NULL,
            source_event TEXT NOT NULL,
            change_event_id INTEGER,
            sweep_run_id INTEGER,
            name_hint TEXT,
            enabled_hint INTEGER
        );
```

Foreign keys to `config_change_events(id)` and `config_sweep_runs(id)` are intentionally omitted here because those tables don't exist yet in Task 3 execution order. They are added as constraints only via `PRAGMA foreign_keys=ON` at runtime plus application-level integrity. Alternatively, we could add them inline once Tasks 4 and 5 land; see Task 6 for the verification that confirms no stray FK issues.

- [ ] **Step 3.4: Run the test to verify it passes**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_observations_table_exists -v`

Expected: `PASSED`.

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/database.py server/tests/test_config_schema.py
git commit -m "feat(schema): add config_observations table (Plan 1.01)"
```

---

## Task 4: Add `config_change_events` table

Raw Meraki change-log events. Drives the incremental flow and seeds the Phase 2 timeline. Includes a UNIQUE constraint to dedupe events observed across overlapping poll windows.

**Files:**
- Modify: `server/database.py`
- Test: `server/tests/test_config_schema.py`

- [ ] **Step 4.1: Write the failing test**

Append to `server/tests/test_config_schema.py`:

```python
def test_config_change_events_table_exists(fresh_db):
    """config_change_events table has expected columns and unique dedup index."""
    assert _table_exists(fresh_db, "config_change_events")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_change_events)")}
    expected = {
        "id", "org_id", "ts", "admin_id", "admin_name", "admin_email",
        "network_id", "network_name", "ssid_number", "ssid_name",
        "page", "label", "old_value", "new_value",
        "client_id", "client_description",
        "raw_json", "fetched_at",
    }
    assert set(cols.keys()) == expected
    assert cols["id"]["pk"] == 1
    assert cols["org_id"]["notnull"] == 1
    assert cols["ts"]["notnull"] == 1
    assert cols["raw_json"]["notnull"] == 1
    assert cols["fetched_at"]["notnull"] == 1


def test_config_change_events_dedup_unique_constraint(fresh_db):
    """Inserting the same (org_id, ts, network_id, label, old_value, new_value) twice fails."""
    insert_sql = """
        INSERT INTO config_change_events
          (org_id, ts, network_id, label, old_value, new_value, raw_json, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    args = ("org1", "2026-04-22T10:00:00Z", "N_1", "VLAN", "10", "20", "{}", "2026-04-22T10:01:00Z")
    fresh_db.execute(insert_sql, args)
    fresh_db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        fresh_db.execute(insert_sql, args)
        fresh_db.commit()
```

- [ ] **Step 4.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_change_events_table_exists server/tests/test_config_schema.py::test_config_change_events_dedup_unique_constraint -v`

Expected: Both `FAILED` — table does not yet exist.

- [ ] **Step 4.3: Add the table to `_create_tables()`**

In `server/database.py`, insert after the `config_observations` block:

```sql
        CREATE TABLE IF NOT EXISTS config_change_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            ts TEXT NOT NULL,
            admin_id TEXT,
            admin_name TEXT,
            admin_email TEXT,
            network_id TEXT,
            network_name TEXT,
            ssid_number INTEGER,
            ssid_name TEXT,
            page TEXT,
            label TEXT,
            old_value TEXT,
            new_value TEXT,
            client_id TEXT,
            client_description TEXT,
            raw_json TEXT NOT NULL,
            fetched_at TEXT NOT NULL,
            UNIQUE(org_id, ts, network_id, label, old_value, new_value)
        );
```

- [ ] **Step 4.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_change_events_table_exists server/tests/test_config_schema.py::test_config_change_events_dedup_unique_constraint -v`

Expected: Both `PASSED`.

- [ ] **Step 4.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/database.py server/tests/test_config_schema.py
git commit -m "feat(schema): add config_change_events table with dedup constraint (Plan 1.01)"
```

---

## Task 5: Add `config_sweep_runs` table

Tracks baseline, anti-drift, and incremental sweep metadata for progress, resumability, and observability.

**Files:**
- Modify: `server/database.py`
- Test: `server/tests/test_config_schema.py`

- [ ] **Step 5.1: Write the failing test**

Append to `server/tests/test_config_schema.py`:

```python
def test_config_sweep_runs_table_exists(fresh_db):
    """config_sweep_runs table has expected columns and defaults."""
    assert _table_exists(fresh_db, "config_sweep_runs")

    cols = {row["name"]: row for row in fresh_db.execute("PRAGMA table_info(config_sweep_runs)")}
    expected = {
        "id", "org_id", "kind", "status",
        "started_at", "completed_at",
        "total_calls", "completed_calls", "failed_calls", "skipped_calls",
        "error_summary",
    }
    assert set(cols.keys()) == expected
    assert cols["id"]["pk"] == 1
    assert cols["org_id"]["notnull"] == 1
    assert cols["kind"]["notnull"] == 1
    assert cols["status"]["notnull"] == 1


def test_config_sweep_runs_counter_defaults(fresh_db):
    """Inserting with only required fields leaves counters at 0."""
    fresh_db.execute(
        "INSERT INTO config_sweep_runs (org_id, kind, status) VALUES (?, ?, ?)",
        ("org1", "baseline", "queued"),
    )
    fresh_db.commit()
    row = fresh_db.execute(
        "SELECT completed_calls, failed_calls, skipped_calls FROM config_sweep_runs"
    ).fetchone()
    assert row["completed_calls"] == 0
    assert row["failed_calls"] == 0
    assert row["skipped_calls"] == 0
```

- [ ] **Step 5.2: Run the tests to verify they fail**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_sweep_runs_table_exists server/tests/test_config_schema.py::test_config_sweep_runs_counter_defaults -v`

Expected: Both `FAILED` — table does not yet exist.

- [ ] **Step 5.3: Add the table to `_create_tables()`**

In `server/database.py`, insert after the `config_change_events` block:

```sql
        CREATE TABLE IF NOT EXISTS config_sweep_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            total_calls INTEGER,
            completed_calls INTEGER DEFAULT 0,
            failed_calls INTEGER DEFAULT 0,
            skipped_calls INTEGER DEFAULT 0,
            error_summary TEXT
        );
```

- [ ] **Step 5.4: Run the tests to verify they pass**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_sweep_runs_table_exists server/tests/test_config_schema.py::test_config_sweep_runs_counter_defaults -v`

Expected: Both `PASSED`.

- [ ] **Step 5.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/database.py server/tests/test_config_schema.py
git commit -m "feat(schema): add config_sweep_runs table with counter defaults (Plan 1.01)"
```

---

## Task 6: Add indexes for all four new tables

Indexes support the queries defined in the spec: latest observation per entity/area, observations by area over time, hash-based joins, change events by org/network, and sweep runs by org/kind.

**Files:**
- Modify: `server/database.py`
- Test: `server/tests/test_config_schema.py`

- [ ] **Step 6.1: Write the failing test**

Append to `server/tests/test_config_schema.py`:

```python
def test_config_indexes_exist(fresh_db):
    """All Plan 1.01 indexes are created."""
    expected_indexes = {
        "idx_obs_entity_latest",
        "idx_obs_area_time",
        "idx_obs_hash",
        "idx_events_org_ts",
        "idx_events_network",
        "idx_runs_org_kind",
    }
    for idx_name in expected_indexes:
        assert _index_exists(fresh_db, idx_name), f"Missing index: {idx_name}"
```

- [ ] **Step 6.2: Run the test to verify it fails**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_indexes_exist -v`

Expected: `FAILED` — none of the indexes yet exist.

- [ ] **Step 6.3: Add the indexes to `_create_tables()`**

In `server/database.py`, insert after the `config_sweep_runs` block (still inside the `executescript`):

```sql
        CREATE INDEX IF NOT EXISTS idx_obs_entity_latest
            ON config_observations(org_id, entity_type, entity_id, config_area, sub_key, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_obs_area_time
            ON config_observations(config_area, observed_at DESC);
        CREATE INDEX IF NOT EXISTS idx_obs_hash
            ON config_observations(hash);
        CREATE INDEX IF NOT EXISTS idx_events_org_ts
            ON config_change_events(org_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_events_network
            ON config_change_events(network_id, ts DESC);
        CREATE INDEX IF NOT EXISTS idx_runs_org_kind
            ON config_sweep_runs(org_id, kind, started_at DESC);
```

- [ ] **Step 6.4: Run the test to verify it passes**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_config_indexes_exist -v`

Expected: `PASSED`.

- [ ] **Step 6.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/database.py server/tests/test_config_schema.py
git commit -m "feat(schema): add indexes for config tables (Plan 1.01)"
```

---

## Task 7: Verify migration idempotency

Running `get_connection()` twice on the same DB must not raise or duplicate anything. This is the core safety property that makes the migration safe for existing production DBs.

**Files:**
- Test: `server/tests/test_config_schema.py`

- [ ] **Step 7.1: Write the test**

Append to `server/tests/test_config_schema.py`:

```python
def test_migration_is_idempotent(monkeypatch):
    """Running get_connection() twice on the same DB file does not error or duplicate state."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)

        conn1 = database.get_connection()
        # Seed a row in config_blobs
        conn1.execute(
            "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?, ?, ?, ?)",
            ("abc123", "{}", 2, "2026-04-22T10:00:00Z"),
        )
        conn1.commit()
        conn1.close()

        # Second open should re-run _create_tables without error and preserve data
        conn2 = database.get_connection()
        row = conn2.execute(
            "SELECT hash, payload FROM config_blobs WHERE hash='abc123'"
        ).fetchone()
        assert row is not None
        assert row["payload"] == "{}"
        conn2.close()
```

- [ ] **Step 7.2: Run the test — should pass immediately**

Because `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` are idempotent by construction, this test should pass without any code changes.

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_migration_is_idempotent -v`

Expected: `PASSED`. If it fails, the migration is using an incorrect pattern — investigate by checking for `CREATE TABLE` (without `IF NOT EXISTS`) in `server/database.py`.

- [ ] **Step 7.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_config_schema.py
git commit -m "test(schema): verify config migration idempotency (Plan 1.01)"
```

---

## Task 8: Verify existing tables are untouched by the migration

Regression guard — adding config tables must not break the existing topology schema.

**Files:**
- Test: `server/tests/test_config_schema.py`

- [ ] **Step 8.1: Write the test**

Append to `server/tests/test_config_schema.py`:

```python
def test_existing_tables_still_work(fresh_db):
    """devices, edges, topology_snapshots, connection_history are unaffected by the migration."""
    for existing in ("devices", "edges", "topology_snapshots", "connection_history"):
        assert _table_exists(fresh_db, existing), f"Missing existing table: {existing}"

    # Existing indexes still present
    for idx in (
        "idx_edges_source",
        "idx_edges_target",
        "idx_devices_type",
        "idx_connection_history_device",
    ):
        assert _index_exists(fresh_db, idx), f"Missing existing index: {idx}"

    # Sanity insert into an existing table still works
    fresh_db.execute(
        """INSERT INTO devices (id, type, model, ip, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        ("dev1", "switch", "MS225-48LP", "192.0.2.1", "2026-04-22T10:00:00Z"),
    )
    fresh_db.commit()
    row = fresh_db.execute("SELECT id FROM devices WHERE id='dev1'").fetchone()
    assert row["id"] == "dev1"
```

- [ ] **Step 8.2: Run the test — should pass immediately**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py::test_existing_tables_still_work -v`

Expected: `PASSED`.

- [ ] **Step 8.3: Run the full schema test suite one last time**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/test_config_schema.py -v`

Expected: All 9 tests pass.

- [ ] **Step 8.4: Final commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_config_schema.py
git commit -m "test(schema): regression guard for existing topology tables (Plan 1.01)"
```

---

## Completion Checklist

When all tasks above are complete, verify:

- [ ] All 9 tests in `server/tests/test_config_schema.py` pass
- [ ] Full test suite still passes: `cd "/Users/jkarnik/Code/Topology Maps" && pytest server/tests/ -v`
- [ ] Existing DB at `data/topology.db` (if present) opens without error after the migration
- [ ] 7 commits on the branch, one per task (Tasks 1–6 have 1 commit each; Task 7 and Task 8 have 1 commit each, with the last being `test(schema): regression guard ...`)

## What This Plan Unblocks

- Plan 1.10 (`storage: blobs + observations`) can begin — it inserts into and queries `config_blobs` and `config_observations`.
- Plan 1.11 (`storage: change events + sweep runs`) can begin — it operates on the two remaining new tables.

## Out of Scope for This Plan

- Insert/update/query helper functions for config tables — those live in Plans 1.10 and 1.11.
- FK constraint linking `config_observations.change_event_id → config_change_events.id` — intentionally not declared at schema time; application-layer integrity is sufficient, and adding the FK after initial migration would require table rebuild (SQLite limitation). Can be revisited in a future migration plan if needed.
- Any data migration from existing topology snapshots into the new config schema.






