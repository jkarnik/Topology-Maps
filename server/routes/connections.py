"""Connection editing routes.

Bridges the UI to the simulator by forwarding connection edits,
triggering re-polls, and broadcasting changes via WebSocket.
"""

import logging
import os

import httpx
from fastapi import APIRouter, HTTPException, Request

from server.models import ConnectionEdit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections", tags=["connections"])

SIMULATOR_HOST = os.environ.get("SIMULATOR_HOST", "localhost")
SIMULATOR_REST_PORT = int(os.environ.get("SIMULATOR_REST_PORT", "8001"))
SIMULATOR_BASE_URL = f"http://{SIMULATOR_HOST}:{SIMULATOR_REST_PORT}"


@router.post("")
async def create_or_move_connection(edit: ConnectionEdit, request: Request):
    """Create or move a connection.

    Flow:
      1. Forward to the simulator REST API
      2. Trigger an immediate collector re-poll
      3. Broadcast the connection change via WebSocket
      4. Return the result
    """
    poller = request.state.poller
    ws_manager = request.state.ws_manager

    # Build the payload using aliased field names for the simulator
    payload = edit.model_dump(by_alias=True, exclude_none=True)

    # 1. Forward to simulator
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{SIMULATOR_BASE_URL}/simulator/connections",
                json=payload,
            )
            resp.raise_for_status()
            sim_result = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Cannot reach simulator -- is it running?",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Simulator rejected edit: {exc.response.text}",
        )

    # 2. Trigger immediate re-poll so the topology reflects the change
    try:
        await poller.poll_once()
    except Exception:
        logger.exception("Re-poll after connection edit failed")

    # 3. Broadcast the change to all WebSocket clients
    await ws_manager.broadcast("connection_change", {
        "action": edit.action.value,
        "device": edit.device,
        "simulator_result": sim_result,
    })

    return {
        "status": "applied",
        "action": edit.action.value,
        "device": edit.device,
        "simulator_result": sim_result,
    }


@router.delete("/{edge_id}")
async def delete_connection(edge_id: str, request: Request):
    """Remove a connection by edge ID.

    Forwards a DELETE to the simulator, re-polls, and broadcasts.
    """
    poller = request.state.poller
    ws_manager = request.state.ws_manager

    # 1. Forward to simulator
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{SIMULATOR_BASE_URL}/simulator/connections/{edge_id}",
            )
            resp.raise_for_status()
            sim_result = resp.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Cannot reach simulator -- is it running?",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=exc.response.status_code,
            detail=f"Simulator rejected delete: {exc.response.text}",
        )

    # 2. Re-poll
    try:
        await poller.poll_once()
    except Exception:
        logger.exception("Re-poll after connection delete failed")

    # 3. Broadcast
    await ws_manager.broadcast("connection_change", {
        "action": "delete",
        "edge_id": edge_id,
        "simulator_result": sim_result,
    })

    return {
        "status": "deleted",
        "edge_id": edge_id,
        "simulator_result": sim_result,
    }
