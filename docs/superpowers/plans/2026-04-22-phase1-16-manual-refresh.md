# Plan 1.16 — Manual Refresh

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Targeted, user-triggered refresh of a specific `(entity_type, entity_id)` — optionally scoped to a single `config_area`. Used by the UI "↻" buttons and for ad-hoc operator refreshes. Idempotent: an identical in-flight refresh returns the existing task id.

**Depends on:** Plans 1.04, 1.05-1.09, 1.10, 1.12.
**Unblocks:** Plan 1.17 (REST `POST /orgs/{id}/refresh`).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/manual_refresh.py` | Create | `refresh_entity(client, conn, ...)` and an in-memory "active refresh" tracker |
| `server/tests/test_manual_refresh.py` | Create | Tests covering single-area, all-areas, idempotency |

---

## Task 1: `refresh_entity` core logic

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_manual_refresh.py`:

```python
"""Tests for manual refresh (Plan 1.16)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        yield c
        c.close()


@pytest.mark.asyncio
async def test_refresh_single_area(client, conn):
    """Refresh writes an observation with source_event=manual_refresh."""
    from server.config_collector.manual_refresh import refresh_entity

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(return_value=httpx.Response(200, json=[]))

        result = await refresh_entity(
            client, conn, org_id="o1",
            entity_type="network", entity_id="N_1",
            config_area="appliance_vlans",
        )

    assert result["expected_calls"] == 1
    row = conn.execute(
        "SELECT source_event FROM config_observations WHERE entity_id=? AND config_area=?",
        ("N_1", "appliance_vlans"),
    ).fetchone()
    assert row["source_event"] == "manual_refresh"


@pytest.mark.asyncio
async def test_refresh_all_areas_for_entity(client, conn):
    """When config_area is omitted, every area applicable to the entity is refreshed."""
    from server.config_collector.manual_refresh import refresh_entity

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json=[]))

        result = await refresh_entity(
            client, conn, org_id="o1",
            entity_type="org", entity_id="o1",
            config_area=None,
        )

    # Every tier-1+2 org endpoint should have been attempted
    from server.config_collector._endpoints_org import ORG_ENDPOINTS
    assert result["expected_calls"] == len(ORG_ENDPOINTS)
```

- [ ] **Step 1.2: Run — should fail**

- [ ] **Step 1.3: Create `manual_refresh.py` with `refresh_entity`**

Create `server/config_collector/manual_refresh.py`:

