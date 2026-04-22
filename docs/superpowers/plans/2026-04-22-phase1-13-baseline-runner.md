# Plan 1.13 — Baseline Runner

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Orchestrate a one-time full baseline sweep for an organization: enumerate networks + devices + enabled SSIDs, expand all Tier-1+2 endpoints via `expand_for_org()`, skip jobs already completed for the current sweep (resumability), and run them through `pull_many()`. Emits progress events for later WebSocket integration.

**Architecture:** One module `scanner.py` with `run_baseline(client, conn, org_id, *, resume_run_id=None) -> int`. Returns the `sweep_run_id`. Progress is surfaced by invoking a caller-supplied async `progress_callback` (WebSocket wiring is Plan 1.18).

**Depends on:** Plans 1.04 (catalog), 1.05-1.09 (client methods), 1.10-1.11 (storage), 1.12 (pull_many).
**Unblocks:** Plan 1.15 (anti-drift sweep reuses this), Plan 1.17 (REST API triggers it).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/scanner.py` | Create | `run_baseline()`, `enumerate_org_composition()` helpers |
| `server/tests/test_baseline_scanner.py` | Create | Integration tests with respx + in-memory DB |

---

## Task 1: `enumerate_org_composition` helper

Gathers the inputs needed for `expand_for_org()`: networks, devices per network, enabled SSIDs per network.

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_baseline_scanner.py`:

```python
"""Tests for baseline scanner (Plan 1.13)."""
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
async def test_enumerate_org_composition(client):
    from server.config_collector.scanner import enumerate_org_composition

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[
            {"id": "N_1", "name": "Store 1", "productTypes": ["appliance", "switch", "wireless"]},
            {"id": "N_2", "name": "Store 2", "productTypes": ["wireless"]},
        ]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[
            {"serial": "Q2SW-1", "networkId": "N_1", "productType": "switch"},
            {"serial": "Q2MR-1", "networkId": "N_1", "productType": "wireless"},
            {"serial": "Q2MR-2", "networkId": "N_2", "productType": "wireless"},
        ]))
        mock.get("/networks/N_1/wireless/ssids").mock(return_value=httpx.Response(200, json=[
            {"number": 0, "enabled": True},
            {"number": 1, "enabled": False},
            {"number": 2, "enabled": True},
        ]))
        mock.get("/networks/N_2/wireless/ssids").mock(return_value=httpx.Response(200, json=[
            {"number": 0, "enabled": True},
        ]))

        composition = await enumerate_org_composition(client, org_id="o1")

    assert len(composition["networks"]) == 2
    assert composition["devices_by_network"]["N_1"] == [
        {"serial": "Q2SW-1", "networkId": "N_1", "productType": "switch"},
        {"serial": "Q2MR-1", "networkId": "N_1", "productType": "wireless"},
    ]
    assert composition["enabled_ssids_by_network"]["N_1"] == [0, 2]
    assert composition["enabled_ssids_by_network"]["N_2"] == [0]
```

- [ ] **Step 1.2: Run — should fail**

- [ ] **Step 1.3: Create scanner module with `enumerate_org_composition`**

Create `server/config_collector/scanner.py`:

```python
"""Baseline scanner — enumerate and fetch all Tier-1+2 configs for an org."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from server.config_collector.endpoints_catalog import expand_for_org
from server.config_collector.store import (
    create_sweep_run, mark_sweep_running, mark_sweep_complete,
    mark_sweep_failed, increment_sweep_counters,
    list_completed_entity_areas, get_active_sweep_run,
)
from server.config_collector.targeted_puller import pull_many, coalesce_jobs
from server.meraki_client import MerakiClient

logger = logging.getLogger(__name__)


async def enumerate_org_composition(
    client: MerakiClient,
    org_id: str,
) -> dict:
    """Gather {networks, devices_by_network, enabled_ssids_by_network} for expand_for_org."""
    networks = await client._get(f"/organizations/{org_id}/networks")

    all_devices = await client._get(f"/organizations/{org_id}/devices")
    devices_by_network: dict[str, list[dict]] = {n["id"]: [] for n in networks}
    for d in all_devices:
        nid = d.get("networkId")
        if nid in devices_by_network:
            devices_by_network[nid].append(d)

    enabled_ssids_by_network: dict[str, list[int]] = {}
    for n in networks:
        if "wireless" in (n.get("productTypes") or []):
            ssids = await client._get(f"/networks/{n['id']}/wireless/ssids")
            enabled_ssids_by_network[n["id"]] = [
                s["number"] for s in ssids if s.get("enabled") is True
            ]
        else:
            enabled_ssids_by_network[n["id"]] = []

    return {
        "networks": networks,
        "devices_by_network": devices_by_network,
        "enabled_ssids_by_network": enabled_ssids_by_network,
    }
```

- [ ] **Step 1.4: Run — should pass**

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/scanner.py server/tests/test_baseline_scanner.py
git commit -m "feat(config): enumerate_org_composition helper (Plan 1.13)"
```

---

## Task 2: `run_baseline` — full pipeline

- [ ] **Step 2.1: Write failing test**

Append to `server/tests/test_baseline_scanner.py`:

```python
@pytest.mark.asyncio
async def test_run_baseline_writes_observations_and_marks_complete(client, conn):
    """Minimal happy-path baseline: one wireless-only network, one AP."""
    from server.config_collector.scanner import run_baseline

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        # Composition enumeration
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[
            {"id": "N_W", "productTypes": ["wireless"]},
        ]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[
            {"serial": "Q2MR-1", "networkId": "N_W", "productType": "wireless"},
        ]))
        mock.get("/networks/N_W/wireless/ssids").mock(return_value=httpx.Response(200, json=[
            {"number": 0, "enabled": True},
        ]))
        # Any other GET returns an empty success
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        run_id = await run_baseline(client, conn, org_id="o1")

    # Sweep run ended in 'complete'
    row = conn.execute("SELECT status FROM config_sweep_runs WHERE id=?", (run_id,)).fetchone()
    assert row["status"] == "complete"

    # At least one observation was written
    count = conn.execute("SELECT COUNT(*) AS n FROM config_observations").fetchone()["n"]
    assert count > 0
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Implement `run_baseline`**

