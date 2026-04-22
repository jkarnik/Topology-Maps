# Plan 1.14 — Change-Log Poller

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** A background task per organization that polls `/organizations/{orgId}/configurationChanges` every 30 minutes (default), dedupes events against `config_change_events`, maps each event to affected endpoints via `event_to_endpoints()`, and runs targeted pulls via `pull_many()`. Includes the SSID reactive catch (any event with `ssidNumber` set pulls all per-SSID sub-endpoints for that SSID).

**Depends on:** Plans 1.04, 1.09, 1.10, 1.11, 1.12.
**Unblocks:** Plan 1.17 (REST exposes poller status), Plan 1.18 (WS emits `change_event.new`).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/config_collector/change_log_poller.py` | Create | `poll_once()`, `run_poller()` (long-lived loop) |
| `server/tests/test_change_log_poller.py` | Create | Tests with respx + mocked events |

---

## Task 1: `poll_once` — single poll + event dedup

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_change_log_poller.py`:

```python
"""Tests for change-log poller (Plan 1.14)."""
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
async def test_poll_once_stores_new_events(client, conn):
    from server.config_collector.change_log_poller import poll_once

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/configurationChanges").mock(return_value=httpx.Response(200, json=[
            {"ts": "2026-04-22T10:00:00Z", "page": "Security & SD-WAN > Addressing & VLANs",
             "label": "VLAN", "networkId": "N_1", "oldValue": "10", "newValue": "20"},
        ]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        summary = await poll_once(client, conn, org_id="o1", timespan=3600)

    assert summary["new_events"] == 1

    count = conn.execute("SELECT COUNT(*) AS n FROM config_change_events").fetchone()["n"]
    assert count == 1


@pytest.mark.asyncio
async def test_poll_once_dedupes_previously_seen(client, conn):
    from server.config_collector.change_log_poller import poll_once

    event = {
        "ts": "2026-04-22T10:00:00Z", "page": "Wireless > Access Control",
        "label": "Bandwidth limit", "networkId": "N_1",
        "oldValue": "11", "newValue": "24", "ssidNumber": 3,
    }

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/configurationChanges").mock(return_value=httpx.Response(200, json=[event, event]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        summary = await poll_once(client, conn, org_id="o1", timespan=3600)

    # Only one change_events row despite duplicate input
    count = conn.execute("SELECT COUNT(*) AS n FROM config_change_events").fetchone()["n"]
    assert count == 1
    assert summary["new_events"] == 1
    assert summary["duplicates"] == 1
```

- [ ] **Step 1.2: Run — should fail**

- [ ] **Step 1.3: Create `change_log_poller.py` with `poll_once`**

Create `server/config_collector/change_log_poller.py`:

```python
"""Change-log poller: fetch recent configurationChanges, dedupe, and trigger targeted pulls."""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, Optional

from server.config_collector.endpoints_catalog import event_to_endpoints, ENDPOINTS
from server.config_collector.store import (
    insert_change_event, get_change_events,
)
from server.config_collector.targeted_puller import pull_many
from server.meraki_client import MerakiClient

logger = logging.getLogger(__name__)


async def poll_once(
    client: MerakiClient,
    conn,
    *,
    org_id: str,
    timespan: int,
    progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> dict:
    """Fetch + store + dispatch targeted pulls for one poll cycle.

    Returns a summary: {new_events, duplicates, successes, skipped_unchanged, failures}.
    """
    events = await client.get_org_configuration_changes(org_id, timespan=timespan)

    new_event_ids: list[tuple[dict, int]] = []
    duplicates = 0
    for ev in events:
        row_id = insert_change_event(conn, org_id=org_id, event=ev)
        if row_id is None:
            duplicates += 1
        else:
            new_event_ids.append((ev, row_id))
            if progress_callback:
                await progress_callback({
                    "type": "change_event.new", "org_id": org_id,
                    "event_id": row_id, "network_id": ev.get("networkId"),
                    "label": ev.get("label"), "ts": ev.get("ts"),
                })

    jobs, change_id_by_key = _build_jobs_from_events(org_id, new_event_ids)

    summary = {
        "new_events": len(new_event_ids),
        "duplicates": duplicates,
        "successes": 0, "skipped_unchanged": 0, "failures": 0,
    }
    if jobs:
        pull_summary = await pull_many(
            client=client, conn=conn, jobs=jobs,
            org_id=org_id, sweep_run_id=None, source_event="change_log",
            change_event_id_by_key=change_id_by_key,
        )
        summary["successes"] = pull_summary.successes
        summary["skipped_unchanged"] = pull_summary.skipped_unchanged
        summary["failures"] = pull_summary.failures
    return summary


def _build_jobs_from_events(org_id: str, events_with_ids: list[tuple[dict, int]]):
    """Compute targeted-pull jobs from change events."""
    specs_by_area = {e.config_area: e for e in ENDPOINTS}
    jobs: list[dict] = []
    change_id_by_key: dict[tuple, int] = {}

    for ev, event_row_id in events_with_ids:
        affected_areas = event_to_endpoints(ev)
        network_id = ev.get("networkId")
        ssid_number = ev.get("ssidNumber")

        for area in affected_areas:
            spec = specs_by_area.get(area)
            if spec is None:
                logger.warning("event_to_endpoints produced unknown config_area %r", area)
                continue

            if spec.scope == "org":
                url = spec.url_template.format(org_id=org_id)
                job = {
                    "url": url, "config_area": area, "scope": "org",
                    "entity_type": "org", "entity_id": org_id,
                    "sub_key": None, "paginated": spec.paginated,
                }
            elif spec.scope == "network":
                if not network_id:
                    continue
                url = spec.url_template.format(network_id=network_id)
                job = {
                    "url": url, "config_area": area, "scope": "network",
                    "entity_type": "network", "entity_id": network_id,
                    "sub_key": None, "paginated": spec.paginated,
                }
            elif spec.scope == "ssid":
                if not network_id or ssid_number is None:
                    continue
                url = spec.url_template.format(network_id=network_id, ssid_number=ssid_number)
                job = {
                    "url": url, "config_area": area, "scope": "ssid",
                    "entity_type": "ssid", "entity_id": f"{network_id}:{ssid_number}",
                    "sub_key": str(ssid_number), "paginated": spec.paginated,
                }
            else:
                # device-scope not derivable from typical events — skip
                continue

            jobs.append(job)
            key = (job["entity_type"], job["entity_id"], job["config_area"], job.get("sub_key"))
            change_id_by_key.setdefault(key, event_row_id)

    return jobs, change_id_by_key
```

