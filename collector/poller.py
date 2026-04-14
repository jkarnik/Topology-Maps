"""Continuous topology polling loop.

Periodically runs a full discovery + build cycle and notifies
registered callbacks whenever the topology changes.  Designed to run
as a background ``asyncio`` task inside the FastAPI server.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from collector.discovery import TopologyDiscovery
from collector.topology_builder import TopologyBuilder
from server.models import L2Topology, L3Topology

logger = logging.getLogger(__name__)


class TopologyPoller:
    """Runs periodic SNMP discovery and builds topology snapshots.

    Parameters
    ----------
    discovery : TopologyDiscovery
        Discovery engine to poll network devices.
    builder : TopologyBuilder
        Builder that transforms discovery data into topology models.
    interval : int
        Seconds between polling cycles (default ``5``).
    """

    def __init__(
        self,
        discovery: TopologyDiscovery,
        builder: TopologyBuilder,
        interval: int = 5,
    ):
        self.discovery = discovery
        self.builder = builder
        self.interval = interval
        self.l2_topology: Optional[L2Topology] = None
        self.l3_topology: Optional[L3Topology] = None
        self._running = False
        self._version = 0
        self._on_change_callbacks: list[Callable] = []
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Callback registration
    # ------------------------------------------------------------------

    def on_change(self, callback: Callable) -> None:
        """Register a callback invoked with ``(l2, l3)`` on topology change.

        The callback may be a regular function or an ``async`` coroutine
        function; both are supported.
        """
        self._on_change_callbacks.append(callback)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the polling loop as a background task."""
        if self._running:
            logger.warning("Poller is already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Topology poller started (interval=%ds)", self.interval)

    async def stop(self) -> None:
        """Stop the polling loop gracefully."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Topology poller stopped")

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def poll_once(self) -> None:
        """Run a single discovery + build cycle.

        If the resulting topology differs from the previous snapshot,
        the version counter is incremented and all registered callbacks
        are invoked.
        """
        try:
            discovery_data = await self.discovery.discover_from_seed()
        except Exception:
            logger.exception("Discovery failed")
            return

        try:
            new_l2 = self.builder.build_l2(discovery_data)
            new_l3 = self.builder.build_l3(discovery_data)
        except Exception:
            logger.exception("Topology build failed")
            return

        # Detect changes by comparing JSON serialisation
        changed = False
        if self.l2_topology is None or self.l3_topology is None:
            changed = True
        else:
            old_l2_json = self.l2_topology.model_dump_json()
            old_l3_json = self.l3_topology.model_dump_json()
            new_l2_json = new_l2.model_dump_json()
            new_l3_json = new_l3.model_dump_json()
            if old_l2_json != new_l2_json or old_l3_json != new_l3_json:
                changed = True

        self.l2_topology = new_l2
        self.l3_topology = new_l3

        if changed:
            self._version += 1
            logger.info(
                "Topology updated to version %d  (L2: %d nodes, %d edges / L3: %d subnets, %d routes)",
                self._version,
                len(new_l2.nodes),
                len(new_l2.edges),
                len(new_l3.subnets),
                len(new_l3.routes),
            )
            await self._notify_callbacks()
        else:
            logger.debug("Topology unchanged at version %d", self._version)

    async def _notify_callbacks(self) -> None:
        """Invoke all registered on-change callbacks."""
        for cb in self._on_change_callbacks:
            try:
                result = cb(self.l2_topology, self.l3_topology)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("Error in topology change callback")

    async def _poll_loop(self) -> None:
        """Continuous polling loop that runs until stopped."""
        while self._running:
            await self.poll_once()
            try:
                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def version(self) -> int:
        """Current topology version (incremented on each change)."""
        return self._version

    @property
    def is_running(self) -> bool:
        """Return True if the poller is actively running."""
        return self._running and self._task is not None and not self._task.done()
