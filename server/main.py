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

from server.websocket import WebSocketManager
from server.routes import topology, devices, connections, system
from collector.main import create_poller

logger = logging.getLogger(__name__)

ws_manager = WebSocketManager()
poller = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup and shutdown of the collector poller."""
    global poller

    # Startup: create and start the collector poller
    poller = create_poller()

    # Register callback to broadcast topology changes via WebSocket
    async def on_topology_change(l2, l3):
        await ws_manager.broadcast("topology_update", {
            "l2": l2.model_dump() if l2 else None,
            "l3": l3.model_dump() if l3 else None,
        })

    poller.on_change(on_topology_change)
    await poller.start()
    logger.info("Collector poller started")

    yield

    # Shutdown
    await poller.stop()
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
app.include_router(connections.router)
app.include_router(system.router)


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
