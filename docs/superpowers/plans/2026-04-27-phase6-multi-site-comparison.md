# Phase 6 — Multi-Site & Template Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add four read-only features to ConfigBrowser: side-by-side network comparison, a coverage dashboard, template extraction (promote-a-network), and template scoring.

**Architecture:** Two new SQLite tables (`config_templates`, `config_template_areas`) reference existing `config_blobs` by hash — no content duplication. Five new endpoints added to the existing `/api/config` router. A new "Compare" tab with three pill-segmented sub-views is added to `ConfigBrowser`. Scoring is computed on-demand using the existing `compute_diff` engine from Phase 2.

**Tech Stack:** Python 3.11, FastAPI, SQLite (server); React 18, TypeScript, Tailwind (frontend); pytest + FastAPI TestClient (tests).

---

## File Map

### Backend — new/modified
| File | Change |
|---|---|
| `server/database.py` | Add `config_templates` + `config_template_areas` table DDL to `_create_tables` |
| `server/config_collector/store.py` | Add 5 new store functions for templates + coverage |
| `server/routes/config.py` | Add 5 new route handlers |
| `server/tests/test_config_store_templates.py` | New: store-layer tests |
| `server/tests/test_config_api_compare.py` | New: API-layer tests |

### Frontend — new files
| File | Purpose |
|---|---|
| `ui/src/api/compare.ts` | Fetch wrappers for all 5 Phase 6 endpoints |
| `ui/src/hooks/useNetworkCompare.ts` | State + fetch for `/compare/networks` |
| `ui/src/hooks/useCoverage.ts` | State + fetch for `/coverage` |
| `ui/src/hooks/useTemplates.ts` | State + mutations for templates CRUD |
| `ui/src/hooks/useTemplateScores.ts` | State + fetch for `/templates/{id}/scores` |
| `ui/src/components/ConfigBrowser/CompareTab.tsx` | Tab shell with pill segmented control |
| `ui/src/components/ConfigBrowser/CompareNetworksView.tsx` | Sub-view 1 |
| `ui/src/components/ConfigBrowser/CoverageView.tsx` | Sub-view 2 |
| `ui/src/components/ConfigBrowser/TemplatesView.tsx` | Sub-view 3 |

### Frontend — modified
| File | Change |
|---|---|
| `ui/src/types/config.ts` | Add Phase 6 types |
| `ui/src/components/ConfigBrowser/ConfigBrowser.tsx` | Add Compare tab |
| `ui/src/components/ConfigBrowser/index.ts` | Re-export new components |

---

## Task 1: Add DB tables for templates

**Files:**
- Modify: `server/database.py` (inside `_create_tables` executescript)

- [ ] **Step 1: Add the two CREATE TABLE statements to the executescript in `_create_tables`**

In `server/database.py`, inside the `conn.executescript("""...""")` block (after the `config_sweep_runs` table and before the `CREATE INDEX` lines), add:

```sql
        CREATE TABLE IF NOT EXISTS config_templates (
            id                   INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id               TEXT NOT NULL,
            name                 TEXT NOT NULL,
            source_network_id    TEXT NOT NULL,
            source_network_name  TEXT,
            created_at           TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS config_template_areas (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id  INTEGER NOT NULL REFERENCES config_templates(id) ON DELETE CASCADE,
            config_area  TEXT NOT NULL,
            sub_key      TEXT,
            blob_hash    TEXT NOT NULL REFERENCES config_blobs(hash)
        );

        CREATE INDEX IF NOT EXISTS idx_template_areas_template
            ON config_template_areas(template_id);
```

- [ ] **Step 2: Verify tables are created**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python - <<'EOF'
from server.database import get_connection
conn = get_connection()
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'config_template%'").fetchall()
print([r[0] for r in tables])
conn.close()
EOF
```
Expected: `['config_templates', 'config_template_areas']`

- [ ] **Step 3: Commit**

```bash
git add server/database.py
git commit -m "feat(phase6): add config_templates and config_template_areas tables"
```

---

## Task 2: Add store functions for templates

**Files:**
- Modify: `server/config_collector/store.py`
- Create: `server/tests/test_config_store_templates.py`

- [ ] **Step 1: Write failing tests**

Create `server/tests/test_config_store_templates.py`:

```python
"""Tests for Phase 6 template store functions."""
from __future__ import annotations
import tempfile
from pathlib import Path
import pytest
from server import database
from server.config_collector import store


@pytest.fixture
def conn(monkeypatch, tmp_path):
    db_path = tmp_path / "test.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    c = database.get_connection()
    yield c
    c.close()


def _seed_blob(conn, payload: str = '{"ssid": 1}') -> str:
    import hashlib
    h = hashlib.sha256(payload.encode()).hexdigest()
    store.upsert_blob(conn, h, payload, len(payload))
    return h


def _seed_observation(conn, org_id, network_id, config_area, blob_hash):
    store.insert_observation_if_changed(
        conn,
        org_id=org_id,
        entity_type="network",
        entity_id=network_id,
        config_area=config_area,
        sub_key=None,
        hash_hex=blob_hash,
        source_event="baseline",
        change_event_id=None,
        sweep_run_id=None,
        hot_columns={},
    )


def test_create_and_list_template(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)

    tmpl = store.create_template(conn, org_id="org1", name="Standard Retail", network_id="net1", network_name="Store 7")
    assert tmpl["id"] > 0
    assert tmpl["name"] == "Standard Retail"
    assert tmpl["source_network_id"] == "net1"
    assert len(tmpl["areas"]) == 1
    assert tmpl["areas"][0]["config_area"] == "wireless_ssids"
    assert tmpl["areas"][0]["blob_hash"] == h

    templates = store.list_templates(conn, org_id="org1")
    assert len(templates) == 1
    assert templates[0]["id"] == tmpl["id"]


def test_delete_template(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)
    tmpl = store.create_template(conn, org_id="org1", name="T1", network_id="net1", network_name="Store 7")
    store.delete_template(conn, template_id=tmpl["id"])
    assert store.list_templates(conn, org_id="org1") == []
    areas = conn.execute("SELECT * FROM config_template_areas WHERE template_id=?", (tmpl["id"],)).fetchall()
    assert list(areas) == []


def test_get_template_areas(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)
    tmpl = store.create_template(conn, org_id="org1", name="T1", network_id="net1", network_name="Store 7")
    areas = store.get_template_areas(conn, template_id=tmpl["id"])
    assert len(areas) == 1
    assert areas[0]["blob_hash"] == h


