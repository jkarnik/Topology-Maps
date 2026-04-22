# Plan 1.17 — REST API

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Expose all `/api/config/*` endpoints from the spec. Wire the config router into `server/main.py`. Each endpoint is a thin FastAPI function delegating to the already-built backend functions (scanner, poller, store).

**Depends on:** Plans 1.10-1.16.
**Unblocks:** Plans 1.19-1.21 (UI consumes these endpoints).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/routes/config.py` | Create | FastAPI router for `/api/config/*` |
| `server/main.py` | Modify | Register the config router |
| `server/tests/test_config_api.py` | Create | FastAPI TestClient tests |

---

## Task 1: Create router + `GET /api/config/orgs`

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_config_api.py`:

```python
"""Tests for config REST API (Plan 1.17)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app(monkeypatch):
    """Build a minimal FastAPI app with the config router mounted."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        database.get_connection().close()

        from fastapi import FastAPI
        from server.routes import config as config_routes
        app = FastAPI()
        app.include_router(config_routes.router)
        yield app


@pytest.fixture
def client(app):
    return TestClient(app)


def test_list_orgs_empty(client):
    resp = client.get("/api/config/orgs")
    assert resp.status_code == 200
    assert resp.json() == []
```

- [ ] **Step 1.2: Run — should fail (module doesn't exist)**

- [ ] **Step 1.3: Create the router**

Create `server/routes/config.py`:

```python
"""REST API for Meraki config collection (Plan 1.17)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from server.database import get_connection

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/orgs")
async def list_orgs() -> list[dict]:
    """List orgs with collection status. Empty until a baseline is started."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT org_id FROM config_sweep_runs
           UNION SELECT DISTINCT org_id FROM config_observations"""
    ).fetchall()
    result = []
    for r in rows:
        org_id = r["org_id"]
        obs_count = conn.execute(
            "SELECT COUNT(*) AS n FROM config_observations WHERE org_id=?", (org_id,)
        ).fetchone()["n"]
        last_baseline = conn.execute(
            """SELECT id, status, completed_at FROM config_sweep_runs
               WHERE org_id=? AND kind='baseline'
               ORDER BY id DESC LIMIT 1""",
            (org_id,),
        ).fetchone()
        active = conn.execute(
            """SELECT id FROM config_sweep_runs
               WHERE org_id=? AND status IN ('queued','running')
               ORDER BY id DESC LIMIT 1""",
            (org_id,),
        ).fetchone()
        result.append({
            "org_id": org_id,
            "observation_count": obs_count,
            "baseline_state": last_baseline["status"] if last_baseline else "none",
            "last_baseline_at": last_baseline["completed_at"] if last_baseline else None,
            "active_sweep_run_id": active["id"] if active else None,
        })
    conn.close()
    return result
```

- [ ] **Step 1.4: Run — should pass**

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/routes/config.py server/tests/test_config_api.py
git commit -m "feat(api): GET /api/config/orgs listing endpoint (Plan 1.17)"
```

---

## Task 2: Sweep trigger endpoints (baseline / sweep / refresh / status)

- [ ] **Step 2.1: Write failing tests**

Append to `server/tests/test_config_api.py`:

```python
from unittest.mock import AsyncMock, patch


def test_status_empty_org(client):
    resp = client.get("/api/config/orgs/o1/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["baseline_state"] == "none"
    assert body["active_sweep"] is None


def test_baseline_trigger_returns_run_id(client):
    with patch("server.routes.config._get_meraki_client") as gc, \
         patch("server.routes.config.run_baseline", new=AsyncMock(return_value=42)):
        gc.return_value = object()
        resp = client.post("/api/config/orgs/o1/baseline")
    assert resp.status_code == 200
    assert resp.json()["sweep_run_id"] == 42


def test_sweep_trigger_returns_run_id(client):
    with patch("server.routes.config._get_meraki_client") as gc, \
         patch("server.routes.config.run_anti_drift_sweep", new=AsyncMock(return_value=99)):
        gc.return_value = object()
        resp = client.post("/api/config/orgs/o1/sweep")
    assert resp.status_code == 200
    assert resp.json()["sweep_run_id"] == 99


def test_refresh_trigger_validates_entity_type(client):
    resp = client.post("/api/config/orgs/o1/refresh", json={
        "entity_type": "bogus", "entity_id": "x",
    })
    assert resp.status_code == 400
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Implement the endpoints**

Append to `server/routes/config.py`:

```python
from pydantic import BaseModel
from server.config_collector.scanner import run_baseline, run_anti_drift_sweep
from server.config_collector.manual_refresh import refresh_entity
from server.meraki_client import MerakiClient

_VALID_ENTITY_TYPES = {"org", "network", "device", "ssid"}


def _get_meraki_client() -> MerakiClient:
    return MerakiClient()


@router.get("/orgs/{org_id}/status")
async def get_status(org_id: str) -> dict:
    conn = get_connection()
    last = conn.execute(
        "SELECT status, completed_at FROM config_sweep_runs WHERE org_id=? AND kind='baseline' ORDER BY id DESC LIMIT 1",
        (org_id,),
    ).fetchone()
    active = conn.execute(
        "SELECT id, kind, status FROM config_sweep_runs WHERE org_id=? AND status IN ('queued','running') ORDER BY id DESC LIMIT 1",
        (org_id,),
    ).fetchone()
    conn.close()
    return {
        "baseline_state": last["status"] if last else "none",
        "last_sync": last["completed_at"] if last else None,
        "active_sweep": dict(active) if active else None,
    }


@router.post("/orgs/{org_id}/baseline")
async def start_baseline(org_id: str) -> dict:
    conn = get_connection()
    client = _get_meraki_client()
    try:
        run_id = await run_baseline(client, conn, org_id=org_id)
    finally:
        conn.close()
    return {"sweep_run_id": run_id}


@router.post("/orgs/{org_id}/sweep")
async def start_sweep(org_id: str) -> dict:
    conn = get_connection()
    client = _get_meraki_client()
    try:
        run_id = await run_anti_drift_sweep(client, conn, org_id=org_id)
    finally:
        conn.close()
    return {"sweep_run_id": run_id}


class RefreshRequest(BaseModel):
    entity_type: str
    entity_id: str
    config_area: Optional[str] = None


@router.post("/orgs/{org_id}/refresh")
async def refresh(org_id: str, req: RefreshRequest) -> dict:
    if req.entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(400, detail=f"entity_type must be one of {_VALID_ENTITY_TYPES}")
    conn = get_connection()
    client = _get_meraki_client()
    try:
        result = await refresh_entity(
            client, conn,
            org_id=org_id,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            config_area=req.config_area,
        )
    finally:
        conn.close()
    return result
```

- [ ] **Step 2.4: Run — should pass**

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/routes/config.py server/tests/test_config_api.py
git commit -m "feat(api): baseline/sweep/refresh/status endpoints (Plan 1.17)"
```

---

## Task 3: Browse endpoints (tree / entity / history / blob / events)

- [ ] **Step 3.1: Write tests**

Append to `server/tests/test_config_api.py`:

```python
def test_get_entity_returns_404_if_missing(client):
    resp = client.get("/api/config/entities/network/N_MISSING?org_id=o1")
    assert resp.status_code == 404


def test_get_blob_returns_404_if_missing(client):
    resp = client.get("/api/config/blobs/does-not-exist")
    assert resp.status_code == 404


def test_list_change_events_empty(client):
    resp = client.get("/api/config/change-events?org_id=o1")
    assert resp.status_code == 200
    assert resp.json() == {"events": [], "has_more": False, "next_cursor": None}
```

- [ ] **Step 3.2: Run — should fail**

- [ ] **Step 3.3: Implement the endpoints**

Append to `server/routes/config.py`:

```python
import json
from server.config_collector.store import (
    get_latest_observation, get_observation_history,
    get_blob_by_hash, get_change_events,
)


@router.get("/orgs/{org_id}/tree")
async def get_tree(org_id: str) -> dict:
    """Hierarchical tree of entities with observations."""
    conn = get_connection()
    try:
        # Org-level areas
        org_areas = [r["config_area"] for r in conn.execute(
            "SELECT DISTINCT config_area FROM config_observations WHERE org_id=? AND entity_type='org'",
            (org_id,),
        ).fetchall()]

        # Networks
        net_rows = conn.execute(
            "SELECT DISTINCT entity_id, name_hint FROM config_observations WHERE org_id=? AND entity_type='network'",
            (org_id,),
        ).fetchall()
        networks = []
        for nr in net_rows:
            nid = nr["entity_id"]
            net_areas = [r["config_area"] for r in conn.execute(
                "SELECT DISTINCT config_area FROM config_observations WHERE org_id=? AND entity_type='network' AND entity_id=?",
                (org_id, nid),
            ).fetchall()]
            dev_rows = conn.execute(
                "SELECT DISTINCT entity_id, name_hint FROM config_observations WHERE org_id=? AND entity_type='device'",
                (org_id,),
            ).fetchall()
            networks.append({
                "id": nid, "name": nr["name_hint"], "config_areas": net_areas,
                "devices": [{"serial": d["entity_id"], "name": d["name_hint"]} for d in dev_rows],
            })
        return {"org": {"id": org_id, "config_areas": org_areas}, "networks": networks}
    finally:
        conn.close()


@router.get("/entities/{entity_type}/{entity_id}")
async def get_entity(
    entity_type: str, entity_id: str,
    org_id: str = Query(...),
) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT DISTINCT config_area, sub_key FROM config_observations
               WHERE org_id=? AND entity_type=? AND entity_id=?""",
            (org_id, entity_type, entity_id),
        ).fetchall()
        if not rows:
            raise HTTPException(404, detail="Entity not found")
        areas = []
        for r in rows:
            latest = get_latest_observation(
                conn, org_id=org_id, entity_type=entity_type, entity_id=entity_id,
                config_area=r["config_area"], sub_key=r["sub_key"],
            )
            blob = get_blob_by_hash(conn, latest["hash"]) if latest else None
            areas.append({
                **latest,
                "payload": json.loads(blob["payload"]) if blob else None,
            })
        return {"entity_type": entity_type, "entity_id": entity_id, "org_id": org_id, "areas": areas}
    finally:
        conn.close()


@router.get("/entities/{entity_type}/{entity_id}/history")
async def get_history(
    entity_type: str, entity_id: str,
    org_id: str = Query(...),
    config_area: Optional[str] = None,
    limit: int = 100,
    before: Optional[str] = None,
) -> dict:
    conn = get_connection()
    try:
        obs = get_observation_history(
            conn, org_id=org_id, entity_type=entity_type, entity_id=entity_id,
            config_area=config_area, limit=limit, before_observed_at=before,
        )
        return {"observations": obs, "has_more": len(obs) == limit,
                "next_cursor": obs[-1]["observed_at"] if obs and len(obs) == limit else None}
    finally:
        conn.close()


@router.get("/blobs/{hash_hex}")
async def get_blob(hash_hex: str) -> dict:
    conn = get_connection()
    try:
        blob = get_blob_by_hash(conn, hash_hex)
        if not blob:
            raise HTTPException(404, detail="Blob not found")
        return {**blob, "payload": json.loads(blob["payload"])}
    finally:
        conn.close()


@router.get("/change-events")
async def list_change_events(
    org_id: str = Query(...),
    network_id: Optional[str] = None,
    limit: int = 100,
    before: Optional[str] = None,
) -> dict:
    conn = get_connection()
    try:
        events = get_change_events(
            conn, org_id=org_id, network_id=network_id,
            limit=limit, before_ts=before,
        )
        return {
            "events": events,
            "has_more": len(events) == limit,
            "next_cursor": events[-1]["ts"] if events and len(events) == limit else None,
        }
    finally:
        conn.close()
```

- [ ] **Step 3.2: Run — should pass**

- [ ] **Step 3.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/routes/config.py server/tests/test_config_api.py
git commit -m "feat(api): tree/entity/history/blob/events browse endpoints (Plan 1.17)"
```

---

## Task 4: Register the router in `main.py`

- [ ] **Step 4.1: Register router**

In `server/main.py`, add (near other `app.include_router(...)` calls):

```python
from server.routes import config as config_routes
app.include_router(config_routes.router)
```

- [ ] **Step 4.2: Verify app starts**

Run: `cd "/Users/jkarnik/Code/Topology Maps" && python -c "from server.main import app; print('ok')"`

Expected: `ok` (no import errors).

- [ ] **Step 4.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/main.py
git commit -m "feat(api): register config router in main.py (Plan 1.17)"
```

---

## Completion Checklist

- [ ] All `/api/config/*` endpoints implemented
- [ ] Router registered in main.py
- [ ] ~8 passing API tests
- [ ] 4 commits

## What This Unblocks

- Plans 1.19-1.21 (UI) can now call real backend endpoints.

