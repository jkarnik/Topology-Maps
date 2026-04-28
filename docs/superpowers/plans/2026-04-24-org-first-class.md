# Org First-Class in Topology Module — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Meraki org a first-class DB entity in the topology module so `org_id` is persisted and available to all consumers (including NR ingest) without requiring `.env` workarounds.

**Architecture:** Add an `orgs` table to `app.db`, add a nullable `org_id` FK column to `networks`, bump the schema to v3 with a safe in-place migration, then thread `orgId` through `save_snapshot`/`load_snapshot`, the frontend save payload, and the NR ingest scripts.

**Tech Stack:** Python stdlib `sqlite3`, FastAPI, React/TypeScript, pytest

---

### Task 1: DB schema migration (v2 → v3)

**Files:**
- Modify: `server/db.py`
- Create: `server/tests/test_db_snapshot.py`

**What this task delivers:** An `orgs(id, name)` table and a nullable `org_id` FK column on `networks`. Existing rows are left with `org_id = NULL` (populated on next sync). Schema version bumps to 3.

---

- [ ] **Step 1: Write the failing tests**

Create `server/tests/test_db_snapshot.py`:

```python
"""Tests for db.py schema and migration."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def patched_db(monkeypatch, tmp_path):
    """Fresh isolated db.py pointing at a temp file."""
    import importlib
    import server.db as db_mod
    monkeypatch.setattr(db_mod, "DB_PATH", tmp_path / "app.db")
    monkeypatch.setattr(db_mod, "_connection", None)
    db_mod.init_db()
    yield db_mod
    db_mod.close_db()
    monkeypatch.setattr(db_mod, "_connection", None)


def test_orgs_table_exists(patched_db):
    conn = patched_db._conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "orgs" in tables


def test_networks_has_org_id_column(patched_db):
    conn = patched_db._conn()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(networks)").fetchall()}
    assert "org_id" in cols


def test_schema_version_is_3(patched_db):
    assert patched_db.meta_get("schema_version") == "3"
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
python -m pytest server/tests/test_db_snapshot.py -v
```

Expected: 3 failures — `orgs` table missing, `org_id` column missing, schema version is `2`.

- [ ] **Step 3: Implement the migration in `db.py`**

In `init_db()`, replace the `executescript` block with:

```python
def init_db() -> None:
    """Open the connection and ensure all tables exist."""
    global _connection
    if _connection is not None:
        return
    _connection = _connect()
    with _write_lock:
        _connection.executescript(
            """
            -- Scalar metadata (orgId, orgName, selectedNetwork, lastUpdated, schema_version, …).
            CREATE TABLE IF NOT EXISTS meta (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- Org registry: one row per Meraki organisation.
            CREATE TABLE IF NOT EXISTS orgs (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            -- Flat Meraki networks list used to populate the dropdown.
            CREATE TABLE IF NOT EXISTS networks (
                id            TEXT PRIMARY KEY,
                name          TEXT NOT NULL,
                product_types TEXT NOT NULL,  -- JSON array
                org_id        TEXT REFERENCES orgs(id)
            );

            -- Per-network topology cache.
            CREATE TABLE IF NOT EXISTS topology_cache (
                cache_key  TEXT PRIMARY KEY,
                payload    TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        _migrate(_connection)
    logger.info("SQLite DB initialised at %s", DB_PATH)
```

Then add `_migrate` just above `init_db`:

```python
def _migrate(conn: sqlite3.Connection) -> None:
    """Apply incremental schema migrations based on schema_version in meta."""
    version_str = conn.execute(
        "SELECT value FROM meta WHERE key = 'schema_version'"
    ).fetchone()
    version = int(version_str[0]) if version_str and version_str[0] else 0

    if version < 3:
        # Add org_id column to networks if it doesn't exist yet.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(networks)").fetchall()}
        if "org_id" not in cols:
            conn.execute("ALTER TABLE networks ADD COLUMN org_id TEXT REFERENCES orgs(id)")
        conn.execute(
            "INSERT INTO meta(key, value) VALUES ('schema_version', '3') "
            "ON CONFLICT(key) DO UPDATE SET value = '3'"
        )
        conn.commit()
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
python -m pytest server/tests/test_db_snapshot.py -v
```

Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add server/db.py server/tests/test_db_snapshot.py
git commit -m "feat(db): add orgs table and org_id FK on networks (schema v3)"
```

### Task 2: `save_snapshot` / `load_snapshot` read and write `orgId`

**Files:**
- Modify: `server/db.py`
- Modify: `server/tests/test_db_snapshot.py`

**What this task delivers:** Callers that pass `orgId` in the snapshot dict have the org upserted into `orgs` and FK set on every network row. `load_snapshot` returns `orgId` in its dict. Existing callers that omit `orgId` continue to work unchanged.

---

- [ ] **Step 1: Add failing tests**

Append to `server/tests/test_db_snapshot.py`:

```python
def test_save_snapshot_upserts_org(patched_db):
    patched_db.save_snapshot({
        "version": 3,
        "orgId": "537758",
        "orgName": "New Relic",
        "networks": [{"id": "N_1", "name": "London", "productTypes": ["switch"]}],
        "selectedNetwork": None,
        "topology": {},
        "lastUpdated": None,
    })
    row = patched_db._conn().execute(
        "SELECT id, name FROM orgs WHERE id = '537758'"
    ).fetchone()
    assert row is not None
    assert row[1] == "New Relic"