def test_delete_nonexistent_template_is_noop(conn):
    store.delete_template(conn, template_id=9999)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/test_config_store_templates.py -v 2>&1 | head -30
```
Expected: `AttributeError: module 'server.config_collector.store' has no attribute 'create_template'`

- [ ] **Step 3: Add store functions to `server/config_collector/store.py`**

Append to the end of `server/config_collector/store.py`:

```python


# ── Phase 6: Templates ────────────────────────────────────────────────────────

def create_template(
    conn: sqlite3.Connection,
    *,
    org_id: str,
    name: str,
    network_id: str,
    network_name: Optional[str],
) -> dict:
    """Promote a network snapshot to a template. Returns the full template dict."""
    now = _now_iso()
    cursor = conn.execute(
        """INSERT INTO config_templates (org_id, name, source_network_id, source_network_name, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (org_id, name, network_id, network_name, now),
    )
    template_id = cursor.lastrowid

    rows = conn.execute(
        """SELECT config_area, sub_key, hash
           FROM config_observations
           WHERE org_id=? AND entity_type='network' AND entity_id=?
           GROUP BY config_area, sub_key
           HAVING MAX(observed_at)""",
        (org_id, network_id),
    ).fetchall()

    areas = []
    for row in rows:
        conn.execute(
            """INSERT INTO config_template_areas (template_id, config_area, sub_key, blob_hash)
               VALUES (?, ?, ?, ?)""",
            (template_id, row["config_area"], row["sub_key"], row["hash"]),
        )
        areas.append({"config_area": row["config_area"], "sub_key": row["sub_key"], "blob_hash": row["hash"]})

    conn.commit()
    return {
        "id": template_id,
        "org_id": org_id,
        "name": name,
        "source_network_id": network_id,
        "source_network_name": network_name,
        "created_at": now,
        "areas": areas,
    }


def list_templates(conn: sqlite3.Connection, *, org_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM config_templates WHERE org_id=? ORDER BY created_at DESC",
        (org_id,),
    ).fetchall()
    templates = []
    for row in rows:
        areas = conn.execute(
            "SELECT config_area, sub_key, blob_hash FROM config_template_areas WHERE template_id=?",
            (row["id"],),
        ).fetchall()
        t = dict(row)
        t["areas"] = [dict(a) for a in areas]
        templates.append(t)
    return templates


def get_template_areas(conn: sqlite3.Connection, *, template_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM config_template_areas WHERE template_id=?",
        (template_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_template(conn: sqlite3.Connection, *, template_id: int) -> None:
    conn.execute("DELETE FROM config_templates WHERE id=?", (template_id,))
    conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/test_config_store_templates.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add server/config_collector/store.py server/tests/test_config_store_templates.py
git commit -m "feat(phase6): add template store functions + tests"
```

---

## Task 3: Add coverage store function

**Files:**
- Modify: `server/config_collector/store.py`
- Modify: `server/tests/test_config_store_templates.py` (append test)

- [ ] **Step 1: Append a failing test to `server/tests/test_config_store_templates.py`**

```python
def test_get_coverage(conn):
    h = _seed_blob(conn)
    _seed_observation(conn, "org1", "net1", "wireless_ssids", h)
    _seed_observation(conn, "org1", "net2", "wireless_ssids", h)
    _seed_observation(conn, "org1", "net1", "appliance_vlans", h)

    coverage = store.get_coverage(conn, org_id="org1")
    areas = {a["config_area"]: a for a in coverage}

    assert areas["wireless_ssids"]["network_count"] == 2
    assert areas["wireless_ssids"]["network_total"] == 2
    assert areas["wireless_ssids"]["missing_networks"] == []

    assert areas["appliance_vlans"]["network_count"] == 1
    assert areas["appliance_vlans"]["network_total"] == 2
    assert len(areas["appliance_vlans"]["missing_networks"]) == 1
    assert areas["appliance_vlans"]["missing_networks"][0]["id"] == "net2"
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/test_config_store_templates.py::test_get_coverage -v 2>&1 | head -20
```
Expected: `AttributeError: ... has no attribute 'get_coverage'`

- [ ] **Step 3: Add `get_coverage` to `store.py`**

Append to the end of `server/config_collector/store.py`:

```python


def get_coverage(conn: sqlite3.Connection, *, org_id: str) -> list[dict]:
    """Return per-config-area coverage counts for all networks in an org."""
    all_nets = conn.execute(
        """SELECT DISTINCT entity_id, MAX(name_hint) as name_hint
           FROM config_observations
           WHERE org_id=? AND entity_type='network'
           GROUP BY entity_id""",
        (org_id,),
    ).fetchall()
    all_net_ids = {r["entity_id"] for r in all_nets}
    net_name_map = {r["entity_id"]: r["name_hint"] for r in all_nets}
    network_total = len(all_net_ids)

    area_rows = conn.execute(
        """SELECT config_area, entity_id
           FROM config_observations
           WHERE org_id=? AND entity_type='network'
           GROUP BY config_area, entity_id""",
        (org_id,),
    ).fetchall()

    from collections import defaultdict
    area_nets: dict[str, set] = defaultdict(set)
    for r in area_rows:
        area_nets[r["config_area"]].add(r["entity_id"])

    device_rows = conn.execute(
        """SELECT config_area, entity_id, MAX(name_hint) as name_hint
           FROM config_observations
           WHERE org_id=? AND entity_type='device'
           GROUP BY config_area, entity_id""",
        (org_id,),
    ).fetchall()

    area_devices: dict[str, list] = defaultdict(list)
    for r in device_rows:
        area_devices[r["config_area"]].append({"id": r["entity_id"], "name": r["name_hint"]})

    results = []
    for area, present_nets in sorted(area_nets.items()):
        missing = [
            {"id": nid, "name": net_name_map.get(nid)}
            for nid in sorted(all_net_ids - present_nets)
        ]
        results.append({
            "config_area": area,
            "network_count": len(present_nets),
            "network_total": network_total,
            "missing_networks": missing,
            "device_breakdown": area_devices.get(area, []),
        })
    return results
```

- [ ] **Step 4: Run all store tests**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/test_config_store_templates.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add server/config_collector/store.py server/tests/test_config_store_templates.py
git commit -m "feat(phase6): add get_coverage store function + test"
```

---

## Task 4: Add backend API endpoints

**Files:**
- Modify: `server/routes/config.py`
- Create: `server/tests/test_config_api_compare.py`

- [ ] **Step 1: Write failing API tests**

Create `server/tests/test_config_api_compare.py`:

```python
"""Tests for Phase 6 compare/coverage/template API endpoints."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from server import database
from server.config_collector import store


@pytest.fixture
def app(monkeypatch, tmp_path):
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.get_connection().close()
    from fastapi import FastAPI
    from server.routes import config as config_routes
    import importlib
    importlib.reload(config_routes)
    app = FastAPI()
    app.include_router(config_routes.router)
    yield app


@pytest.fixture
def client(app):
    return TestClient(app)


def _seed(monkeypatch, tmp_path):
    """Returns a seeded (conn, h1, h2) tuple for use in tests."""
    db_path = tmp_path / "topology.db"
    monkeypatch.setattr(database, "DB_PATH", db_path)
    conn = database.get_connection()
    payload_a = json.dumps({"ssid": 1})
    payload_b = json.dumps({"ssid": 2})
    import hashlib
    h1 = hashlib.sha256(payload_a.encode()).hexdigest()
    h2 = hashlib.sha256(payload_b.encode()).hexdigest()
    store.upsert_blob(conn, h1, payload_a, len(payload_a))
    store.upsert_blob(conn, h2, payload_b, len(payload_b))
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net1", config_area="wireless_ssids", sub_key=None, hash_hex=h1,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={"name_hint": "Store 7"})
    store.insert_observation_if_changed(conn, org_id="org1", entity_type="network",
        entity_id="net2", config_area="wireless_ssids", sub_key=None, hash_hex=h2,
        source_event="baseline", change_event_id=None, sweep_run_id=None, hot_columns={"name_hint": "Store 42"})
    conn.close()
    return h1, h2


def test_list_templates_empty(client):
    resp = client.get("/api/config/templates?org_id=org1")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_and_delete_template(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    resp = client.post("/api/config/templates", json={"org_id": "org1", "name": "Standard Retail", "network_id": "net1"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Standard Retail"
    assert len(body["areas"]) == 1
    tmpl_id = body["id"]

    resp = client.get("/api/config/templates?org_id=org1")
    assert len(resp.json()) == 1

    resp = client.delete(f"/api/config/templates/{tmpl_id}")
    assert resp.status_code == 200
    assert client.get("/api/config/templates?org_id=org1").json() == []


def test_compare_networks(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    resp = client.get("/api/config/compare/networks?org_id=org1&network_a=net1&network_b=net2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["differing_areas"] == 1
    assert body["areas"][0]["status"] == "differs"


def test_coverage(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    resp = client.get("/api/config/coverage?org_id=org1")
    assert resp.status_code == 200
    areas = resp.json()["areas"]
    assert len(areas) == 1
    assert areas[0]["config_area"] == "wireless_ssids"
    assert areas[0]["network_count"] == 2


def test_template_scores(client, monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    # Create template from net1
    tmpl = client.post("/api/config/templates", json={"org_id": "org1", "name": "T1", "network_id": "net1"}).json()
    resp = client.get(f"/api/config/templates/{tmpl['id']}/scores?org_id=org1")
    assert resp.status_code == 200
    scores = {s["network_id"]: s for s in resp.json()["scores"]}
    assert scores["net1"]["score_pct"] == 100
    assert scores["net2"]["score_pct"] < 100
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/test_config_api_compare.py -v 2>&1 | head -30
```
Expected: 404/405 errors — the routes don't exist yet.

- [ ] **Step 3: Add route imports and handlers to `server/routes/config.py`**

Add to the imports block at the top of `server/routes/config.py`:

```python
from server.config_collector.store import (
    get_latest_observation, get_observation_history,
    get_blob_by_hash, get_change_events,
    create_sweep_run, get_active_sweep_run,
    get_observations_in_window,
    create_template, list_templates, get_template_areas, delete_template,
    get_coverage,
)
```

Then append to the end of `server/routes/config.py` (before the `ConfigWebSocketHub` class):

```python

# ── Phase 6: Templates ────────────────────────────────────────────────────────

class PromoteTemplateRequest(BaseModel):
    org_id: str
    name: str
    network_id: str


@router.get("/templates")
async def list_templates_route(org_id: str) -> list[dict]:
    conn = get_connection()
    try:
        return list_templates(conn, org_id=org_id)
    finally:
        conn.close()


@router.post("/templates")
async def create_template_route(req: PromoteTemplateRequest) -> dict:
    conn = get_connection()
    try:
        # Resolve network name from most recent name_hint observation
        name_row = conn.execute(
            """SELECT name_hint FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               AND name_hint IS NOT NULL ORDER BY observed_at DESC LIMIT 1""",
            (req.org_id, req.network_id),
        ).fetchone()
        network_name = name_row["name_hint"] if name_row else None
        return create_template(conn, org_id=req.org_id, name=req.name,
                               network_id=req.network_id, network_name=network_name)
    finally:
        conn.close()


@router.delete("/templates/{template_id}")
async def delete_template_route(template_id: int) -> dict:
    conn = get_connection()
    try:
        delete_template(conn, template_id=template_id)
        return {"deleted": template_id}
    finally:
        conn.close()


# ── Phase 6: Network Comparison ───────────────────────────────────────────────

@router.get("/compare/networks")
async def compare_networks(
    org_id: str,
    network_a: str,
    network_b: str,
) -> dict:
    conn = get_connection()
    try:
        # Get all config areas present in either network
        rows_a = conn.execute(
            """SELECT config_area, sub_key, hash, name_hint FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
            (org_id, network_a),
        ).fetchall()
        rows_b = conn.execute(
            """SELECT config_area, sub_key, hash, name_hint FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
            (org_id, network_b),
        ).fetchall()

        name_a = rows_a[0]["name_hint"] if rows_a else network_a
        name_b = rows_b[0]["name_hint"] if rows_b else network_b

        map_a = {(r["config_area"], r["sub_key"]): r for r in rows_a}
        map_b = {(r["config_area"], r["sub_key"]): r for r in rows_b}
        all_keys = set(map_a) | set(map_b)

        areas = []
        total_changes = 0
        differing_areas = 0

        for key in sorted(all_keys):
            config_area, sub_key = key
            in_a = key in map_a
            in_b = key in map_b

            if in_a and not in_b:
                areas.append({"config_area": config_area, "sub_key": sub_key,
                               "status": "only_in_a", "diff": None})
                differing_areas += 1
                continue
            if in_b and not in_a:
                areas.append({"config_area": config_area, "sub_key": sub_key,
                               "status": "only_in_b", "diff": None})
                differing_areas += 1
                continue

            blob_row_a = get_blob_by_hash(conn, map_a[key]["hash"])
            blob_row_b = get_blob_by_hash(conn, map_b[key]["hash"])
            blob_a = json.loads(blob_row_a["payload"]) if blob_row_a else {}
            blob_b = json.loads(blob_row_b["payload"]) if blob_row_b else {}
            diff = compute_diff(blob_a, blob_b)
            change_count = len(diff.changes)
            total_changes += change_count
            status = "differs" if change_count > 0 else "identical"
            if change_count > 0:
                differing_areas += 1
            areas.append({
                "config_area": config_area,
                "sub_key": sub_key,
                "status": status,
                "diff": dataclasses.asdict(diff),
            })

        # Sort: differs/only first, then identical
        areas.sort(key=lambda a: (0 if a["status"] != "identical" else 1, a["config_area"]))

        return {
            "network_a": {"id": network_a, "name": name_a},
            "network_b": {"id": network_b, "name": name_b},
            "areas": areas,
            "total_areas": len(areas),
            "differing_areas": differing_areas,
            "total_changes": total_changes,
        }
    finally:
        conn.close()


# ── Phase 6: Coverage ─────────────────────────────────────────────────────────

@router.get("/coverage")
async def get_coverage_route(org_id: str) -> dict:
    conn = get_connection()
    try:
        return {"areas": get_coverage(conn, org_id=org_id)}
    finally:
        conn.close()


# ── Phase 6: Template Scoring ─────────────────────────────────────────────────

@router.get("/templates/{template_id}/scores")
async def get_template_scores(template_id: int, org_id: str) -> dict:
    conn = get_connection()
    try:
        tmpl_row = conn.execute(
            "SELECT * FROM config_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not tmpl_row:
            raise HTTPException(status_code=404, detail="Template not found")

        template_areas = get_template_areas(conn, template_id=template_id)
        area_count = len(template_areas)

        # All networks in the org
        networks = conn.execute(
            """SELECT DISTINCT entity_id, MAX(name_hint) as name_hint
               FROM config_observations
               WHERE org_id=? AND entity_type='network'
               GROUP BY entity_id""",
            (org_id,),
        ).fetchall()

        scores = []
        for net in networks:
            network_id = net["entity_id"]
            network_name = net["name_hint"] or network_id

            # Latest observation per config area for this network
            net_obs = conn.execute(
                """SELECT config_area, sub_key, hash FROM config_observations
                   WHERE org_id=? AND entity_type='network' AND entity_id=?
                   GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
                (org_id, network_id),
            ).fetchall()
            net_map = {(r["config_area"], r["sub_key"]): r["hash"] for r in net_obs}

            total_fields = 0
            total_changes = 0
            missing_areas = []
            area_scores = []

            for ta in template_areas:
                key = (ta["config_area"], ta["sub_key"])
                if key not in net_map:
                    missing_areas.append(ta["config_area"])
                    area_scores.append({"config_area": ta["config_area"], "score_pct": 0, "change_count": 0})
                    continue

                tmpl_blob_row = get_blob_by_hash(conn, ta["blob_hash"])
                net_blob_row = get_blob_by_hash(conn, net_map[key])
                tmpl_blob = json.loads(tmpl_blob_row["payload"]) if tmpl_blob_row else {}
                net_blob = json.loads(net_blob_row["payload"]) if net_blob_row else {}

                diff = compute_diff(tmpl_blob, net_blob)
                n_changes = len(diff.changes)
                n_fields = diff.unchanged_count + n_changes
                total_fields += n_fields
                total_changes += n_changes

                area_score = 100 if n_fields == 0 else round((n_fields - n_changes) / n_fields * 100)
                area_scores.append({
                    "config_area": ta["config_area"],
                    "score_pct": area_score,
                    "change_count": n_changes,
                })

            score_pct = 100 if total_fields == 0 else round((total_fields - total_changes) / total_fields * 100)
            scores.append({
                "network_id": network_id,
                "network_name": network_name,
                "score_pct": score_pct,
                "change_count": total_changes,
                "total_fields": total_fields,
                "missing_areas": missing_areas,
                "area_scores": area_scores,
            })

        scores.sort(key=lambda s: s["score_pct"])

        return {
            "template": {
                "id": template_id,
                "name": tmpl_row["name"],
                "area_count": area_count,
            },
            "scores": scores,
        }
    finally:
        conn.close()
```

- [ ] **Step 4: Run API tests**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/test_config_api_compare.py -v
```
Expected: `5 passed`

- [ ] **Step 5: Run full server test suite to check for regressions**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/ -v 2>&1 | tail -20
```
Expected: all previously passing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add server/routes/config.py server/tests/test_config_api_compare.py
git commit -m "feat(phase6): add compare/coverage/template API endpoints + tests"
```

---

## Task 5: Add frontend types and API wrappers

**Files:**
- Modify: `ui/src/types/config.ts`
- Create: `ui/src/api/compare.ts`

- [ ] **Step 1: Add Phase 6 types to `ui/src/types/config.ts`**

Append to the end of `ui/src/types/config.ts`:

```typescript
// ── Phase 6: Multi-Site Comparison ───────────────────────────────────────────

export interface NetworkCompareArea {
  config_area: string
  sub_key: string | null
  status: 'differs' | 'identical' | 'only_in_a' | 'only_in_b'
  diff: DiffResult | null
}

export interface NetworkCompareResponse {
  network_a: { id: string; name: string | null }
  network_b: { id: string; name: string | null }
  areas: NetworkCompareArea[]
  total_areas: number
  differing_areas: number
  total_changes: number
}

export interface CoverageArea {
  config_area: string
  network_count: number
  network_total: number
  missing_networks: { id: string; name: string | null }[]
  device_breakdown: { id: string; name: string | null }[]
}

export interface CoverageResponse {
  areas: CoverageArea[]
}

export interface TemplateAreaRef {
  config_area: string
  sub_key: string | null
  blob_hash: string
}

export interface ConfigTemplate {
  id: number
  org_id: string
  name: string
  source_network_id: string
  source_network_name: string | null
  created_at: string
  areas: TemplateAreaRef[]
}

export interface TemplateAreaScore {
  config_area: string
  score_pct: number
  change_count: number
}

export interface NetworkTemplateScore {
  network_id: string
  network_name: string
  score_pct: number
  change_count: number
  total_fields: number
  missing_areas: string[]
  area_scores: TemplateAreaScore[]
}

export interface TemplateScoresResponse {
  template: { id: number; name: string; area_count: number }
  scores: NetworkTemplateScore[]
}
```

- [ ] **Step 2: Create `ui/src/api/compare.ts`**

```typescript
import type {
  NetworkCompareResponse,
  CoverageResponse,
  ConfigTemplate,
  TemplateScoresResponse,
} from '../types/config'

const BASE = '/api/config'

async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${path}`)
  return res.json()
}

export function compareNetworks(
  orgId: string,
  networkA: string,
  networkB: string,
): Promise<NetworkCompareResponse> {
  const qs = new URLSearchParams({ org_id: orgId, network_a: networkA, network_b: networkB })
  return _fetch(`/compare/networks?${qs}`)
}

export function getCoverage(orgId: string): Promise<CoverageResponse> {
  return _fetch(`/coverage?${new URLSearchParams({ org_id: orgId })}`)
}

export function listTemplates(orgId: string): Promise<ConfigTemplate[]> {
  return _fetch(`/templates?${new URLSearchParams({ org_id: orgId })}`)
}

export function createTemplate(orgId: string, name: string, networkId: string): Promise<ConfigTemplate> {
  return _fetch('/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ org_id: orgId, name, network_id: networkId }),
  })
}

export function deleteTemplate(templateId: number): Promise<{ deleted: number }> {
  return _fetch(`/templates/${templateId}`, { method: 'DELETE' })
}

export function getTemplateScores(templateId: number, orgId: string): Promise<TemplateScoresResponse> {
  return _fetch(`/templates/${templateId}/scores?${new URLSearchParams({ org_id: orgId })}`)
}
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/types/config.ts ui/src/api/compare.ts
git commit -m "feat(phase6): add frontend types and API wrappers"
```

---

## Task 6: Add frontend hooks

**Files:**
- Create: `ui/src/hooks/useNetworkCompare.ts`
- Create: `ui/src/hooks/useCoverage.ts`
- Create: `ui/src/hooks/useTemplates.ts`
- Create: `ui/src/hooks/useTemplateScores.ts`

- [ ] **Step 1: Create `ui/src/hooks/useNetworkCompare.ts`**

```typescript
import { useState, useCallback } from 'react'
import { compareNetworks } from '../api/compare'
import type { NetworkCompareResponse } from '../types/config'

interface State {
  result: NetworkCompareResponse | null
  loading: boolean
  error: string | null
}

export function useNetworkCompare() {
  const [state, setState] = useState<State>({ result: null, loading: false, error: null })

  const compare = useCallback(async (orgId: string, networkA: string, networkB: string) => {
    setState({ result: null, loading: true, error: null })
    try {
      const data = await compareNetworks(orgId, networkA, networkB)
      setState({ result: data, loading: false, error: null })
    } catch (e) {
      setState({ result: null, loading: false, error: String(e) })
    }
  }, [])

  const clear = useCallback(() => setState({ result: null, loading: false, error: null }), [])

  return { ...state, compare, clear }
}
```

- [ ] **Step 2: Create `ui/src/hooks/useCoverage.ts`**

```typescript
import { useState, useEffect } from 'react'
import { getCoverage } from '../api/compare'
import type { CoverageResponse } from '../types/config'

export function useCoverage(orgId: string | null) {
  const [data, setData] = useState<CoverageResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!orgId) return
    setLoading(true)
    setError(null)
    getCoverage(orgId)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId])

  return { data, loading, error }
}
```

- [ ] **Step 3: Create `ui/src/hooks/useTemplates.ts`**

```typescript
import { useState, useEffect, useCallback } from 'react'
import { listTemplates, createTemplate, deleteTemplate } from '../api/compare'
import type { ConfigTemplate } from '../types/config'

export function useTemplates(orgId: string | null) {
  const [templates, setTemplates] = useState<ConfigTemplate[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(() => {
    if (!orgId) return
    setLoading(true)
    listTemplates(orgId)
      .then(t => { setTemplates(t); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [orgId])

  useEffect(() => { reload() }, [reload])

  const promote = useCallback(async (name: string, networkId: string) => {
    if (!orgId) return
    await createTemplate(orgId, name, networkId)
    reload()
  }, [orgId, reload])

  const remove = useCallback(async (templateId: number) => {
    await deleteTemplate(templateId)
    reload()
  }, [reload])

  return { templates, loading, error, promote, remove, reload }
}
```

- [ ] **Step 4: Create `ui/src/hooks/useTemplateScores.ts`**

```typescript
import { useState, useEffect } from 'react'
import { getTemplateScores } from '../api/compare'
import type { TemplateScoresResponse } from '../types/config'

export function useTemplateScores(templateId: number | null, orgId: string | null) {
  const [data, setData] = useState<TemplateScoresResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!templateId || !orgId) { setData(null); return }
    setLoading(true)
    setError(null)
    getTemplateScores(templateId, orgId)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(String(e)); setLoading(false) })
  }, [templateId, orgId])

  return { data, loading, error }
}
```

- [ ] **Step 5: Commit**

```bash
git add ui/src/hooks/useNetworkCompare.ts ui/src/hooks/useCoverage.ts \
        ui/src/hooks/useTemplates.ts ui/src/hooks/useTemplateScores.ts
git commit -m "feat(phase6): add frontend hooks for compare, coverage, templates"
```

---

## Task 7: Build CompareTab shell

**Files:**
- Create: `ui/src/components/ConfigBrowser/CompareTab.tsx`

- [ ] **Step 1: Create `ui/src/components/ConfigBrowser/CompareTab.tsx`**

```tsx
import { useState } from 'react'
import type { ConfigTree } from '../../types/config'

type SubView = 'networks' | 'coverage' | 'templates'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

// Sub-view components are imported lazily to keep this file small.
// They are implemented in Tasks 8, 9, and 10.
import { CompareNetworksView } from './CompareNetworksView'
import { CoverageView } from './CoverageView'
import { TemplatesView } from './TemplatesView'

const PILLS: { id: SubView; label: string }[] = [
  { id: 'networks', label: 'Compare Networks' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'templates', label: 'Templates' },
]

export function CompareTab({ orgId, tree }: Props) {
  const [active, setActive] = useState<SubView>('networks')

  return (
    <div className="flex flex-col gap-3 p-3 h-full">
      <div className="flex gap-1">
        {PILLS.map(p => (
          <button
            key={p.id}
            onClick={() => setActive(p.id)}
            className={[
              'px-3 py-1 rounded-full text-xs transition-colors',
              active === p.id
                ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/50'
                : 'text-white/50 hover:text-white/80 hover:bg-white/5',
            ].join(' ')}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {active === 'networks' && <CompareNetworksView orgId={orgId} tree={tree} />}
        {active === 'coverage' && <CoverageView orgId={orgId} />}
        {active === 'templates' && <TemplatesView orgId={orgId} tree={tree} />}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Create stub files so the import compiles**

Create `ui/src/components/ConfigBrowser/CompareNetworksView.tsx`:
```tsx
export function CompareNetworksView(_: { orgId: string; tree: unknown }) {
  return <div className="text-xs opacity-50 p-4">Compare Networks — coming soon</div>
}
```

Create `ui/src/components/ConfigBrowser/CoverageView.tsx`:
```tsx
export function CoverageView(_: { orgId: string }) {
  return <div className="text-xs opacity-50 p-4">Coverage — coming soon</div>
}
```

Create `ui/src/components/ConfigBrowser/TemplatesView.tsx`:
```tsx
export function TemplatesView(_: { orgId: string; tree: unknown }) {
  return <div className="text-xs opacity-50 p-4">Templates — coming soon</div>
}
```

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ConfigBrowser/CompareTab.tsx \
        ui/src/components/ConfigBrowser/CompareNetworksView.tsx \
        ui/src/components/ConfigBrowser/CoverageView.tsx \
        ui/src/components/ConfigBrowser/TemplatesView.tsx
git commit -m "feat(phase6): add CompareTab shell with stub sub-views"
```

---

## Task 8: Wire Compare tab into ConfigBrowser

**Files:**
- Modify: `ui/src/components/ConfigBrowser/ConfigBrowser.tsx`
- Modify: `ui/src/components/ConfigBrowser/index.ts`

- [ ] **Step 1: Add the Compare tab to `ConfigBrowser.tsx`**

In `ui/src/components/ConfigBrowser/ConfigBrowser.tsx`:

1. Add import at the top:
```tsx
import { CompareTab } from './CompareTab'
```

2. Find the `activeTab` state declaration and add `'compare'` to the type union:
```tsx
const [activeTab, setActiveTab] = useState<'overview' | 'history' | 'compare'>('overview')
```

3. Find the tab bar rendering (the `div` with tab buttons for Overview and History) and add the Compare button alongside them:
```tsx
<button
  onClick={() => setActiveTab('compare')}
  className={activeTab === 'compare' ? 'tab-active' : 'tab-inactive'}
>
  Compare
</button>
```
Match the exact `className` pattern of the existing Overview and History tab buttons.

4. Add the Compare tab panel alongside the existing Overview and History panels:
```tsx
{activeTab === 'compare' && selectedOrgId && (
  <CompareTab orgId={selectedOrgId} tree={tree ?? null} />
)}
```

- [ ] **Step 2: Export from `index.ts`**

In `ui/src/components/ConfigBrowser/index.ts`, add:
```typescript
export { CompareTab } from './CompareTab'
export { CompareNetworksView } from './CompareNetworksView'
export { CoverageView } from './CoverageView'
export { TemplatesView } from './TemplatesView'
```

- [ ] **Step 3: Verify the UI builds**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npm run build 2>&1 | tail -20
```
Expected: build succeeds with no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add ui/src/components/ConfigBrowser/ConfigBrowser.tsx \
        ui/src/components/ConfigBrowser/index.ts
git commit -m "feat(phase6): wire Compare tab into ConfigBrowser"
```

---

## Task 9: Implement CompareNetworksView

**Files:**
- Modify: `ui/src/components/ConfigBrowser/CompareNetworksView.tsx`

- [ ] **Step 1: Replace the stub with the full implementation**

Replace `ui/src/components/ConfigBrowser/CompareNetworksView.tsx`:

```tsx
import { useState } from 'react'
import { useNetworkCompare } from '../../hooks/useNetworkCompare'
import { DiffViewer } from './DiffViewer'
import type { ConfigTree, NetworkCompareArea } from '../../types/config'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

function AreaRow({ area, nameA, nameB }: { area: NetworkCompareArea; nameA: string; nameB: string }) {
  const [open, setOpen] = useState(false)
  const changeCount = area.diff?.changes.length ?? 0
  const isOnly = area.status === 'only_in_a' || area.status === 'only_in_b'

  return (
    <div className="border border-white/10 rounded mb-1 overflow-hidden">
      <button
        onClick={() => !isOnly && setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <span className="text-xs font-mono opacity-80">{area.config_area}</span>
        {isOnly ? (
          <span className="text-xs opacity-40">
            Only in {area.status === 'only_in_a' ? nameA : nameB}
          </span>
        ) : (
          <span className={[
            'text-xs px-2 py-0.5 rounded-full',
            changeCount > 0 ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400',
          ].join(' ')}>
            {changeCount > 0 ? `${changeCount} diff${changeCount !== 1 ? 's' : ''}` : 'identical'}
          </span>
        )}
      </button>
      {open && area.diff && (
        <div className="border-t border-white/10 p-2">
          <DiffViewer diff={area.diff} />
        </div>
      )}
    </div>
  )
}

export function CompareNetworksView({ orgId, tree }: Props) {
  const networks = tree?.networks ?? []
  const [netA, setNetA] = useState('')
  const [netB, setNetB] = useState('')
  const { result, loading, error, compare, clear } = useNetworkCompare()

  const canCompare = netA && netB && netA !== netB
  const nameA = networks.find(n => n.id === netA)?.name ?? netA
  const nameB = networks.find(n => n.id === netB)?.name ?? netB

  const handleCompare = () => {
    if (canCompare) compare(orgId, netA, netB)
  }

  const handleNetAChange = (v: string) => { setNetA(v); clear() }
  const handleNetBChange = (v: string) => { setNetB(v); clear() }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <select
          value={netA}
          onChange={e => handleNetAChange(e.target.value)}
          className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
        >
          <option value="">Select network A…</option>
          {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
        </select>
        <span className="text-xs opacity-40">vs</span>
        <select
          value={netB}
          onChange={e => handleNetBChange(e.target.value)}
          className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
        >
          <option value="">Select network B…</option>
          {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
        </select>
        <button
          onClick={handleCompare}
          disabled={!canCompare || loading}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs transition-colors"
        >
          {loading ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {netA && netB && netA === netB && (
        <p className="text-xs text-amber-400/70">Select two different networks.</p>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}

      {result && (
        <div>
          {result.differing_areas === 0 ? (
            <p className="text-xs opacity-50 text-center py-6">
              No differences found — these networks have identical config across all areas.
            </p>
          ) : (
            <>
              <p className="text-xs opacity-50 mb-2">
                {result.differing_areas} area{result.differing_areas !== 1 ? 's' : ''} differ · {result.total_changes} field{result.total_changes !== 1 ? 's' : ''} changed
              </p>
              {result.areas.map((area, i) => (
                <AreaRow key={i} area={area} nameA={nameA} nameB={nameB} />
              ))}
            </>
          )}
        </div>
      )}

      {!result && !loading && networks.length === 0 && (
        <p className="text-xs opacity-40 text-center py-6">
          No networks collected yet — run a baseline first.
        </p>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Build to verify no TypeScript errors**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npm run build 2>&1 | tail -20
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add ui/src/components/ConfigBrowser/CompareNetworksView.tsx
git commit -m "feat(phase6): implement CompareNetworksView"
```

---

## Task 10: Implement CoverageView

**Files:**
- Modify: `ui/src/components/ConfigBrowser/CoverageView.tsx`

- [ ] **Step 1: Replace the stub**

```tsx
import { useState } from 'react'
import { useCoverage } from '../../hooks/useCoverage'
import type { CoverageArea } from '../../types/config'

function coverageColor(count: number, total: number): string {
  if (total === 0) return 'text-white/40'
  const pct = count / total
  if (pct === 1) return 'text-green-400'
  if (pct >= 0.5) return 'text-amber-400'
  return 'text-red-400'
}

interface Props { orgId: string }

export function CoverageView({ orgId }: Props) {
  const { data, loading, error } = useCoverage(orgId)
  const [selected, setSelected] = useState<CoverageArea | null>(null)

  if (loading) return <p className="text-xs opacity-40 p-4">Loading coverage…</p>
  if (error) return <p className="text-xs text-red-400 p-4">{error}</p>
  if (!data || data.areas.length === 0) return (
    <p className="text-xs opacity-40 text-center py-6">No networks collected yet — run a baseline first.</p>
  )

  return (
    <div className="flex gap-3 h-full min-h-0">
      {/* Left: area list */}
      <div className="w-48 shrink-0 flex flex-col gap-0.5 overflow-y-auto">
        {data.areas.map(area => (
          <button
            key={area.config_area}
            onClick={() => setSelected(area)}
            className={[
              'flex items-center justify-between px-2 py-1.5 rounded text-left transition-colors',
              selected?.config_area === area.config_area
                ? 'bg-indigo-500/20 border border-indigo-500/40'
                : 'hover:bg-white/5',
            ].join(' ')}
          >
            <span className="text-xs font-mono truncate opacity-80">{area.config_area}</span>
            <span className={`text-xs ml-2 shrink-0 ${coverageColor(area.network_count, area.network_total)}`}>
              {area.network_count}/{area.network_total}
            </span>
          </button>
        ))}
      </div>

      {/* Right: detail panel */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {!selected ? (
          <p className="text-xs opacity-30 p-4">Select a config area to see details.</p>
        ) : (
          <div>
            <p className="text-xs font-mono mb-3 opacity-70">{selected.config_area}</p>
            {selected.missing_networks.length === 0 ? (
              <p className="text-xs text-green-400/70">All networks have this config area.</p>
            ) : (
              <>
                <p className="text-xs opacity-40 mb-2">
                  {selected.missing_networks.length} network{selected.missing_networks.length !== 1 ? 's' : ''} missing
                </p>
                {selected.missing_networks.map(n => (
                  <div key={n.id} className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-400/80 mb-1">
                    {n.name ?? n.id}
                  </div>
                ))}
              </>
            )}
            {selected.device_breakdown.length > 0 && (
              <div className="mt-4">
                <p className="text-xs opacity-40 mb-2">Devices with this area</p>
                {selected.device_breakdown.map(d => (
                  <div key={d.id} className="text-xs px-2 py-1 rounded bg-white/5 mb-1 opacity-70">
                    {d.name ?? d.id}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npm run build 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ConfigBrowser/CoverageView.tsx
git commit -m "feat(phase6): implement CoverageView"
```

---

## Task 11: Implement TemplatesView

**Files:**
- Modify: `ui/src/components/ConfigBrowser/TemplatesView.tsx`

- [ ] **Step 1: Replace the stub**

```tsx
import { useState } from 'react'
import { useTemplates } from '../../hooks/useTemplates'
import { useTemplateScores } from '../../hooks/useTemplateScores'
import type { ConfigTemplate, ConfigTree, NetworkTemplateScore } from '../../types/config'

function ScoreBar({ pct }: { pct: number }) {
  const color = pct >= 90 ? 'bg-green-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500'
  const textColor = pct >= 90 ? 'text-green-400' : pct >= 60 ? 'text-amber-400' : 'text-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-white/10 rounded overflow-hidden">
        <div className={`h-full ${color} rounded`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs w-8 text-right ${textColor}`}>{pct}%</span>
    </div>
  )
}

function NetworkScoreRow({ score }: { score: NetworkTemplateScore }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-white/10 rounded mb-1 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition-colors"
      >
        <span className="text-xs opacity-80 w-32 text-left truncate">{score.network_name}</span>
        <div className="flex-1"><ScoreBar pct={score.score_pct} /></div>
      </button>
      {open && (
        <div className="border-t border-white/10 p-2 space-y-1">
          {score.missing_areas.length > 0 && (
            <p className="text-xs text-red-400/70">Missing areas: {score.missing_areas.join(', ')}</p>
          )}
          {score.area_scores.map(as => (
            <div key={as.config_area} className="flex items-center gap-2">
              <span className="text-xs font-mono opacity-60 w-40 truncate">{as.config_area}</span>
              <div className="flex-1"><ScoreBar pct={as.score_pct} /></div>
              {as.change_count > 0 && (
                <span className="text-xs text-red-400/60">{as.change_count} change{as.change_count !== 1 ? 's' : ''}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface PromoteModalProps {
  tree: ConfigTree | null
  onConfirm: (name: string, networkId: string) => void
  onCancel: () => void
}

function PromoteModal({ tree, onConfirm, onCancel }: PromoteModalProps) {
  const [name, setName] = useState('')
  const [networkId, setNetworkId] = useState('')
  const networks = tree?.networks ?? []
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1a1a2e] border border-white/10 rounded-lg p-5 w-80 space-y-3">
        <h3 className="text-sm font-medium">Promote Network as Template</h3>
        <div>
          <label className="text-xs opacity-50 block mb-1">Network</label>
          <select
            value={networkId}
            onChange={e => setNetworkId(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          >
            <option value="">Select a network…</option>
            {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs opacity-50 block mb-1">Template name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Standard Retail"
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          />
        </div>
        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onCancel} className="px-3 py-1.5 text-xs opacity-60 hover:opacity-100">Cancel</button>
          <button
            disabled={!name.trim() || !networkId}
            onClick={() => onConfirm(name.trim(), networkId)}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs"
          >
            Save Template
          </button>
        </div>
      </div>
    </div>
  )
}

interface Props { orgId: string; tree: ConfigTree | null }

export function TemplatesView({ orgId, tree }: Props) {
  const { templates, loading, promote, remove } = useTemplates(orgId)
  const [selected, setSelected] = useState<ConfigTemplate | null>(null)
  const [showPromote, setShowPromote] = useState(false)
  const { data: scoresData, loading: scoresLoading } = useTemplateScores(selected?.id ?? null, orgId)

  const handlePromote = async (name: string, networkId: string) => {
    await promote(name, networkId)
    setShowPromote(false)
  }

  const handleDelete = async (tmpl: ConfigTemplate) => {
    if (!confirm(`Delete template "${tmpl.name}"?`)) return
    if (selected?.id === tmpl.id) setSelected(null)
    await remove(tmpl.id)
  }

  return (
    <div className="flex gap-3 h-full min-h-0">
      {showPromote && (
        <PromoteModal tree={tree} onConfirm={handlePromote} onCancel={() => setShowPromote(false)} />
      )}

      {/* Left: template list */}
      <div className="w-48 shrink-0 flex flex-col gap-1 overflow-y-auto">
        {loading && <p className="text-xs opacity-40 p-2">Loading…</p>}
        {!loading && templates.length === 0 && (
          <p className="text-xs opacity-40 p-2">No templates yet.</p>
        )}
        {templates.map(tmpl => (
          <div
            key={tmpl.id}
            onClick={() => setSelected(tmpl)}
            className={[
              'p-2 rounded cursor-pointer group transition-colors',
              selected?.id === tmpl.id
                ? 'bg-indigo-500/20 border border-indigo-500/40'
                : 'hover:bg-white/5 border border-transparent',
            ].join(' ')}
          >
            <div className="flex items-start justify-between">
              <span className="text-xs font-medium truncate">{tmpl.name}</span>
              <button
                onClick={e => { e.stopPropagation(); handleDelete(tmpl) }}
                className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-red-400 text-xs ml-1"
                title="Delete template"
              >✕</button>
            </div>
            <div className="text-xs opacity-40 mt-0.5 truncate">{tmpl.source_network_name ?? tmpl.source_network_id}</div>
            <div className="text-xs opacity-30 mt-0.5">{tmpl.areas.length} areas</div>
          </div>
        ))}
        <button
          onClick={() => setShowPromote(true)}
          className="mt-1 p-2 border border-dashed border-white/20 rounded text-xs opacity-50 hover:opacity-80 text-center"
        >
          + Promote a network
        </button>
      </div>

      {/* Right: scoring panel */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {!selected ? (
          <p className="text-xs opacity-30 p-4">Select a template to see network scores.</p>
        ) : scoresLoading ? (
          <p className="text-xs opacity-40 p-4">Scoring networks…</p>
        ) : scoresData ? (
          <div>
            <p className="text-xs opacity-50 mb-3">
              {scoresData.template.name} · {scoresData.scores.length} networks · {scoresData.template.area_count} template areas
            </p>
            {scoresData.scores.map(score => (
              <NetworkScoreRow key={score.network_id} score={score} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Build**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npm run build 2>&1 | tail -10
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add ui/src/components/ConfigBrowser/TemplatesView.tsx
git commit -m "feat(phase6): implement TemplatesView with promote modal and scoring panel"
```

---

## Task 12: End-to-end smoke test

- [ ] **Step 1: Start the dev server**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
docker compose up -d
```
or
```bash
cd "/Users/jkarnik/Code/Topology Maps"
uvicorn server.main:app --reload &
cd ui && npm run dev &
```

- [ ] **Step 2: Smoke test Compare Networks**

1. Open the app in a browser
2. Navigate to Config → select an org
3. Click the **Compare** tab — verify the three pill buttons appear
4. Click **Compare Networks** — verify two network dropdowns appear
5. Select two different networks and click Compare — verify grouped, collapsible results appear
6. Select the same network for both — verify Compare button is disabled

- [ ] **Step 3: Smoke test Coverage**

1. Click **Coverage** pill — verify left panel lists config areas with counts
2. Click a config area — verify detail panel shows missing networks on the right

- [ ] **Step 4: Smoke test Templates**

1. Click **Templates** pill — verify "No templates yet" state and promote button
2. Click **+ Promote a network** — verify modal appears with network dropdown and name input
3. Leave name empty — verify Save is disabled
4. Fill name and select a network — verify Save is enabled
5. Save — verify template appears in left panel
6. Click the template — verify scoring panel loads and shows all networks with bars
7. Click a network row — verify it expands to show per-area scores
8. Delete the template (✕ button) — verify it disappears

- [ ] **Step 5: Final regression check**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
python -m pytest server/tests/ -v 2>&1 | tail -20
```
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat(phase6): complete Phase 6 multi-site comparison"
```

---
