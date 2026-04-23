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

    Returns {expected_calls, task_id, status}. Idempotent.
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
    await task
    return {"task_id": id(task), "expected_calls": len(jobs), "status": "done"}