def test_save_snapshot_sets_org_id_on_networks(patched_db):
    patched_db.save_snapshot({
        "version": 3,
        "orgId": "537758",
        "orgName": "New Relic",
        "networks": [{"id": "N_1", "name": "London", "productTypes": ["switch"]}],
        "selectedNetwork": None,
        "topology": {},
        "lastUpdated": None,
    })
    row = patched_db._conn().execute(
        "SELECT org_id FROM networks WHERE id = 'N_1'"
    ).fetchone()
    assert row[0] == "537758"


def test_load_snapshot_returns_org_id(patched_db):
    patched_db.save_snapshot({
        "version": 3,
        "orgId": "537758",
        "orgName": "New Relic",
        "networks": [{"id": "N_1", "name": "London", "productTypes": ["switch"]}],
        "selectedNetwork": None,
        "topology": {"N_1": {"l2": {"nodes": [], "edges": []}, "l3": {"subnets": [], "routes": []}, "deviceDetails": {}}},
        "lastUpdated": None,
    })
    result = patched_db.load_snapshot()
    assert result is not None
    assert result["orgId"] == "537758"


def test_save_snapshot_without_org_id_still_works(patched_db):
    """Backwards compatibility: callers that omit orgId must not break."""
    patched_db.save_snapshot({
        "version": 2,
        "orgName": "New Relic",
        "networks": [{"id": "N_2", "name": "Paris", "productTypes": []}],
        "selectedNetwork": None,
        "topology": {"N_2": {"l2": {"nodes": [], "edges": []}, "l3": {"subnets": [], "routes": []}, "deviceDetails": {}}},
        "lastUpdated": None,
    })
    result = patched_db.load_snapshot()
    assert result is not None
    assert result.get("orgId") is None
```

- [ ] **Step 2: Run tests to confirm new ones fail**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
python -m pytest server/tests/test_db_snapshot.py -v
```

Expected: the 4 new tests fail; the 3 from Task 1 still pass.

- [ ] **Step 3: Update `save_snapshot` in `db.py`**

In the `save_snapshot` function, after extracting locals from `snapshot`, add `org_id`:

```python
def save_snapshot(snapshot: dict[str, Any]) -> int:
    version = snapshot.get("version")
    org_id = snapshot.get("orgId")          # NEW
    org_name = snapshot.get("orgName")
    networks: list[dict[str, Any]] = snapshot.get("networks") or []
    selected_network = snapshot.get("selectedNetwork")
    topology: dict[str, dict] = snapshot.get("topology") or {}
    last_updated = snapshot.get("lastUpdated")

    with _write_lock:
        conn = _conn()
        try:
            conn.execute("BEGIN")

            # Upsert org row when org_id provided                            # NEW
            if org_id:                                                        # NEW
                conn.execute(                                                 # NEW
                    "INSERT INTO orgs(id, name) VALUES (?, ?) "               # NEW
                    "ON CONFLICT(id) DO UPDATE SET name = excluded.name",     # NEW
                    (org_id, org_name or ""),                                 # NEW
                )                                                             # NEW

            # Scalar meta
            for key, value in {
                "schema_version": str(version) if version is not None else None,
                "orgName": org_name,
                "selectedNetwork": selected_network,
                "lastUpdated": last_updated,
            }.items():
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )

            # Networks — full replace
            conn.execute("DELETE FROM networks")
            conn.executemany(
                "INSERT INTO networks(id, name, product_types, org_id) VALUES (?, ?, ?, ?)",  # CHANGED
                [
                    (
                        n.get("id"),
                        n.get("name"),
                        json.dumps(n.get("productTypes") or []),
                        org_id,                                               # NEW
                    )
                    for n in networks
                    if n.get("id")
                ],
            )

            # Topology cache — full replace
            conn.execute("DELETE FROM topology_cache")
            conn.executemany(
                "INSERT INTO topology_cache(cache_key, payload) VALUES (?, ?)",
                [(key, json.dumps(payload)) for key, payload in topology.items()],
            )

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return len(topology)
```

