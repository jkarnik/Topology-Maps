"""Tests for config WebSocket channel (Plan 1.18)."""
from __future__ import annotations

import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from server.routes import config as config_routes
    app = FastAPI()
    app.include_router(config_routes.router)
    app.add_api_websocket_route("/ws/config", config_routes.config_ws)
    return app


def test_ws_config_connects_and_receives_broadcast(app):
    from server.routes.config import _config_ws_hub

    client = TestClient(app)
    with client.websocket_connect("/ws/config?org_id=o1") as ws:
        asyncio.get_event_loop().run_until_complete(
            _config_ws_hub.broadcast("o1", {"type": "test", "hello": "world"})
        )
        msg = ws.receive_json()
        assert msg == {"type": "test", "hello": "world"}


def test_ws_config_other_org_is_not_delivered(app):
    from server.routes.config import _config_ws_hub

    client = TestClient(app)
    with client.websocket_connect("/ws/config?org_id=o1") as ws:
        asyncio.get_event_loop().run_until_complete(
            _config_ws_hub.broadcast("o2", {"type": "other"})
        )
        import time
        time.sleep(0.1)
        asyncio.get_event_loop().run_until_complete(
            _config_ws_hub.broadcast("o1", {"type": "mine"})
        )
        msg = ws.receive_json()
        assert msg == {"type": "mine"}
