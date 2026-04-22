# Plan 1.18 — WebSocket Channel

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Add `/ws/config?org_id=...` WebSocket channel. Broadcasts sweep/observation/change events to connected clients for the subscribed org. Plugs into the `progress_callback` hooks exposed by the baseline runner (Plan 1.13), anti-drift sweep (Plan 1.15), and change-log poller (Plan 1.14).

**Depends on:** Plans 1.13, 1.14, 1.15, 1.17.
**Unblocks:** Plan 1.19 (UI hook `useConfigCollection` subscribes).

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `server/websocket.py` | Modify | Extend with a `ConfigWebSocketHub` or reuse existing hub with a new channel |
| `server/routes/config.py` | Modify | Add WS endpoint `@router.websocket("/ws/config")` or at main app scope |
| `server/main.py` | Modify | Start long-lived `run_poller` per connected org at startup |
| `server/tests/test_config_ws.py` | Create | WebSocket broadcast tests via FastAPI TestClient |

---

## Task 1: `ConfigWebSocketHub` with per-org subscription

- [ ] **Step 1.1: Write failing test**

Create `server/tests/test_config_ws.py`:

```python
"""Tests for config WebSocket channel (Plan 1.18)."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def app():
    from server.routes import config as config_routes
    app = FastAPI()
    app.include_router(config_routes.router)
    return app


def test_ws_config_connects_and_receives_broadcast(app):
    from server.routes.config import _config_ws_hub

    client = TestClient(app)
    with client.websocket_connect("/ws/config?org_id=o1") as ws:
        # Broadcast an event — should be delivered
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            _config_ws_hub.broadcast("o1", {"type": "test", "hello": "world"})
        )
        msg = ws.receive_json()
        assert msg == {"type": "test", "hello": "world"}


def test_ws_config_other_org_is_not_delivered(app):
    from server.routes.config import _config_ws_hub

    client = TestClient(app)
    with client.websocket_connect("/ws/config?org_id=o1") as ws:
        import asyncio
        asyncio.get_event_loop().run_until_complete(
            _config_ws_hub.broadcast("o2", {"type": "other"})
        )
        # No message expected for o1; drain with timeout
        import time
        time.sleep(0.1)
        # Use a second broadcast to o1 to verify the connection still works
        asyncio.get_event_loop().run_until_complete(
            _config_ws_hub.broadcast("o1", {"type": "mine"})
        )
        msg = ws.receive_json()
        assert msg == {"type": "mine"}  # first was filtered out
```

- [ ] **Step 1.2: Run — should fail**

- [ ] **Step 1.3: Implement the hub + WS endpoint**

Append to `server/routes/config.py`:

```python
from fastapi import WebSocket, WebSocketDisconnect


class ConfigWebSocketHub:
    """Per-org WebSocket broadcast hub for config events."""

    def __init__(self):
        # org_id -> set[WebSocket]
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


@router.websocket("/ws/config")
async def config_ws(ws: WebSocket, org_id: str = Query(...)):
    await _config_ws_hub.subscribe(org_id, ws)
    try:
        while True:
            # Keep the connection open; we don't expect client-initiated messages
            await ws.receive_text()
    except WebSocketDisconnect:
        _config_ws_hub.unsubscribe(org_id, ws)
```

Note: the path is `/ws/config` but because it's inside a router with prefix `/api/config`, the actual mount is `/api/config/ws/config`. Adjust the prefix in the WebSocket route decoration to bypass the prefix:

In the websocket handler, we actually want the path to just be `/ws/config`. Since FastAPI's `APIRouter` applies the `prefix` to both HTTP and WS routes, the full path becomes `/api/config/ws/config`. Update the spec reference in Plan 1.19 accordingly — or mount the WS separately at app level in main.py:

```python
# In server/main.py, after include_router
from server.routes.config import config_ws
app.add_api_websocket_route("/ws/config", config_ws)
```