- [ ] **Step 4: Update `load_snapshot` in `db.py`**

In `load_snapshot`, read the org row and add `orgId` to the returned dict:

```python
def load_snapshot() -> Optional[dict[str, Any]]:
    conn = _conn()

    meta_rows = conn.execute("SELECT key, value FROM meta").fetchall()
    if not meta_rows:
        return None
    meta = {row["key"]: row["value"] for row in meta_rows}

    # Read org_id from the orgs table (one org per installation)           # NEW
    org_row = conn.execute("SELECT id FROM orgs LIMIT 1").fetchone()        # NEW
    org_id = org_row["id"] if org_row else None                             # NEW

    network_rows = conn.execute(
        "SELECT id, name, product_types FROM networks"
    ).fetchall()
    networks = [
        {
            "id": row["id"],
            "name": row["name"],
            "productTypes": json.loads(row["product_types"]),
        }
        for row in network_rows
    ]

    topology_rows = conn.execute(
        "SELECT cache_key, payload FROM topology_cache"
    ).fetchall()
    topology = {row["cache_key"]: json.loads(row["payload"]) for row in topology_rows}

    if not networks and not topology:
        return None

    return {
        "version": int(meta["schema_version"]) if meta.get("schema_version") else None,
        "orgId": org_id,                                                     # NEW
        "orgName": meta.get("orgName"),
        "networks": networks,
        "selectedNetwork": meta.get("selectedNetwork"),
        "topology": topology,
        "lastUpdated": meta.get("lastUpdated"),
    }
```

- [ ] **Step 5: Run all tests**

```bash
cd /Users/jkarnik/Code/Topology\ Maps
python -m pytest server/tests/test_db_snapshot.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add server/db.py server/tests/test_db_snapshot.py
git commit -m "feat(db): save_snapshot/load_snapshot persist and return orgId"
```

### Task 3: Frontend — thread `orgId` through state and save payload

**Files:**
- Modify: `ui/src/hooks/useMerakiTopology.ts`

**What this task delivers:** The frontend stores `orgId` alongside `orgName`, populates it from the `/api/meraki/status` response (which already returns `organizations[0].id`), includes it in the `saveSnapshot` POST body, and reads it back from the cache-load response.

No new tests — this is a stateful React hook wired to live API calls. Manual verification steps are listed instead.

---

- [ ] **Step 1: Add `orgId` state next to `orgName`**

In `useMerakiTopology.ts`, find the `orgName` state declaration (around line 157) and add `orgId` directly below it:

```typescript
  const [orgName, setOrgName] = useState<string | null>(
    bootCache?.orgName ?? null,
  );
  const [orgId, setOrgId] = useState<string | null>(   // NEW
    bootCache?.orgId ?? null,                            // NEW
  );                                                     // NEW
```

Also add `orgId` to the exported return object (find the existing `orgName` in the return and add the line below it):

```typescript
    orgName,
    orgId,    // NEW
```

And add it to the TypeScript interface — find where `orgName: string | null;` is declared in the hook's return type and add:

```typescript
  orgName: string | null;
  orgId: string | null;   // NEW
```

- [ ] **Step 2: Set `orgId` from the status response**

Find the block around line 216 where `setOrgName` is called from the status response:

```typescript
      if (statusData.organizations && statusData.organizations.length > 0) {
        setOrgName(statusData.organizations[0].name ?? null);
      } else if (statusData.org_name) {
        setOrgName(statusData.org_name);
      }
```

Replace with:

```typescript
      if (statusData.organizations && statusData.organizations.length > 0) {
        setOrgName(statusData.organizations[0].name ?? null);
        setOrgId(statusData.organizations[0].id ?? null);    // NEW
      } else if (statusData.org_name) {
        setOrgName(statusData.org_name);
      }
```

- [ ] **Step 3: Include `orgId` in the `saveSnapshot` payload**

Find the payload construction in `saveSnapshot` (around line 615):

```typescript
    const payload = {
      version: SCHEMA_VERSION,
      orgName,
      networks,
      selectedNetwork,
      topology: Object.fromEntries(cacheRef.current),
      lastUpdated: lastUpdated ? lastUpdated.toISOString() : null,
    };
```

