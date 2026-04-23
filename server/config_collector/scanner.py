"""Baseline scanner — enumerate and fetch all Tier-1+2 configs for an org."""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from server.config_collector.endpoints_catalog import expand_for_org
from server.config_collector.store import (
    create_sweep_run, mark_sweep_running, mark_sweep_complete,
    mark_sweep_failed, increment_sweep_counters,
    list_completed_entity_areas, get_active_sweep_run,
)
from server.config_collector.targeted_puller import pull_many, coalesce_jobs
from server.meraki_client import MerakiClient

logger = logging.getLogger(__name__)


async def enumerate_org_composition(
    client: MerakiClient,
    org_id: str,
) -> dict:
    """Gather {networks, devices_by_network, enabled_ssids_by_network} for expand_for_org."""
    networks = await client._get(f"/organizations/{org_id}/networks")

    all_devices = await client._get(f"/organizations/{org_id}/devices")
    devices_by_network: dict[str, list[dict]] = {n["id"]: [] for n in networks}
    for d in all_devices:
        nid = d.get("networkId")
        if nid in devices_by_network:
            devices_by_network[nid].append(d)

    enabled_ssids_by_network: dict[str, list[int]] = {}
    for n in networks:
        if "wireless" in (n.get("productTypes") or []):
            ssids = await client._get(f"/networks/{n['id']}/wireless/ssids")
            enabled_ssids_by_network[n["id"]] = [
                s["number"] for s in ssids if s.get("enabled") is True
            ]
        else:
            enabled_ssids_by_network[n["id"]] = []

    return {
        "networks": networks,
        "devices_by_network": devices_by_network,
        "enabled_ssids_by_network": enabled_ssids_by_network,
    }
