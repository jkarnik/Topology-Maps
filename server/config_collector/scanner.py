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
