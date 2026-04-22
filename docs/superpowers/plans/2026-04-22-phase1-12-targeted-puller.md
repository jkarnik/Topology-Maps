# Plan 1.12 — Targeted Puller

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Implement a single orchestrator that: takes a list of fetch jobs (output of `expand_for_org()` or derived from change-log events), coalesces duplicates, fetches each through the rate-limited client, runs responses through the redactor, and writes observations via the storage layer. Returns per-job outcomes (success / failure / skipped-unchanged).

**Architecture:** One module `targeted_puller.py` with an async function `pull_many(client, conn, jobs, *, sweep_run_id, source_event, change_event_id_by_job=None) -> PullSummary`. Jobs are dicts matching the shape produced by `expand_for_org()`. Coalescing key is `(entity_type, entity_id, config_area, sub_key)` — if multiple jobs share the same key (e.g. from multiple change events), the URL is fetched once.

**Depends on:** Plans 1.03 (redactor), 1.04 (catalog), 1.05 (pagination), 1.06–1.09 (client methods), 1.10 + 1.11 (storage).
**Unblocks:** Plans 1.13, 1.14, 1.15, 1.16.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/targeted_puller.py` | Create | `pull_many()`, `PullSummary` |
| `server/tests/test_targeted_puller.py` | Create | End-to-end integration tests with respx + in-memory DB |

---

## Task 1: `PullSummary` dataclass + job coalescing

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_targeted_puller.py`:

```python
"""Tests for targeted_puller (Plan 1.12)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import respx
import httpx

from server.meraki_client import MerakiClient


@pytest.fixture
def conn(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "topology.db"
        from server import database
        monkeypatch.setattr(database, "DB_PATH", db_path)
        c = database.get_connection()
        yield c
        c.close()


@pytest.fixture
def client():
    return MerakiClient(api_key="test-key")


def test_coalesce_removes_duplicates():
    from server.config_collector.targeted_puller import coalesce_jobs

    jobs = [
        {"url": "/a", "config_area": "vlans", "entity_type": "network", "entity_id": "N1", "sub_key": None, "paginated": False, "scope": "network"},
        {"url": "/a", "config_area": "vlans", "entity_type": "network", "entity_id": "N1", "sub_key": None, "paginated": False, "scope": "network"},
        {"url": "/b", "config_area": "ports", "entity_type": "device", "entity_id": "Q-A", "sub_key": None, "paginated": False, "scope": "device"},
    ]
    result = list(coalesce_jobs(jobs))
    assert len(result) == 2
    assert {r["url"] for r in result} == {"/a", "/b"}


def test_coalesce_treats_different_sub_keys_as_distinct():
    from server.config_collector.targeted_puller import coalesce_jobs

    jobs = [
        {"url": "/ssids/0/fw", "config_area": "wireless_ssid_l3_firewall", "entity_type": "ssid", "entity_id": "N:0", "sub_key": "0", "paginated": False, "scope": "ssid"},
        {"url": "/ssids/1/fw", "config_area": "wireless_ssid_l3_firewall", "entity_type": "ssid", "entity_id": "N:1", "sub_key": "1", "paginated": False, "scope": "ssid"},
    ]
    assert len(list(coalesce_jobs(jobs))) == 2
```

- [ ] **Step 1.2: Run — should fail**

- [ ] **Step 1.3: Create module with `coalesce_jobs` and summary**

Create `server/config_collector/targeted_puller.py`:

```python
"""Targeted fetch pipeline: rate-limited fetch → redact → store.

One async function `pull_many` orchestrates the full pipeline for a list
of jobs (dicts as produced by `endpoints_catalog.expand_for_org`).
Coalesces duplicate entity/area requests, logs per-job outcomes, and
writes observations via the storage layer.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


@dataclass
class PullSummary:
    successes: int = 0
    skipped_unchanged: int = 0
    failures: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)  # (url, msg)


def coalesce_jobs(jobs: Iterable[dict]) -> Iterable[dict]:
    """Yield unique jobs keyed by (entity_type, entity_id, config_area, sub_key).

    First occurrence wins. Duplicates are dropped.
    """
    seen: set[tuple] = set()
    for j in jobs:
        key = (j["entity_type"], j["entity_id"], j["config_area"], j.get("sub_key"))
        if key in seen:
            continue
        seen.add(key)
        yield j
```

- [ ] **Step 1.4: Run — should pass**

Expected: 2 tests pass.

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/targeted_puller.py server/tests/test_targeted_puller.py
git commit -m "feat(config): coalesce_jobs + PullSummary (Plan 1.12)"
```

---

## Task 2: `pull_many` — fetch → redact → store for one job

- [ ] **Step 2.1: Write failing test**

Append to `server/tests/test_targeted_puller.py`:

```python
@pytest.mark.asyncio
async def test_pull_many_single_job_writes_observation(client, conn):
    from server.config_collector.targeted_puller import pull_many

    jobs = [{
        "url": "/networks/N_1/appliance/vlans",
        "config_area": "appliance_vlans",
        "entity_type": "network",
        "entity_id": "N_1",
        "sub_key": None,
        "paginated": False,
        "scope": "network",
    }]

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(
            return_value=httpx.Response(200, json=[{"id": 10, "name": "Data"}])
        )
        summary = await pull_many(
            client=client, conn=conn, jobs=jobs,
            org_id="o1", sweep_run_id=None, source_event="manual_refresh",
        )
    assert summary.successes == 1
    assert summary.failures == 0

    # Observation row exists
    row = conn.execute(
        "SELECT * FROM config_observations WHERE entity_id=? AND config_area=?",
        ("N_1", "appliance_vlans"),
    ).fetchone()
    assert row is not None
    assert row["source_event"] == "manual_refresh"


