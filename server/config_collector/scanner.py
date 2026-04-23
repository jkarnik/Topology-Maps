"""Baseline scanner — enumerate and fetch all Tier-1+2 configs for an org."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from server.config_collector.endpoints_catalog import expand_for_org
from server.config_collector.redactor import redact
from server.config_collector.store import (
    create_sweep_run, mark_sweep_running, mark_sweep_complete,
    mark_sweep_failed, increment_sweep_counters,
    list_completed_entity_areas, get_active_sweep_run,
    update_sweep_total_calls,
    upsert_blob, get_latest_observation, insert_observation_if_changed,
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
        # Now that enumeration is complete, fill in total_calls for sweep rows
        # pre-created by the REST handler.
        update_sweep_total_calls(conn, run_id, len(all_jobs))
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


async def run_anti_drift_sweep(
    client: MerakiClient,
    conn,
    *,
    org_id: str,
    progress_callback: Optional[Callable[[dict], Awaitable[None]]] = None,
    resume_run_id: Optional[int] = None,
) -> int:
    """Run a full sweep and annotate each observation with confirm or discrepancy.

    Unlike baseline, anti-drift *always* writes a row per (entity, area): the
    source_event distinguishes confirms (hash matched) from discrepancies
    (hash changed without a corresponding change-log event).
    """
    if resume_run_id is None:
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

    if resume_run_id is not None:
        run_id = resume_run_id
        update_sweep_total_calls(conn, run_id, len(jobs))
    else:
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
