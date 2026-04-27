"""REST API for Meraki config collection (Plan 1.17)."""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import json
import logging
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from server.database import get_connection
from server.config_collector.scanner import run_baseline, run_anti_drift_sweep
from server.config_collector.manual_refresh import refresh_entity
from server.config_collector.store import (
    get_latest_observation, get_observation_history,
    get_blob_by_hash, get_change_events,
    create_sweep_run, get_active_sweep_run,
    get_observations_in_window,
    create_template, list_templates, get_template_areas,
    delete_template, get_coverage,
)
from server.config_collector.diff_engine import compute_diff
from server.meraki_client import MerakiClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


def _row_for_org(conn, org_id: str, name: Optional[str]) -> dict:
    obs_count = conn.execute(
        """SELECT COUNT(*) AS n FROM (
               SELECT DISTINCT entity_type, entity_id, config_area, sub_key
               FROM config_observations WHERE org_id=?
           )""", (org_id,)
    ).fetchone()["n"]
    last_baseline = conn.execute(
        """SELECT id, status, completed_at FROM config_sweep_runs
           WHERE org_id=? AND kind='baseline'
           ORDER BY id DESC LIMIT 1""",
        (org_id,),
    ).fetchone()
    active = conn.execute(
        """SELECT id FROM config_sweep_runs
           WHERE org_id=? AND status IN ('queued','running')
           ORDER BY id DESC LIMIT 1""",
        (org_id,),
    ).fetchone()
    return {
        "org_id": org_id,
        "name": name,
        "observation_count": obs_count,
        "baseline_state": last_baseline["status"] if last_baseline else "none",
        "last_baseline_at": last_baseline["completed_at"] if last_baseline else None,
        "active_sweep_run_id": active["id"] if active else None,
    }


@router.get("/orgs")
async def list_orgs() -> list[dict]:
    """List orgs visible to the Meraki API key, plus any with local-only data.

    Returns Meraki-discovered orgs as the primary list so the dropdown is
    populated on a fresh install. baseline_state='none' indicates an org
    that has been discovered but never baselined.
    """
    conn = get_connection()
    try:
        client = _get_meraki_client()
        meraki_orgs: list[dict] = []
        if client.is_configured:
            try:
                meraki_orgs = await client.get_organizations()
            except Exception as exc:
                logger.warning("Could not fetch orgs from Meraki: %s", exc)

        seen: set[str] = set()
        result: list[dict] = []
        for mo in meraki_orgs:
            org_id = str(mo.get("id", ""))
            if not org_id:
                continue
            seen.add(org_id)
            result.append(_row_for_org(conn, org_id, mo.get("name")))

        # Include locally-known orgs that aren't in the Meraki list (e.g.
        # key was rotated or org was removed — still want to see history).
        local_rows = conn.execute(
            "SELECT DISTINCT org_id FROM config_sweep_runs "
            "UNION SELECT DISTINCT org_id FROM config_observations"
        ).fetchall()
        for r in local_rows:
            if r["org_id"] not in seen:
                result.append(_row_for_org(conn, r["org_id"], None))

        return result
    finally:
        conn.close()


_VALID_ENTITY_TYPES = {"org", "network", "device", "ssid"}


def _get_meraki_client() -> MerakiClient:
    return MerakiClient()


async def _broadcast_callback_for_org(org_id: str):
    async def _cb(event: dict) -> None:
        await _config_ws_hub.broadcast(org_id, event)
    return _cb


@router.get("/orgs/{org_id}/status")
async def get_status(org_id: str) -> dict:
    conn = get_connection()
    last = conn.execute(
        "SELECT status, completed_at FROM config_sweep_runs WHERE org_id=? AND kind='baseline' ORDER BY id DESC LIMIT 1",
        (org_id,),
    ).fetchone()
    active = conn.execute(
        "SELECT id, kind, status FROM config_sweep_runs WHERE org_id=? AND status IN ('queued','running') ORDER BY id DESC LIMIT 1",
        (org_id,),
    ).fetchone()
    conn.close()
    return {
        "baseline_state": last["status"] if last else "none",
        "last_sync": last["completed_at"] if last else None,
        "active_sweep": dict(active) if active else None,
    }