@pytest.mark.asyncio
async def test_pull_many_skips_unchanged_hash(client, conn):
    """Same payload twice → second call is skipped (no new row)."""
    from server.config_collector.targeted_puller import pull_many

    job = {
        "url": "/networks/N_1/appliance/vlans",
        "config_area": "appliance_vlans",
        "entity_type": "network", "entity_id": "N_1",
        "sub_key": None, "paginated": False, "scope": "network",
    }

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(
            return_value=httpx.Response(200, json=[{"id": 10}])
        )
        await pull_many(client=client, conn=conn, jobs=[job], org_id="o1", sweep_run_id=None, source_event="change_log")
        summary = await pull_many(client=client, conn=conn, jobs=[job], org_id="o1", sweep_run_id=None, source_event="change_log")

    assert summary.successes == 0
    assert summary.skipped_unchanged == 1

    # Still only one row
    count = conn.execute("SELECT COUNT(*) AS n FROM config_observations").fetchone()["n"]
    assert count == 1


@pytest.mark.asyncio
async def test_pull_many_records_http_failure(client, conn):
    from server.config_collector.targeted_puller import pull_many

    job = {
        "url": "/networks/N_1/appliance/vlans",
        "config_area": "appliance_vlans",
        "entity_type": "network", "entity_id": "N_1",
        "sub_key": None, "paginated": False, "scope": "network",
    }

    async with respx.mock(base_url="https://api.meraki.com/api/v1") as mock:
        mock.get("/networks/N_1/appliance/vlans").mock(return_value=httpx.Response(500, json={"error": "oops"}))
        summary = await pull_many(client=client, conn=conn, jobs=[job], org_id="o1", sweep_run_id=None, source_event="baseline")

    assert summary.failures == 1
    assert summary.successes == 0
    assert len(summary.errors) == 1
    assert "/networks/N_1/appliance/vlans" in summary.errors[0][0]
```

- [ ] **Step 2.2: Run — should fail**

- [ ] **Step 2.3: Implement `pull_many`**

Append to `server/config_collector/targeted_puller.py`:

```python
from server.config_collector.redactor import redact
from server.config_collector.store import upsert_blob, insert_observation_if_changed
from server.meraki_client import MerakiClient


async def _fetch_one(client: MerakiClient, job: dict) -> Any:
    """Issue the HTTP GET for a single job, respecting pagination."""
    url = job["url"]
    if job.get("paginated"):
        return await client._get_paginated(url)
    return await client._get(url)


async def pull_many(
    *,
    client: MerakiClient,
    conn,
    jobs: list[dict],
    org_id: str,
    sweep_run_id: Optional[int],
    source_event: str,
    change_event_id_by_key: Optional[dict] = None,
) -> PullSummary:
    """Run the fetch → redact → store pipeline for each (coalesced) job."""
    summary = PullSummary()
    change_event_id_by_key = change_event_id_by_key or {}

    for job in coalesce_jobs(jobs):
        key = (job["entity_type"], job["entity_id"], job["config_area"], job.get("sub_key"))
        try:
            raw = await _fetch_one(client, job)
        except Exception as exc:  # includes httpx.HTTPStatusError, MaxPagesExceeded, network errors
            logger.warning("pull_many failed for %s: %s", job["url"], exc)
            summary.failures += 1
            summary.errors.append((job["url"], str(exc)))
            continue

        redacted_str, hash_hex, byte_size, hot_cols = redact(raw, job["config_area"])
        upsert_blob(conn, hash_hex=hash_hex, payload=redacted_str, byte_size=byte_size)

        wrote = insert_observation_if_changed(
            conn,
            org_id=org_id,
            entity_type=job["entity_type"],
            entity_id=job["entity_id"],
            config_area=job["config_area"],
            sub_key=job.get("sub_key"),
            hash_hex=hash_hex,
            source_event=source_event,
            change_event_id=change_event_id_by_key.get(key),
            sweep_run_id=sweep_run_id,
            hot_columns=hot_cols,
        )
        if wrote:
            summary.successes += 1
        else:
            summary.skipped_unchanged += 1

    return summary
```

- [ ] **Step 2.4: Run — should pass**

Expected: 5 tests pass.

- [ ] **Step 2.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/targeted_puller.py server/tests/test_targeted_puller.py
git commit -m "feat(config): pull_many orchestrator (fetch → redact → store) (Plan 1.12)"
```

---

## Completion Checklist

- [ ] `pull_many`, `coalesce_jobs`, `PullSummary` exist
- [ ] 5+ passing tests covering success, unchanged-skip, HTTP failure
- [ ] 2 commits

## What This Unblocks

- Plan 1.13 (baseline runner) calls `pull_many` for all enumerated jobs.
- Plan 1.14 (change-log poller) calls `pull_many` for event-driven jobs.
- Plan 1.16 (manual refresh) calls `pull_many` for a single job.
