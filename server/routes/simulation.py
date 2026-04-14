"""Simulation start/stop routes.

Provides endpoints to start and stop the topology simulation (collector
poller), with an automatic 10-minute shutdown timer.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from fastapi import APIRouter, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/simulation", tags=["simulation"])


class SimulationManager:
    """Manages the lifecycle of the simulation (poller + auto-shutdown).

    Parameters
    ----------
    timeout_seconds : int
        Seconds until the simulation auto-shuts down (default 600 = 10 min).
    """

    def __init__(self, timeout_seconds: int = 600):
        self._timeout_seconds = timeout_seconds
        self._is_running = False
        self._start_time: Optional[float] = None
        self._shutdown_task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_running(self) -> bool:
        """Return True if the simulation is currently active."""
        return self._is_running

    @property
    def remaining_seconds(self) -> float:
        """Seconds until auto-shutdown, or 0 if not running."""
        if not self._is_running or self._start_time is None:
            return 0
        elapsed = time.monotonic() - self._start_time
        remaining = self._timeout_seconds - elapsed
        return max(0.0, remaining)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self, poller, ws_manager) -> None:
        """Start the simulation and the auto-shutdown timer."""
        if self._is_running:
            logger.warning("Simulation is already running")
            return

        self._is_running = True
        self._start_time = time.monotonic()
        await poller.start()
        logger.info(
            "Simulation started (auto-shutdown in %ds)", self._timeout_seconds
        )

        # Cancel any existing shutdown task before creating a new one
        if self._shutdown_task is not None and not self._shutdown_task.done():
            self._shutdown_task.cancel()
        self._shutdown_task = asyncio.create_task(
            self._auto_shutdown(poller, ws_manager)
        )

    async def stop(self, poller, ws_manager) -> None:
        """Stop the simulation and cancel the auto-shutdown timer."""
        if not self._is_running:
            logger.warning("Simulation is not running")
            return

        self._is_running = False
        self._start_time = None

        # Cancel the auto-shutdown task if it's still pending
        if self._shutdown_task is not None and not self._shutdown_task.done():
            self._shutdown_task.cancel()
            try:
                await self._shutdown_task
            except asyncio.CancelledError:
                pass
            self._shutdown_task = None

        await poller.stop()
        logger.info("Simulation stopped")

    # ------------------------------------------------------------------
    # Auto-shutdown
    # ------------------------------------------------------------------

    async def _auto_shutdown(self, poller, ws_manager) -> None:
        """Sleep for the timeout duration then stop the simulation."""
        try:
            await asyncio.sleep(self._timeout_seconds)
        except asyncio.CancelledError:
            return

        logger.info("Simulation auto-shutdown triggered after %ds timeout", self._timeout_seconds)
        self._is_running = False
        self._start_time = None
        await poller.stop()
        await ws_manager.broadcast("simulation_stopped", {"reason": "timeout"})


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

simulation_manager = SimulationManager(timeout_seconds=600)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/start")
async def start_simulation(request: Request):
    """Start the simulation."""
    poller = request.state.poller
    ws_manager = request.state.ws_manager

    if simulation_manager.is_running:
        return {"status": "already_running", "remaining_seconds": simulation_manager.remaining_seconds}

    await simulation_manager.start(poller, ws_manager)
    return {
        "status": "started",
        "remaining_seconds": simulation_manager.remaining_seconds,
    }


@router.post("/stop")
async def stop_simulation(request: Request):
    """Stop the simulation."""
    poller = request.state.poller
    ws_manager = request.state.ws_manager

    if not simulation_manager.is_running:
        return {"status": "not_running"}

    await simulation_manager.stop(poller, ws_manager)
    return {"status": "stopped"}


@router.get("/status")
async def simulation_status():
    """Return the current simulation status."""
    return {
        "is_running": simulation_manager.is_running,
        "remaining_seconds": simulation_manager.remaining_seconds,
    }
