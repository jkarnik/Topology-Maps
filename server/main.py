"""FastAPI application entry point.

Central hub that:
  - Serves the REST API for the UI
  - Manages WebSocket connections for live topology updates
  - Runs the collector as a background polling task
  - Bridges connection edits to the simulator
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from server.db import close_db, init_db
from server.websocket import WebSocketManager
from server.routes import topology, devices, system, simulation, meraki, config
from collector.main import create_poller

logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
poller = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of the collector poller."""
    global poller

    # Startup: open the SQLite connection and ensure the schema exists
    init_db()

    # Startup: create and start the collector poller
    poller = create_poller()

    # Register callback to broadcast topology changes via WebSocket
    async def on_topology_change(l2, l3):
        await ws_manager.broadcast("topology_update", {
            "l2": l2.model_dump() if l2 else None,
            "l3": l3.model_dump() if l3 else None,
        })

    poller.on_change(on_topology_change)
    logger.info("Collector poller created (waiting for simulation start)")

    yield

    # Shutdown
    if poller.is_running:
        await poller.stop()
    close_db()
    logger.info("Server shutdown complete")


app = FastAPI(
    title="Network Topology Simulator",
    description="REST API and WebSocket server for the network topology simulator",
    lifespan=lifespan,
)

# CORS -- allow all origins so the dev UI can connect freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include route modules
app.include_router(topology.router)
app.include_router(devices.router)
app.include_router(system.router)
app.include_router(simulation.router)
app.include_router(meraki.router)
app.include_router(config.router)

# Register config WebSocket route
from server.routes.config import config_ws as _config_ws
app.add_api_websocket_route("/ws/config", _config_ws)


# --------------------------------------------------------------------------- #
# WebSocket endpoint
# --------------------------------------------------------------------------- #


@app.websocket("/ws/topology")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for live topology updates.

    Clients connect here to receive real-time topology_update,
    device_status, and connection_change events.
    """
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep the connection alive by reading (client may send pings)
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# --------------------------------------------------------------------------- #
# Middleware to inject shared state into request.state
# --------------------------------------------------------------------------- #


@app.middleware("http")
async def inject_state(request, call_next):
    """Make the poller and WebSocket manager available to route handlers."""
    request.state.poller = poller
    request.state.ws_manager = ws_manager
    return await call_next(request)


# --------------------------------------------------------------------------- #
# Config WebSocket poller startup (Plan 1.18)
# --------------------------------------------------------------------------- #

import asyncio as _asyncio
import os as _os
from contextlib import asynccontextmanager as _asynccontextmanager

from server.config_collector.change_log_poller import run_poller as _run_poller
from server.routes.config import _config_ws_hub as _cfg_ws_hub


async def _poller_for_org(org_id: str) -> None:
    from server.meraki_client import MerakiClient as _MC
    from server.database import get_connection as _get_conn

    client = _MC()
    conn = _get_conn()

    async def cb(event: dict) -> None:
        await _cfg_ws_hub.broadcast(org_id, event)

    interval = int(_os.environ.get("CONFIG_CHANGE_LOG_INTERVAL_SECONDS", "1800"))
    timespan = int(_os.environ.get("CONFIG_CHANGE_LOG_TIMESPAN_SECONDS", "3600"))
    await _run_poller(client, conn, org_id=org_id, interval=interval, timespan=timespan, progress_callback=cb)


@app.on_event("startup")
async def _start_config_pollers():
    if _os.environ.get("CONFIG_ENABLE_AUTO_POLLER", "true").lower() != "true":
        return
    if not _os.environ.get("MERAKI_API_KEY"):
        return
    from server.database import get_connection as _get_conn
    conn = _get_conn()
    rows = conn.execute("SELECT DISTINCT org_id FROM config_sweep_runs").fetchall()
    conn.close()
    for r in rows:
        _asyncio.create_task(_poller_for_org(r["org_id"]))
