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
    """Fetch + store + dispatch targeted pulls for one poll cycle."""
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
                continue

            jobs.append(job)
            key = (job["entity_type"], job["entity_id"], job["config_area"], job.get("sub_key"))
            change_id_by_key.setdefault(key, event_row_id)

    return jobs, change_id_by_key


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
