"""REST API for Meraki config collection (Plan 1.17)."""
from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from server.database import get_connection
from server.config_collector.scanner import run_baseline, run_anti_drift_sweep
from server.config_collector.manual_refresh import refresh_entity
from server.config_collector.store import (
    get_latest_observation, get_observation_history,
    get_blob_by_hash, get_change_events,
)
from server.meraki_client import MerakiClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])


def _row_for_org(conn, org_id: str, name: Optional[str]) -> dict:
    obs_count = conn.execute(
        "SELECT COUNT(*) AS n FROM config_observations WHERE org_id=?", (org_id,)
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


@router.post("/orgs/{org_id}/baseline")
async def start_baseline(org_id: str) -> dict:
    conn = get_connection()
    client = _get_meraki_client()
    cb = await _broadcast_callback_for_org(org_id)
    try:
        run_id = await run_baseline(client, conn, org_id=org_id, progress_callback=cb)
    finally:
        conn.close()
    return {"sweep_run_id": run_id}


@router.post("/orgs/{org_id}/sweep")
async def start_sweep(org_id: str) -> dict:
    conn = get_connection()
    client = _get_meraki_client()
    cb = await _broadcast_callback_for_org(org_id)
    try:
        run_id = await run_anti_drift_sweep(client, conn, org_id=org_id, progress_callback=cb)
    finally:
        conn.close()
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
    """Hierarchical tree of entities with observations."""
    conn = get_connection()
    try:
        org_areas = [r["config_area"] for r in conn.execute(
            "SELECT DISTINCT config_area FROM config_observations WHERE org_id=? AND entity_type='org'",
            (org_id,),
        ).fetchall()]

        net_rows = conn.execute(
            "SELECT DISTINCT entity_id, name_hint FROM config_observations WHERE org_id=? AND entity_type='network'",
            (org_id,),
        ).fetchall()
        networks = []
        for nr in net_rows:
            nid = nr["entity_id"]
            net_areas = [r["config_area"] for r in conn.execute(
                "SELECT DISTINCT config_area FROM config_observations WHERE org_id=? AND entity_type='network' AND entity_id=?",
                (org_id, nid),
            ).fetchall()]
            dev_rows = conn.execute(
                "SELECT DISTINCT entity_id, name_hint FROM config_observations WHERE org_id=? AND entity_type='device'",
                (org_id,),
            ).fetchall()
            networks.append({
                "id": nid, "name": nr["name_hint"], "config_areas": net_areas,
                "devices": [{"serial": d["entity_id"], "name": d["name_hint"]} for d in dev_rows],
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