async def _run_baseline_bg(org_id: str, run_id: int) -> None:
    """Background task: performs the full baseline after the HTTP response returns."""
    client = _get_meraki_client()
    conn = get_connection()
    cb = await _broadcast_callback_for_org(org_id)
    try:
        await run_baseline(client, conn, org_id=org_id, progress_callback=cb, resume_run_id=run_id)
    except Exception:
        logger.exception("Background baseline failed for org %s (run_id=%s)", org_id, run_id)
    finally:
        conn.close()


@router.post("/orgs/{org_id}/baseline")
async def start_baseline(org_id: str) -> dict:
    """Queue a baseline sweep. Returns immediately with sweep_run_id; work runs in background.

    If a sweep is already running (e.g. interrupted by a server restart), resumes it.
    """
    conn = get_connection()
    try:
        active = get_active_sweep_run(conn, org_id=org_id, kind="baseline")
        run_id = active["id"] if active else create_sweep_run(conn, org_id=org_id, kind="baseline", total_calls=None)
    finally:
        conn.close()

    asyncio.create_task(_run_baseline_bg(org_id, run_id))
    return {"sweep_run_id": run_id}


async def _run_sweep_bg(org_id: str, run_id: int) -> None:
    """Background task: performs the full anti-drift sweep after the HTTP response returns."""
    client = _get_meraki_client()
    conn = get_connection()
    cb = await _broadcast_callback_for_org(org_id)
    try:
        await run_anti_drift_sweep(client, conn, org_id=org_id, progress_callback=cb, resume_run_id=run_id)
    except Exception:
        logger.exception("Background anti-drift sweep failed for org %s (run_id=%s)", org_id, run_id)
    finally:
        conn.close()


@router.post("/orgs/{org_id}/sweep")
async def start_sweep(org_id: str) -> dict:
    """Queue an anti-drift sweep. Returns immediately with sweep_run_id; work runs in background."""
    conn = get_connection()
    try:
        active = get_active_sweep_run(conn, org_id=org_id, kind="anti_drift")
        if active is not None:
            return {"sweep_run_id": active["id"]}
        run_id = create_sweep_run(conn, org_id=org_id, kind="anti_drift", total_calls=None)
    finally:
        conn.close()

    asyncio.create_task(_run_sweep_bg(org_id, run_id))
    return {"sweep_run_id": run_id}


class RefreshRequest(BaseModel):
    entity_type: str
    entity_id: str
    config_area: Optional[str] = None


@router.post("/orgs/{org_id}/refresh")
async def refresh(org_id: str, req: RefreshRequest) -> dict:
    if req.entity_type not in _VALID_ENTITY_TYPES:
        raise HTTPException(400, detail=f"entity_type must be one of {_VALID_ENTITY_TYPES}")
    conn = get_connection()
    client = _get_meraki_client()
    try:
        result = await refresh_entity(
            client, conn,
            org_id=org_id,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            config_area=req.config_area,
        )
    finally:
        conn.close()
    return result


@router.get("/orgs/{org_id}/tree")
async def get_tree(org_id: str) -> dict:
    """Hierarchical tree of entities with observations.

    Dedupes by entity_id and picks the non-null name_hint when multiple
    observations for the same entity carry different hints. Device→network
    association is resolved from the Meraki /organizations/{id}/devices
    endpoint (one extra API call per tree render).
    """
    conn = get_connection()
    try:
        # Org-level config areas seen locally
        org_areas = [r["config_area"] for r in conn.execute(
            """SELECT DISTINCT config_area FROM config_observations
               WHERE org_id=? AND entity_type='org'""",
            (org_id,),
        ).fetchall()]

        # Networks: one row per entity_id, keeping the best name_hint (non-null wins)
        net_rows = conn.execute(
            """SELECT entity_id, MAX(name_hint) AS name_hint
               FROM config_observations
               WHERE org_id=? AND entity_type='network'
               GROUP BY entity_id""",
            (org_id,),
        ).fetchall()

        # Devices: one row per serial, keeping the best name_hint
        device_rows = conn.execute(
            """SELECT entity_id, MAX(name_hint) AS name_hint
               FROM config_observations
               WHERE org_id=? AND entity_type='device'
               GROUP BY entity_id""",
            (org_id,),
        ).fetchall()
        local_devices = {
            r["entity_id"]: {"serial": r["entity_id"], "name": r["name_hint"]}
            for r in device_rows
        }

        # Device → network mapping from Meraki (best-effort; if the API is
        # unreachable, devices will just hang off each network they were
        # observed under, sans the mapping).
        network_for_device: dict[str, str] = {}
        client = _get_meraki_client()
        if client.is_configured and local_devices:
            try:
                meraki_devices = await client.get_org_inventory_devices(org_id)
                for d in meraki_devices:
                    serial = d.get("serial")
                    nid = d.get("networkId")
                    if serial and nid:
                        network_for_device[serial] = nid
                    # Also fill in a better name if we didn't have one
                    if serial in local_devices and not local_devices[serial]["name"]:
                        local_devices[serial]["name"] = d.get("name")
            except Exception as exc:
                logger.warning("Tree: could not fetch device inventory: %s", exc)

        # Per-network payload: own config areas + the devices that belong to it
        networks: list[dict] = []
        for nr in net_rows:
            nid = nr["entity_id"]
            net_areas = [r["config_area"] for r in conn.execute(
                """SELECT DISTINCT config_area FROM config_observations
                   WHERE org_id=? AND entity_type='network' AND entity_id=?""",
                (org_id, nid),
            ).fetchall()]
            devices_in_net = [
                local_devices[s]
                for s, mapped_nid in network_for_device.items()
                if mapped_nid == nid and s in local_devices
            ]
            networks.append({
                "id": nid,
                "name": nr["name_hint"],
                "config_areas": net_areas,
                "devices": devices_in_net,
            })

        return {"org": {"id": org_id, "config_areas": org_areas}, "networks": networks}
    finally:
        conn.close()


