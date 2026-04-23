"""REST API for Meraki config collection (Plan 1.17)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Query

from server.database import get_connection
from server.config_collector.scanner import run_baseline, run_anti_drift_sweep
from server.config_collector.manual_refresh import refresh_entity
from server.meraki_client import MerakiClient

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/orgs")
async def list_orgs() -> list[dict]:
    """List orgs with collection status. Empty until a baseline is started."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT org_id FROM config_sweep_runs
           UNION SELECT DISTINCT org_id FROM config_observations"""
    ).fetchall()
    result = []
    for r in rows:
        org_id = r["org_id"]
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
        result.append({
            "org_id": org_id,
            "observation_count": obs_count,
            "baseline_state": last_baseline["status"] if last_baseline else "none",
            "last_baseline_at": last_baseline["completed_at"] if last_baseline else None,
            "active_sweep_run_id": active["id"] if active else None,
        })
    conn.close()
    return result


_VALID_ENTITY_TYPES = {"org", "network", "device", "ssid"}


def _get_meraki_client() -> MerakiClient:
    return MerakiClient()


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
    try:
        run_id = await run_baseline(client, conn, org_id=org_id)
    finally:
        conn.close()
    return {"sweep_run_id": run_id}


@router.post("/orgs/{org_id}/sweep")
async def start_sweep(org_id: str) -> dict:
    conn = get_connection()
    client = _get_meraki_client()
    try:
        run_id = await run_anti_drift_sweep(client, conn, org_id=org_id)
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