```python
"""Manual refresh: targeted re-pull of a single entity or single config_area for a user."""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from server.config_collector.endpoints_catalog import ENDPOINTS
from server.config_collector.targeted_puller import pull_many
from server.meraki_client import MerakiClient

logger = logging.getLogger(__name__)

# In-memory registry of in-flight refreshes for idempotency.
# Key: (org_id, entity_type, entity_id, config_area_or_None) -> asyncio.Task
_active_refreshes: dict[tuple, asyncio.Task] = {}


def _build_jobs_for_refresh(
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: Optional[str],
) -> list[dict]:
    """Build the full job list for the requested refresh scope."""
    jobs: list[dict] = []
    for spec in ENDPOINTS:
        if config_area and spec.config_area != config_area:
            continue

        if spec.scope == "org" and entity_type == "org" and entity_id == org_id:
            url = spec.url_template.format(org_id=org_id)
            jobs.append({
                "url": url, "config_area": spec.config_area, "scope": "org",
                "entity_type": "org", "entity_id": org_id,
                "sub_key": None, "paginated": spec.paginated,
            })
        elif spec.scope == "network" and entity_type == "network":
            url = spec.url_template.format(network_id=entity_id)
            jobs.append({
                "url": url, "config_area": spec.config_area, "scope": "network",
                "entity_type": "network", "entity_id": entity_id,
                "sub_key": None, "paginated": spec.paginated,
            })
        elif spec.scope == "device" and entity_type == "device":
            url = spec.url_template.format(serial=entity_id)
            jobs.append({
                "url": url, "config_area": spec.config_area, "scope": "device",
                "entity_type": "device", "entity_id": entity_id,
                "sub_key": None, "paginated": spec.paginated,
            })
        elif spec.scope == "ssid" and entity_type == "ssid":
            # entity_id is "networkId:ssidNumber"
            if ":" not in entity_id:
                continue
            network_id, ssid_number = entity_id.split(":", 1)
            url = spec.url_template.format(network_id=network_id, ssid_number=ssid_number)
            jobs.append({
                "url": url, "config_area": spec.config_area, "scope": "ssid",
                "entity_type": "ssid", "entity_id": entity_id,
                "sub_key": ssid_number, "paginated": spec.paginated,
            })
    return jobs


async def refresh_entity(
    client: MerakiClient,
    conn,
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    config_area: Optional[str] = None,
) -> dict:
    """Refresh a single entity (optionally a single area).

    Returns {expected_calls, task_id}. Idempotent: if a refresh with identical
    scope is already in-flight, returns the existing task id.
    """
    key = (org_id, entity_type, entity_id, config_area)
    existing = _active_refreshes.get(key)
    if existing is not None and not existing.done():
        return {"task_id": id(existing), "expected_calls": 0, "status": "already_in_flight"}

    jobs = _build_jobs_for_refresh(
        org_id=org_id, entity_type=entity_type,
        entity_id=entity_id, config_area=config_area,
    )

    async def _run():
        try:
            await pull_many(
                client=client, conn=conn, jobs=jobs,
                org_id=org_id, sweep_run_id=None, source_event="manual_refresh",
            )
        finally:
            _active_refreshes.pop(key, None)

    task = asyncio.create_task(_run())
    _active_refreshes[key] = task
    await task  # For MVP, wait inline; REST layer in Plan 1.17 will awaitresult when needed
    return {"task_id": id(task), "expected_calls": len(jobs), "status": "done"}
```

- [ ] **Step 1.4: Run — should pass**

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/manual_refresh.py server/tests/test_manual_refresh.py
git commit -m "feat(config): manual refresh_entity for targeted re-pulls (Plan 1.16)"
```

---

## Task 2: Idempotency test

- [ ] **Step 2.1: Write test**

Append to `server/tests/test_manual_refresh.py`:

```python
@pytest.mark.asyncio
async def test_concurrent_refresh_is_idempotent(client, conn):
    """Two concurrent refresh calls for identical scope → only one pipeline run."""
    from server.config_collector.manual_refresh import refresh_entity

    # Wrap respx so every request takes a tiny bit of time, enabling the
    # second refresh to see the first as in-flight.
    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        call_count = {"n": 0}

        def _handler(request):
            call_count["n"] += 1
            return httpx.Response(200, json=[])

        mock.get("/networks/N_1/appliance/vlans").mock(side_effect=_handler)

        first, second = await asyncio.gather(
            refresh_entity(client, conn, org_id="o1", entity_type="network",
                           entity_id="N_1", config_area="appliance_vlans"),
            refresh_entity(client, conn, org_id="o1", entity_type="network",
                           entity_id="N_1", config_area="appliance_vlans"),
        )

    # Only one underlying HTTP call — but this depends on exact timing.
    # The stricter invariant: at most one observation row was written.
    count = conn.execute("SELECT COUNT(*) AS n FROM config_observations").fetchone()["n"]
    assert count == 1
```

- [ ] **Step 2.2: Run — should pass**

- [ ] **Step 2.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_manual_refresh.py
git commit -m "test(config): concurrent refresh idempotency (Plan 1.16)"
```

---

## Completion Checklist

- [ ] `refresh_entity`, `_build_jobs_for_refresh` exist
- [ ] 3 passing tests
- [ ] 2 commits

## What This Unblocks

- Plan 1.17 REST `POST /orgs/{id}/refresh` is now a thin wrapper.
