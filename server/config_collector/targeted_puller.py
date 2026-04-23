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
    errors: list[tuple[str, str]] = field(default_factory=list)


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
        except Exception as exc:
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
