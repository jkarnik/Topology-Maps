"""REST API for Meraki config collection (Plan 1.17)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from server.database import get_connection

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
