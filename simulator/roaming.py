"""Wireless client roaming simulator.

A background async task that periodically moves wireless clients between
APs to simulate real-world roaming behavior. Employee handhelds roam
across floors more often than guest devices, and signal strength (RSSI)
drops immediately after a roam event.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

from simulator.constants import (
    ROAMING_INTERVAL_MIN,
    ROAMING_INTERVAL_MAX,
    ROAMING_BATCH_MIN,
    ROAMING_BATCH_MAX,
    ROAMING_SAME_FLOOR,
    ROAMING_CROSS_FLOOR,
    APS_PER_FLOOR,
    TOTAL_FLOORS,
)
from simulator.topology_state import TopologyState

logger = logging.getLogger(__name__)


class RoamingSimulator:
    """Simulates wireless client roaming between APs."""

    def __init__(self, topology_state: TopologyState):
        self._state = topology_state
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start the roaming background task."""
        self._running = True
        self._task = asyncio.create_task(self._roaming_loop())
        logger.info("Roaming simulator started")

    async def stop(self):
        """Stop the roaming background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Roaming simulator stopped")

    async def _roaming_loop(self):
        """Main roaming loop."""
        while self._running:
            interval = random.uniform(ROAMING_INTERVAL_MIN, ROAMING_INTERVAL_MAX)
            await asyncio.sleep(interval)
            self._roam_batch()

    def _roam_batch(self):
        """Select and roam a batch of wireless clients."""
        clients = self._state.get_all_wireless_clients()
        if not clients:
            return

        upper = min(ROAMING_BATCH_MAX, len(clients))
        lower = min(ROAMING_BATCH_MIN, upper)
        batch_size = random.randint(lower, upper)
        selected = random.sample(clients, batch_size)

        for client in selected:
            self._roam_client(client)

    def _roam_client(self, client):
        """Roam a single client to a new AP."""
        # Determine current AP's floor
        current_ap = self._state.get_ap(client.ap_id)
        if not current_ap:
            return

        current_floor = current_ap.floor

        # Decide same-floor vs cross-floor based on device type
        same_floor_prob = ROAMING_SAME_FLOOR.get(client.device_type, 0.85)

        if random.random() < same_floor_prob:
            # Same-floor roam
            target_floor = current_floor
        else:
            # Cross-floor roam (adjacent only)
            adjacent = []
            if current_floor > 1:
                adjacent.append(current_floor - 1)
            if current_floor < TOTAL_FLOORS:
                adjacent.append(current_floor + 1)
            target_floor = random.choice(adjacent) if adjacent else current_floor

        # Pick a different AP on the target floor
        floor_aps = self._state.get_aps_on_floor(target_floor)
        candidates = [ap for ap in floor_aps if ap.ap_id != client.ap_id]
        if not candidates:
            return

        new_ap = random.choice(candidates)

        # Post-roam RSSI (weaker right after roam)
        new_rssi = random.randint(-80, -70)

        # Perform the roam (capture old AP ID before mutation)
        old_ap_id = client.ap_id
        self._state.move_wireless_client(client.mac, new_ap.ap_id, new_rssi)
        logger.debug(
            "Roamed %s (%s) from %s to %s (floor %d->%d)",
            client.mac,
            client.device_type,
            old_ap_id,
            new_ap.ap_id,
            current_floor,
            target_floor,
        )