- [ ] **Step 1.4: Run — should pass**

- [ ] **Step 1.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/change_log_poller.py server/tests/test_change_log_poller.py
git commit -m "feat(config): poll_once single-cycle change-log poller (Plan 1.14)"
```

---

## Task 2: SSID reactive catch test

Verifies that an event with `ssidNumber` set triggers per-SSID sub-endpoint pulls (even if that SSID is disabled at the time).

- [ ] **Step 2.1: Write test**

Append to `server/tests/test_change_log_poller.py`:

```python
@pytest.mark.asyncio
async def test_ssid_event_triggers_sub_endpoint_pulls(client, conn):
    """An event with ssidNumber=3 triggers pulls of per-SSID sub-endpoints."""
    from server.config_collector.change_log_poller import poll_once

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get("/organizations/o1/configurationChanges").mock(return_value=httpx.Response(200, json=[
            {"ts": "2026-04-22T10:00:00Z", "page": "Wireless > Access Control",
             "label": "Bandwidth limit", "networkId": "N_W",
             "oldValue": "11", "newValue": "24", "ssidNumber": 3},
        ]))
        l3_mock = mock.get("/networks/N_W/wireless/ssids/3/firewall/l3FirewallRules").mock(return_value=httpx.Response(200, json={"rules": []}))
        l7_mock = mock.get("/networks/N_W/wireless/ssids/3/firewall/l7FirewallRules").mock(return_value=httpx.Response(200, json={"rules": []}))
        ssids_mock = mock.get("/networks/N_W/wireless/ssids").mock(return_value=httpx.Response(200, json=[]))
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json={}))

        await poll_once(client, conn, org_id="o1", timespan=3600)

    assert l3_mock.call_count >= 1
    assert l7_mock.call_count >= 1
    assert ssids_mock.call_count >= 1
```

- [ ] **Step 2.2: Run — should pass (handled by event_to_endpoints reactive catch from Plan 1.04)**

- [ ] **Step 2.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/tests/test_change_log_poller.py
git commit -m "test(config): SSID reactive catch in change-log poller (Plan 1.14)"
```

---

## Task 3: `run_poller` — long-lived loop

- [ ] **Step 3.1: Write test**

Append to `server/tests/test_change_log_poller.py`:

```python
@pytest.mark.asyncio
async def test_run_poller_exits_on_cancel(client, conn):
    """run_poller is a long-lived loop; verify it exits cleanly on cancel."""
    from server.config_collector.change_log_poller import run_poller

    async with respx.mock(base_url="https://api.meraki.com/api/v1", assert_all_called=False) as mock:
        mock.get(url__regex=r".*").mock(return_value=httpx.Response(200, json=[]))

        task = asyncio.create_task(run_poller(client, conn, org_id="o1", interval=60, timespan=3600))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
```

- [ ] **Step 3.2: Run — should fail**

- [ ] **Step 3.3: Implement `run_poller`**

Append to `server/config_collector/change_log_poller.py`:

```python
async def run_poller(
    client: MerakiClient,
    conn,
    *,
    org_id: str,
    interval: int = 1800,
    timespan: int = 3600,
    progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    """Infinite loop: poll_once → sleep(interval) → poll_once → ...

    Runs until the task is cancelled. Failures from poll_once are logged
    and the loop continues (we never want a transient Meraki hiccup to
    kill the poller entirely).
    """
    logger.info("starting change-log poller for org %s (interval=%ds)", org_id, interval)
    while True:
        try:
            await poll_once(
                client, conn,
                org_id=org_id, timespan=timespan, progress_callback=progress_callback,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("poll_once failed for org %s; will retry on next cycle", org_id)
        await asyncio.sleep(interval)
```

- [ ] **Step 3.4: Run — should pass**

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/config_collector/change_log_poller.py server/tests/test_change_log_poller.py
git commit -m "feat(config): run_poller long-lived loop with cancel handling (Plan 1.14)"
```

---

## Completion Checklist

- [ ] `poll_once`, `run_poller` exist
- [ ] ~4 passing tests covering single poll, dedup, SSID reactive, cancel
- [ ] 3 commits

## What This Unblocks

- Plan 1.17 exposes `run_poller` status via REST.
- Plan 1.18 wires its `progress_callback` to WebSocket broadcasts.

