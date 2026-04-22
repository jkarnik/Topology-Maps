# Plan 1.15 — Anti-Drift Sweep

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Weekly full re-pull that annotates each resulting observation with either `anti_drift_confirm` (hash matched previous) or `anti_drift_discrepancy` (hash differed, suggesting a change the change-log missed). Reuses the baseline runner but with a different `source_event`.

**Depends on:** Plans 1.10, 1.12, 1.13.
**Unblocks:** Plan 1.17 (manual sweep trigger endpoint).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/scanner.py` | Modify | Add `run_anti_drift_sweep()` |
| `server/tests/test_anti_drift_scanner.py` | Create | Tests verifying source_event annotation logic |

---

## Task 1: `run_anti_drift_sweep` reuses baseline with hash-comparison source event

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_anti_drift_scanner.py`:

```python
"""Tests for anti-drift sweep (Plan 1.15)."""
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
async def test_anti_drift_confirms_matching_hash(client, conn):
    """If the fresh payload hash matches the latest stored, source_event=anti_drift_confirm."""
    from server.config_collector.scanner import run_anti_drift_sweep
    from server.config_collector.store import insert_observation_if_changed

    # Seed a blob + observation matching what the mock will return
    from server.config_collector.redactor import redact
    admins_body = [{"id": "a1", "name": "Alice"}]
    _, hash_hex, byte_size, _ = redact(admins_body, "org_admins")
    conn.execute(
        "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
        (hash_hex, "seed_payload", byte_size, "2026-04-15T00:00:00Z"),
    )
    conn.commit()
    insert_observation_if_changed(
        conn, org_id="o1", entity_type="org", entity_id="o1",
        config_area="org_admins", sub_key=None, hash_hex=hash_hex,
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/admins").mock(return_value=httpx.Response(200, json=admins_body))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        await run_anti_drift_sweep(client, conn, org_id="o1")

    # Expect at least one anti_drift_confirm row for admins
    confirms = conn.execute(
        """SELECT * FROM config_observations
           WHERE config_area='org_admins' AND source_event='anti_drift_confirm'"""
    ).fetchall()
    assert len(confirms) >= 1


@pytest.mark.asyncio
async def test_anti_drift_discrepancy_on_hash_mismatch(client, conn):
    """If the fresh payload differs from latest stored, source_event=anti_drift_discrepancy."""
    from server.config_collector.scanner import run_anti_drift_sweep
    from server.config_collector.store import insert_observation_if_changed

    # Seed with DIFFERENT content (old hash)
    conn.execute(
        "INSERT INTO config_blobs (hash, payload, byte_size, first_seen_at) VALUES (?,?,?,?)",
        ("old_hash", "old_payload", 11, "2026-04-15T00:00:00Z"),
    )
    conn.commit()
    insert_observation_if_changed(
        conn, org_id="o1", entity_type="org", entity_id="o1",
        config_area="org_admins", sub_key=None, hash_hex="old_hash",
        source_event="baseline", change_event_id=None, sweep_run_id=None,
        hot_columns={"name_hint": None, "enabled_hint": None},
    )

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/networks").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/devices").mock(return_value=httpx.Response(200, json=[]))
        mock.get("/organizations/o1/admins").mock(return_value=httpx.Response(200, json=[{"id": "new", "name": "Changed"}]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        await run_anti_drift_sweep(client, conn, org_id="o1")

    discrepancies = conn.execute(
        """SELECT * FROM config_observations
           WHERE config_area='org_admins' AND source_event='anti_drift_discrepancy'"""
    ).fetchall()
    assert len(discrepancies) >= 1
```

- [ ] **Step 1.2: Run — should fail (no `run_anti_drift_sweep`)**

- [ ] **Step 1.3: Implement `run_anti_drift_sweep`**

Append to `server/config_collector/scanner.py`:

```python
from server.config_collector.redactor import redact
from server.config_collector.store import (
    upsert_blob, get_latest_observation,
)


async def run_anti_drift_sweep(
    client: MerakiClient,
    conn,
    *,
    org_id: str,
    progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> int:
    """Run a full sweep and annotate each observation with confirm or discrepancy.

    Unlike baseline, anti-drift *always* writes a row per (entity, area): the
    source_event distinguishes confirms (hash matched) from discrepancies
    (hash changed without a corresponding change-log event).
    """
    # Idempotency
    active = get_active_sweep_run(conn, org_id=org_id, kind="anti_drift")
    if active is not None:
        return active["id"]

    composition = await enumerate_org_composition(client, org_id)
    jobs = list(coalesce_jobs(expand_for_org(
        org_id=org_id,
        networks=composition["networks"],
        devices_by_network=composition["devices_by_network"],
        enabled_ssids_by_network=composition["enabled_ssids_by_network"],
    )))

    run_id = create_sweep_run(conn, org_id=org_id, kind="anti_drift", total_calls=len(jobs))
    mark_sweep_running(conn, run_id)
    if progress_callback:
        await progress_callback({
            "type": "sweep.started", "sweep_run_id": run_id,
            "org_id": org_id, "kind": "anti_drift", "total_calls": len(jobs),
        })

    completed = failed = 0
    try:
        for idx, job in enumerate(jobs):
            try:
                if job.get("paginated"):
                    raw = await client._get_paginated(job["url"])
                else:
                    raw = await client._get(job["url"])
            except Exception as exc:
                logger.warning("anti-drift fetch failed for %s: %s", job["url"], exc)
                failed += 1
                continue

            redacted_str, hash_hex, byte_size, hot = redact(raw, job["config_area"])
            upsert_blob(conn, hash_hex=hash_hex, payload=redacted_str, byte_size=byte_size)

            latest = get_latest_observation(
                conn, org_id=org_id,
                entity_type=job["entity_type"], entity_id=job["entity_id"],
                config_area=job["config_area"], sub_key=job.get("sub_key"),
            )
            source = "anti_drift_confirm" if (latest and latest["hash"] == hash_hex) else "anti_drift_discrepancy"

            if source == "anti_drift_discrepancy":
                logger.warning(
                    "Config drift detected for %s/%s (area=%s): not explained by change log",
                    job["entity_type"], job["entity_id"], job["config_area"],
                )

            insert_observation_if_changed(
                conn, org_id=org_id,
                entity_type=job["entity_type"], entity_id=job["entity_id"],
                config_area=job["config_area"], sub_key=job.get("sub_key"),
                hash_hex=hash_hex, source_event=source,
                change_event_id=None, sweep_run_id=run_id,
                hot_columns=hot,
            )
            completed += 1

            if progress_callback and (idx + 1) % 20 == 0:
                await progress_callback({
                    "type": "sweep.progress", "sweep_run_id": run_id,
                    "completed_calls": completed, "total_calls": len(jobs),
                })

        increment_sweep_counters(conn, run_id, completed=completed, failed=failed)
        mark_sweep_complete(conn, run_id)
        if progress_callback:
            await progress_callback({"type": "sweep.completed", "sweep_run_id": run_id, "org_id": org_id})
    except Exception as exc:
        mark_sweep_failed(conn, run_id, error_summary=str(exc))
        raise

    return run_id
```

- [ ] **Step 1.4: Run — should pass**

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/scanner.py server/tests/test_anti_drift_scanner.py
git commit -m "feat(config): run_anti_drift_sweep with confirm/discrepancy annotation (Plan 1.15)"
```

---

## Completion Checklist

- [ ] `run_anti_drift_sweep` exists in `scanner.py`
- [ ] 2 passing tests (confirm + discrepancy paths)
- [ ] 1 commit

## What This Unblocks

- Plan 1.17 REST endpoint `POST /orgs/{id}/sweep` dispatches this function.
- Weekly cron scheduling is done at main.py startup during Plan 1.17.