@router.get("/entities/{entity_type}/{entity_id}")
async def get_entity(
    entity_type: str, entity_id: str,
    org_id: str = Query(...),
) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT DISTINCT config_area, sub_key FROM config_observations
               WHERE org_id=? AND entity_type=? AND entity_id=?""",
            (org_id, entity_type, entity_id),
        ).fetchall()
        if not rows:
            raise HTTPException(404, detail="Entity not found")
        areas = []
        for r in rows:
            latest = get_latest_observation(
                conn, org_id=org_id, entity_type=entity_type, entity_id=entity_id,
                config_area=r["config_area"], sub_key=r["sub_key"],
            )
            blob = get_blob_by_hash(conn, latest["hash"]) if latest else None
            areas.append({
                **latest,
                "payload": json.loads(blob["payload"]) if blob else None,
            })
        return {"entity_type": entity_type, "entity_id": entity_id, "org_id": org_id, "areas": areas}
    finally:
        conn.close()


@router.get("/entities/{entity_type}/{entity_id}/history")
async def get_history(
    entity_type: str, entity_id: str,
    org_id: str = Query(...),
    config_area: Optional[str] = None,
    limit: int = 100,
    before: Optional[str] = None,
) -> dict:
    conn = get_connection()
    try:
        obs = get_observation_history(
            conn, org_id=org_id, entity_type=entity_type, entity_id=entity_id,
            config_area=config_area, limit=limit, before_observed_at=before,
        )
        return {"observations": obs, "has_more": len(obs) == limit,
                "next_cursor": obs[-1]["observed_at"] if obs and len(obs) == limit else None}
    finally:
        conn.close()


@router.get("/blobs/{hash_hex}")
async def get_blob(hash_hex: str) -> dict:
    conn = get_connection()
    try:
        blob = get_blob_by_hash(conn, hash_hex)
        if not blob:
            raise HTTPException(404, detail="Blob not found")
        return {**blob, "payload": json.loads(blob["payload"])}
    finally:
        conn.close()


@router.get("/change-events")
async def list_change_events(
    org_id: str = Query(...),
    network_id: Optional[str] = None,
    limit: int = 100,
    before: Optional[str] = None,
) -> dict:
    conn = get_connection()
    try:
        events = get_change_events(
            conn, org_id=org_id, network_id=network_id,
            limit=limit, before_ts=before,
        )
        return {
            "events": events,
            "has_more": len(events) == limit,
            "next_cursor": events[-1]["ts"] if events and len(events) == limit else None,
        }
    finally:
        conn.close()


@router.get("/diff/org")
async def get_org_diff(
    org_id: str,
    from_ts: str,
    to_ts: Optional[str] = None,
) -> dict:
    if to_ts is None:
        to_ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = get_connection()
    try:
        pairs = get_observations_in_window(conn, org_id=org_id, from_ts=from_ts, to_ts=to_ts)
        results = []
        for p in pairs:
            from_hash = p["from_hash"]
            to_hash = p["to_hash"]
            blob_a: dict = {}
            blob_b: dict = {}
            if from_hash:
                row_a = get_blob_by_hash(conn, from_hash)
                if row_a:
                    blob_a = json.loads(row_a["payload"])
            if to_hash:
                row_b = get_blob_by_hash(conn, to_hash)
                if row_b:
                    blob_b = json.loads(row_b["payload"])

            diff = compute_diff(blob_a, blob_b)
            results.append({
                "entity_type": p["entity_type"],
                "entity_id": p["entity_id"],
                "config_area": p["config_area"],
                "sub_key": p["sub_key"],
                "name_hint": p.get("name_hint", ""),
                "to_observed_at": p["to_observed_at"],
                "diff": dataclasses.asdict(diff),
            })
    finally:
        conn.close()

    estimated = max(1, int(len(pairs) * 0.2))
    content = {
        "from_ts": from_ts,
        "to_ts": to_ts,
        "total_entities_checked": len(pairs),
        "changed_count": len(results),
        "results": results,
    }
    return JSONResponse(content=content, headers={"X-Estimated-Seconds": str(estimated)})


@router.get("/entities/{entity_type}/{entity_id}/timeline")
async def get_entity_timeline(
    entity_type: str,
    entity_id: str,
    org_id: str = Query(...),
) -> dict:
    conn = get_connection()
    try:
        observations = get_observation_history(
            conn,
            org_id=org_id,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=200,
        )
        entries = []
        # Build timeline: each obs that differs from its predecessor has a diff
        # Process oldest-first to build prev map, then reverse at the end
        prev_hashes: dict[tuple, str] = {}
        for obs in reversed(observations):  # oldest first
            key = (obs["config_area"], obs.get("sub_key") or "")
            prior_hash = prev_hashes.get(key)
            has_diff = prior_hash is not None and prior_hash != obs["hash"]
            entries.append({
                "config_area": obs["config_area"],
                "sub_key": obs.get("sub_key") or "",
                "observed_at": obs["observed_at"],
                "source_event": obs["source_event"],
                "hash": obs["hash"],
                "has_diff": has_diff,
                "prior_hash": prior_hash if has_diff else None,
                "admin_email": None,
                "_eid": obs.get("change_event_id"),
            })
            prev_hashes[key] = obs["hash"]

        # Batch-fetch admin info from linked change events (single IN query)
        event_ids = [o.get("change_event_id") for o in observations if o.get("change_event_id")]
        admin_map: dict[int, str] = {}
        if event_ids:
            placeholders = ",".join("?" * len(event_ids))
            rows = conn.execute(
                f"SELECT id, admin_email FROM config_change_events WHERE id IN ({placeholders})",
                tuple(event_ids),
            ).fetchall()
            admin_map = {r["id"]: r["admin_email"] for r in rows if r["admin_email"]}

        # Enrich entries with admin emails from the batch-fetched map
        for entry in entries:
            eid = entry.pop("_eid", None)
            if eid and eid in admin_map:
                entry["admin_email"] = admin_map[eid]

        # Return newest-first
        entries.reverse()
        return {"entity_type": entity_type, "entity_id": entity_id, "entries": entries}
    finally:
        conn.close()


# ── Phase 6: Templates ────────────────────────────────────────────────────────

class PromoteTemplateRequest(BaseModel):
    org_id: str
    name: str
    network_id: str


@router.get("/templates")
async def list_templates_route(org_id: str) -> list[dict]:
    conn = get_connection()
    try:
        return list_templates(conn, org_id=org_id)
    finally:
        conn.close()


@router.post("/templates")
async def create_template_route(req: PromoteTemplateRequest) -> dict:
    conn = get_connection()
    try:
        name_row = conn.execute(
            """SELECT name_hint FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               AND name_hint IS NOT NULL ORDER BY observed_at DESC LIMIT 1""",
            (req.org_id, req.network_id),
        ).fetchone()
        network_name = name_row["name_hint"] if name_row else None
        return create_template(conn, org_id=req.org_id, name=req.name,
                               network_id=req.network_id, network_name=network_name)
    finally:
        conn.close()


@router.delete("/templates/{template_id}")
async def delete_template_route(template_id: int) -> dict:
    conn = get_connection()
    try:
        delete_template(conn, template_id=template_id)
        return {"deleted": template_id}
    finally:
        conn.close()


# ── Phase 6: Network Comparison ───────────────────────────────────────────────

@router.get("/compare/networks")
async def compare_networks(
    org_id: str,
    network_a: str,
    network_b: str,
) -> dict:
    conn = get_connection()
    try:
        rows_a = conn.execute(
            """SELECT config_area, sub_key, hash, name_hint FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
            (org_id, network_a),
        ).fetchall()
        rows_b = conn.execute(
            """SELECT config_area, sub_key, hash, name_hint FROM config_observations
               WHERE org_id=? AND entity_type='network' AND entity_id=?
               GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
            (org_id, network_b),
        ).fetchall()

        logger.info(
            "compare_networks org=%s a=%s(%d rows) b=%s(%d rows)",
            org_id, network_a, len(rows_a), network_b, len(rows_b),
        )

        name_a = rows_a[0]["name_hint"] if rows_a else network_a
        name_b = rows_b[0]["name_hint"] if rows_b else network_b

        map_a = {(r["config_area"], r["sub_key"]): r for r in rows_a}
        map_b = {(r["config_area"], r["sub_key"]): r for r in rows_b}
        all_keys = set(map_a) | set(map_b)

        logger.info("compare_networks all_keys(%d): %s", len(all_keys), sorted(all_keys, key=lambda k: (k[0], "" if k[1] is None else k[1])))

        areas = []
        total_changes = 0
        differing_areas = 0

        for key in sorted(all_keys, key=lambda k: (k[0], "" if k[1] is None else k[1])):
            config_area, sub_key = key
            in_a = key in map_a
            in_b = key in map_b

            if in_a and not in_b:
                areas.append({"config_area": config_area, "sub_key": sub_key,
                               "status": "only_in_a", "diff": None})
                differing_areas += 1
                continue
            if in_b and not in_a:
                areas.append({"config_area": config_area, "sub_key": sub_key,
                               "status": "only_in_b", "diff": None})
                differing_areas += 1
                continue

            logger.info("compare_networks diffing config_area=%s sub_key=%s", config_area, sub_key)
            blob_row_a = get_blob_by_hash(conn, map_a[key]["hash"])
            blob_row_b = get_blob_by_hash(conn, map_b[key]["hash"])
            logger.info(
                "  blob_a hash=%s found=%s  blob_b hash=%s found=%s",
                map_a[key]["hash"][:12], blob_row_a is not None,
                map_b[key]["hash"][:12], blob_row_b is not None,
            )
            blob_a = json.loads(blob_row_a["payload"]) if blob_row_a else {}
            blob_b = json.loads(blob_row_b["payload"]) if blob_row_b else {}
            logger.info("  blob_a type=%s blob_b type=%s", type(blob_a).__name__, type(blob_b).__name__)
            try:
                diff = compute_diff(blob_a, blob_b)
                logger.info("  diff OK: %d changes", len(diff.changes))
            except Exception as diff_exc:
                logger.exception("  compute_diff FAILED for config_area=%s sub_key=%s: %s", config_area, sub_key, diff_exc)
                logger.info("  blob_a preview: %s", str(blob_a)[:200])
                logger.info("  blob_b preview: %s", str(blob_b)[:200])
                raise
            change_count = len(diff.changes)
            total_changes += change_count
            status = "differs" if change_count > 0 else "identical"
            if change_count > 0:
                differing_areas += 1
            try:
                diff_dict = dataclasses.asdict(diff)
            except Exception as serial_exc:
                logger.exception("  dataclasses.asdict FAILED for config_area=%s sub_key=%s: %s", config_area, sub_key, serial_exc)
                raise
            areas.append({
                "config_area": config_area,
                "sub_key": sub_key,
                "status": status,
                "diff": diff_dict,
            })

        areas.sort(key=lambda a: (0 if a["status"] != "identical" else 1, a["config_area"] or ""))

        return {
            "network_a": {"id": network_a, "name": name_a},
            "network_b": {"id": network_b, "name": name_b},
            "areas": areas,
            "total_areas": len(areas),
            "differing_areas": differing_areas,
            "total_changes": total_changes,
        }
    except Exception as exc:
        logger.exception("compare_networks FAILED org=%s a=%s b=%s: %s", org_id, network_a, network_b, exc)
        raise
    finally:
        conn.close()


# ── Phase 6: Coverage ─────────────────────────────────────────────────────────

@router.get("/coverage")
async def get_coverage_route(org_id: str) -> dict:
    conn = get_connection()
    try:
        return {"areas": get_coverage(conn, org_id=org_id)}
    finally:
        conn.close()


# ── Phase 6: Template Scoring ─────────────────────────────────────────────────

@router.get("/templates/{template_id}/scores")
async def get_template_scores(template_id: int, org_id: str) -> dict:
    conn = get_connection()
    try:
        tmpl_row = conn.execute(
            "SELECT * FROM config_templates WHERE id=?", (template_id,)
        ).fetchone()
        if not tmpl_row:
            raise HTTPException(status_code=404, detail="Template not found")

        template_areas = get_template_areas(conn, template_id=template_id)
        area_count = len(template_areas)

        networks = conn.execute(
            """SELECT DISTINCT entity_id, MAX(name_hint) as name_hint
               FROM config_observations
               WHERE org_id=? AND entity_type='network'
               GROUP BY entity_id""",
            (org_id,),
        ).fetchall()

        scores = []
        for net in networks:
            network_id = net["entity_id"]
            network_name = net["name_hint"] or network_id

            net_obs = conn.execute(
                """SELECT config_area, sub_key, hash FROM config_observations
                   WHERE org_id=? AND entity_type='network' AND entity_id=?
                   GROUP BY config_area, sub_key HAVING MAX(observed_at)""",
                (org_id, network_id),
            ).fetchall()
            net_map = {(r["config_area"], r["sub_key"]): r["hash"] for r in net_obs}

            total_fields = 0
            total_changes = 0
            missing_areas = []
            area_scores = []

            for ta in template_areas:
                key = (ta["config_area"], ta["sub_key"])
                if key not in net_map:
                    missing_areas.append(ta["config_area"])
                    area_scores.append({"config_area": ta["config_area"], "score_pct": 0, "change_count": 0})
                    continue

                tmpl_blob_row = get_blob_by_hash(conn, ta["blob_hash"])
                net_blob_row = get_blob_by_hash(conn, net_map[key])
                tmpl_blob = json.loads(tmpl_blob_row["payload"]) if tmpl_blob_row else {}
                net_blob = json.loads(net_blob_row["payload"]) if net_blob_row else {}

                diff = compute_diff(tmpl_blob, net_blob)
                n_changes = len(diff.changes)
                n_fields = diff.unchanged_count + n_changes
                total_fields += n_fields
                total_changes += n_changes

                area_score = 100 if n_fields == 0 else round((n_fields - n_changes) / n_fields * 100)
                area_scores.append({
                    "config_area": ta["config_area"],
                    "score_pct": area_score,
                    "change_count": n_changes,
                })

            score_pct = 100 if total_fields == 0 else round((total_fields - total_changes) / total_fields * 100)
            scores.append({
                "network_id": network_id,
                "network_name": network_name,
                "score_pct": score_pct,
                "change_count": total_changes,
                "total_fields": total_fields,
                "missing_areas": missing_areas,
                "area_scores": area_scores,
            })

        scores.sort(key=lambda s: s["score_pct"])

        return {
            "template": {
                "id": template_id,
                "name": tmpl_row["name"],
                "area_count": area_count,
            },
            "scores": scores,
        }
    finally:
        conn.close()


class ConfigWebSocketHub:
    """Per-org WebSocket broadcast hub for config events."""

    def __init__(self):
        self._subscribers: dict[str, set[WebSocket]] = {}

    async def subscribe(self, org_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._subscribers.setdefault(org_id, set()).add(ws)

    def unsubscribe(self, org_id: str, ws: WebSocket) -> None:
        self._subscribers.get(org_id, set()).discard(ws)

    async def broadcast(self, org_id: str, event: dict) -> None:
        dead: list[WebSocket] = []
        for ws in list(self._subscribers.get(org_id, ())):
            try:
                await ws.send_json(event)
            except Exception:
                dead.append(ws)
        for d in dead:
            self.unsubscribe(org_id, d)


_config_ws_hub = ConfigWebSocketHub()


async def config_ws(ws: WebSocket, org_id: str = Query(...)):
    await _config_ws_hub.subscribe(org_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _config_ws_hub.unsubscribe(org_id, ws)
