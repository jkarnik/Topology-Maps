"""WebSocket manager for live topology updates."""

import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages multiple WebSocket connections and broadcasts topology events."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info(
            "WebSocket client connected (%d total)", len(self._connections)
        )

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection from the active list."""
        self._connections.remove(websocket)
        logger.info(
            "WebSocket client disconnected (%d remaining)",
            len(self._connections),
        )

    async def broadcast(self, event_type: str, data: dict):
        """Broadcast an event to all connected clients.

        Silently removes clients whose connections have gone stale.
        """
        message = json.dumps({"type": event_type, "data": data})
        disconnected: list[WebSocket] = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._connections.remove(ws)

    @property
    def client_count(self) -> int:
        """Number of currently connected WebSocket clients."""
        return len(self._connections)