Replace with:

```typescript
    const payload = {
      version: SCHEMA_VERSION,
      orgId,      // NEW
      orgName,
      networks,
      selectedNetwork,
      topology: Object.fromEntries(cacheRef.current),
      lastUpdated: lastUpdated ? lastUpdated.toISOString() : null,
    };
```

Also add `orgId` to the `useCallback` dependency array at the end of `saveSnapshot`:

```typescript
  }, [networks, orgId, orgName, selectedNetwork, lastUpdated]);
```

- [ ] **Step 4: Load `orgId` from the cache response**

Find the block around line 587 where `setOrgName` is called after loading the cache:

```typescript
      setNetworks(data.networks ?? []);
      setOrgName(data.orgName ?? null);
```

Replace with:

```typescript
      setNetworks(data.networks ?? []);
      setOrgName(data.orgName ?? null);
      setOrgId(data.orgId ?? null);    // NEW
```

- [ ] **Step 5: Build the frontend to catch type errors**

```bash
cd /Users/jkarnik/Code/Topology\ Maps/ui
npm run build 2>&1 | tail -20
```

Expected: build succeeds with no TypeScript errors.

- [ ] **Step 6: Manual verification**

Start the dev server:
```bash
cd /Users/jkarnik/Code/Topology\ Maps/ui
npm run dev
```

In the browser console, after the topology loads, run:
```javascript
// Check that orgId is non-null in the hook's returned state
// (visible via React DevTools or by temporarily logging it)
```

Then click "Save Snapshot" and confirm the POST body in the Network tab includes `"orgId": "<some value>"`.

- [ ] **Step 7: Commit**

```bash
git add ui/src/hooks/useMerakiTopology.ts
git commit -m "feat(ui): thread orgId through topology hook state and save payload"
```

### Task 4: NR ingest — read `orgId` from `load_snapshot()` instead of `.env`

**Files:**
- Modify: `nr_ingest/push_all_devices.py`

**What this task delivers:** The Phase 2 ingest script reads `org_id` from the DB snapshot (populated by Task 2) rather than requiring a `MERAKI_ORG_ID` env var. No change to `data_source.py` — `load_snapshot()` already returns `orgId` after Task 2.

---

- [ ] **Step 1: Update `push_all_devices.py` to include the org entity event**

Find the `main()` function in `nr_ingest/push_all_devices.py`. Add org event construction before the `all_events` assembly:

```python
def build_org_event(org_id: str, org_name: str) -> dict:
    return {
        "eventType": "MerakiOrganization",
        "instrumentation.provider": "kentik",
        "instrumentation.name": "meraki.organization",
        "org_id": org_id,
        "org_name": org_name,
        "tags.environment": "experimental",
        "tags.source": "topology-maps-app",
    }
```

Then in `main()`, after loading the snapshot, extract `org_id`:

```python
    snapshot = load_snapshot()
    org_id: str = snapshot.get("orgId") or ""
    org_name: str = snapshot.get("orgName") or ""

    if not org_id:
        print("WARNING: orgId not in snapshot — org entity will be skipped.")
        print("  Run a topology refresh and save snapshot first.")
        org_events = []
    else:
        org_events = [build_org_event(org_id, org_name)]
        print(f"Org: {org_name} (id={org_id})")
```

And change the final event assembly to include org:

```python
    all_events = org_events + device_events + site_events
```

Also update the success verification message to reflect the org entity:

```python
    print(f"  1. NRQL: FROM KSwitch, KFirewall, KAccessPoint, KNetwork, MerakiOrganization "
          f"SELECT count(*) FACET eventType SINCE 10 minutes ago")
    print(f"     Expected: 1 org, 11 firewalls, 21 switches, 117 APs, 10 networks")
```

- [ ] **Step 2: Verify the script runs without errors against the live DB**

```bash
cd /Users/jkarnik/Code/Topology\ Maps/nr_ingest
python push_all_devices.py 2>&1 | head -20
```

Expected output starts with:
```
Org: New Relic (id=<org_id>)
Device counts:
  access_point: 117
  ...
```

If `orgId not in snapshot` warning appears: run a topology refresh in the UI, save the snapshot, then re-run. The warning is expected on the existing DB before Task 3 is deployed.

- [ ] **Step 3: Commit**

```bash
git add nr_ingest/push_all_devices.py
git commit -m "feat(nr-ingest): add org entity event, read orgId from DB snapshot"
```
