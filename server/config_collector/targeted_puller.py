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
