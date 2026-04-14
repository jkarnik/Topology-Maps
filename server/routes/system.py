"""System status and control routes."""

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["system"])

SIMULATOR_HOST = os.environ.get("SIMULATOR_HOST", "localhost")
SIMULATOR_REST_PORT = int(os.environ.get("SIMULATOR_REST_PORT", "8001"))
SIMULATOR_BASE_URL = f"http://{SIMULATOR_HOST}:{SIMULATOR_REST_PORT}"


@router.get("/status")
async def get_status(request: Request):
    """Health/status of the server, collector, and simulator."""
    poller = request.state.poller
    ws_manager = request.state.ws_manager

    # Check simulator reachability
    simulator_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{SIMULATOR_BASE_URL}/health")
            simulator_ok = resp.status_code == 200
    except Exception:
        simulator_ok = False

    return {
        "server": "running",
        "collector": {
            "running": poller.is_running if poller else False,
            "version": poller.version if poller else 0,
            "l2_nodes": len(poller.l2_topology.nodes) if poller and poller.l2_topology else 0,
            "l2_edges": len(poller.l2_topology.edges) if poller and poller.l2_topology else 0,
            "l3_subnets": len(poller.l3_topology.subnets) if poller and poller.l3_topology else 0,
        },
        "simulator": {
            "reachable": simulator_ok,
            "url": SIMULATOR_BASE_URL,
        },
        "websocket_clients": ws_manager.client_count if ws_manager else 0,
    }


@router.post("/collector/poll")
async def trigger_poll(request: Request):
    """Trigger an immediate re-poll of the topology."""
    poller = request.state.poller
    if poller is None:
        raise HTTPException(status_code=503, detail="Collector not initialized")

    await poller.poll_once()

    return {
        "status": "poll_complete",
        "version": poller.version,
        "l2_nodes": len(poller.l2_topology.nodes) if poller.l2_topology else 0,
        "l2_edges": len(poller.l2_topology.edges) if poller.l2_topology else 0,
    }