Append to `server/config_collector/scanner.py`:

```python
async def run_baseline(
    client: MerakiClient,
    conn,
    *,
    org_id: str,
    progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    resume_run_id: Optional[int] = None,
) -> int:
    """Run a full Tier-1+2 baseline sweep for `org_id`. Returns the sweep_run_id.

    If `resume_run_id` is provided, skip jobs already completed under that
    run. Otherwise create a new sweep.
    """
    # Idempotency: reuse an active sweep if one already exists
    if resume_run_id is None:
        active = get_active_sweep_run(conn, org_id=org_id, kind="baseline")
        if active is not None:
            return active["id"]

    composition = await enumerate_org_composition(client, org_id)
    all_jobs = list(coalesce_jobs(expand_for_org(
        org_id=org_id,
        networks=composition["networks"],
        devices_by_network=composition["devices_by_network"],
        enabled_ssids_by_network=composition["enabled_ssids_by_network"],
    )))

    if resume_run_id is not None:
        run_id = resume_run_id
        done = list_completed_entity_areas(conn, sweep_run_id=run_id)
        remaining = [j for j in all_jobs if (
            j["entity_type"], j["entity_id"], j["config_area"], j.get("sub_key")
        ) not in done]
    else:
        run_id = create_sweep_run(conn, org_id=org_id, kind="baseline", total_calls=len(all_jobs))
        remaining = all_jobs

    mark_sweep_running(conn, run_id)

    if progress_callback:
        await progress_callback({
            "type": "sweep.started", "sweep_run_id": run_id,
            "org_id": org_id, "kind": "baseline", "total_calls": len(all_jobs),
        })

    try:
        CHUNK = 20
        for i in range(0, len(remaining), CHUNK):
            chunk = remaining[i:i + CHUNK]
            summary = await pull_many(
                client=client, conn=conn, jobs=chunk,
                org_id=org_id, sweep_run_id=run_id, source_event="baseline",
            )
            increment_sweep_counters(
                conn, run_id,
                completed=summary.successes + summary.skipped_unchanged,
                failed=summary.failures,
            )
            if progress_callback:
                await progress_callback({
                    "type": "sweep.progress", "sweep_run_id": run_id,
                    "completed_calls": i + len(chunk), "total_calls": len(all_jobs),
                })

        mark_sweep_complete(conn, run_id)
        if progress_callback:
            await progress_callback({
                "type": "sweep.completed", "sweep_run_id": run_id, "org_id": org_id,
            })
    except Exception as exc:
        logger.exception("run_baseline failed")
        mark_sweep_failed(conn, run_id, error_summary=str(exc))
        if progress_callback:
            await progress_callback({
                "type": "sweep.failed", "sweep_run_id": run_id,
                "org_id": org_id, "error_summary": str(exc),
            })
        raise

    return run_id
```

- [ ] **Step 2.4: Run — should pass**

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/scanner.py server/tests/test_baseline_scanner.py
git commit -m "feat(config): run_baseline orchestrator with progress callbacks (Plan 1.13)"
```

---

## Task 3: Resumability test

- [ ] **Step 3.1: Write failing test**

Append to `server/tests/test_baseline_scanner.py`:

```python
@pytest.mark.asyncio
async def test_run_baseline_resume_skips_completed(client, conn):
    """Re-running with resume_run_id only fetches remaining jobs."""
    from server.config_collector.scanner import run_baseline
    from server.config_collector.store import create_sweep_run, insert_observation_if_changed

    # Seed a sweep + one completed observation
    run_id = create_sweep_run(conn, org_id="o1", kind="baseline", total_calls=100)
    conn.execute("INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
                 ("seed", "{}", 2, "t"))
    conn.commit()
    insert_observation_if_changed(
        conn, org_id="o1", entity_type="org", entity_id="o1",
        config_area="org_admins", sub_key=None, hash_hex="seed",
        source_event="baseline", change_event_id=None, sweep_run_id=run_id,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[]))
        admins_mock = mock.get("/organizations/o1/admins").mock(return_value=httpx.Response(200, json=[]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        await run_baseline(client, conn, org_id="o1", resume_run_id=run_id)

    # The /admins endpoint was NOT fetched this run (already completed)
    assert admins_mock.call_count == 0
```

- [ ] **Step 3.2: Run — should pass (implementation already handles this)**

Expected: The resume path in `run_baseline` skips completed jobs.

- [ ] **Step 3.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_baseline_scanner.py
git commit -m "test(config): resumability skips previously-completed entity/area (Plan 1.13)"
```

---

## Completion Checklist

- [ ] `enumerate_org_composition`, `run_baseline` exist
- [ ] ~3 passing tests
- [ ] 3 commits

## What This Unblocks

- Plan 1.15 (anti-drift sweep) subclasses/reuses this with `kind='anti_drift'`.
- Plan 1.17 (REST API) `POST /orgs/{id}/baseline` triggers `run_baseline`.
- Plan 1.18 (WebSocket) wires `progress_callback` to the WS channel.