Pick ONE approach (prefix-inclusive OR app-level). The app-level mount is cleaner and matches the spec. Remove the `@router.websocket` decorator and use `app.add_api_websocket_route` instead.

- [ ] **Step 1.4: Update implementation to use app-level WS route**

Change the router decorator to a plain async function (no decorator):

```python
# In server/routes/config.py — replace the @router.websocket block with:
async def config_ws(ws: WebSocket, org_id: str = Query(...)):
    await _config_ws_hub.subscribe(org_id, ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        _config_ws_hub.unsubscribe(org_id, ws)
```

In `server/main.py`:

```python
from server.routes.config import config_ws as _config_ws
app.add_api_websocket_route("/ws/config", _config_ws)
```

Update `server/tests/test_config_ws.py` fixture to register the WS too:

```python
@pytest.fixture
def app():
    from server.routes import config as config_routes
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(config_routes.router)
    app.add_api_websocket_route("/ws/config", config_routes.config_ws)
    return app
```

- [ ] **Step 1.5: Run — should pass**

- [ ] **Step 1.6: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/routes/config.py server/main.py server/tests/test_config_ws.py
git commit -m "feat(ws): ConfigWebSocketHub + /ws/config channel (Plan 1.18)"
```

---

## Task 2: Wire progress callbacks for baseline/sweep/poller broadcasts

- [ ] **Step 2.1: Update the REST endpoints to pass progress callbacks**

In `server/routes/config.py`, update `start_baseline` and `start_sweep`:

```python
async def _broadcast_callback_for_org(org_id: str):
    async def _cb(event: dict) -> None:
        await _config_ws_hub.broadcast(org_id, event)
    return _cb


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
```

- [ ] **Step 2.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/routes/config.py
git commit -m "feat(ws): wire baseline/sweep progress callbacks to broadcast (Plan 1.18)"
```

---

## Task 3: Launch change-log poller on app startup

- [ ] **Step 3.1: Add startup hook**

In `server/main.py`, add a lifespan/startup event:

```python
import asyncio
import os
from contextlib import asynccontextmanager

from server.config_collector.change_log_poller import run_poller
from server.database import get_connection
from server.meraki_client import MerakiClient
from server.routes.config import _config_ws_hub as _config_hub


async def _poller_for_org(org_id: str) -> None:
    client = MerakiClient()
    conn = get_connection()

    async def cb(event: dict) -> None:
        await _config_hub.broadcast(org_id, event)

    interval = int(os.environ.get("CONFIG_CHANGE_LOG_INTERVAL_SECONDS", "1800"))
    timespan = int(os.environ.get("CONFIG_CHANGE_LOG_TIMESPAN_SECONDS", "3600"))
    await run_poller(client, conn, org_id=org_id, interval=interval, timespan=timespan, progress_callback=cb)


@asynccontextmanager
async def lifespan(app):
    poller_tasks: list[asyncio.Task] = []
    if os.environ.get("CONFIG_ENABLE_AUTO_POLLER", "true").lower() == "true" and os.environ.get("MERAKI_API_KEY"):
        # Start poller for each org we know about
        conn = get_connection()
        rows = conn.execute("SELECT DISTINCT org_id FROM config_sweep_runs").fetchall()
        conn.close()
        for r in rows:
            poller_tasks.append(asyncio.create_task(_poller_for_org(r["org_id"])))
    try:
        yield
    finally:
        for t in poller_tasks:
            t.cancel()
```

Then wire `lifespan=lifespan` on the `FastAPI(...)` instantiation if not already using it.

- [ ] **Step 3.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add server/main.py
git commit -m "feat(ws): launch change-log poller per org on startup (Plan 1.18)"
```

---

## Completion Checklist

- [ ] `ConfigWebSocketHub` + `/ws/config` route work
- [ ] baseline/sweep callbacks broadcast to hub
- [ ] App startup launches pollers for known orgs
- [ ] 3 commits

## What This Unblocks

- Plan 1.19: UI hook `useConfigCollection` connects to `/ws/config` and receives live progress.
