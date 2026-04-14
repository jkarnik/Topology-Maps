"""Collector entry point.

Provides a factory for creating a fully-wired :class:`TopologyPoller`,
and a CLI runner for standalone testing (start the simulator first,
then run this module to verify discovery).
"""

from __future__ import annotations

import asyncio
import logging

from collector.snmp_client import SNMPClient
from collector.discovery import TopologyDiscovery
from collector.topology_builder import TopologyBuilder
from collector.poller import TopologyPoller
from simulator.constants import POLL_INTERVAL, SIMULATOR_HOST, SNMP_COMMUNITY

logger = logging.getLogger(__name__)


def create_poller(
    host: str = SIMULATOR_HOST,
    community: str = SNMP_COMMUNITY,
    interval: int = POLL_INTERVAL,
) -> TopologyPoller:
    """Create a fully-wired TopologyPoller ready to start.

    Parameters
    ----------
    host : str
        IP address where the SNMP agents are running (default localhost).
    community : str
        SNMP community string (default from constants).
    interval : int
        Polling interval in seconds (default from constants).

    Returns
    -------
    TopologyPoller
        Poller instance -- call ``await poller.start()`` to begin.
    """
    client = SNMPClient(host=host, community=community)
    discovery = TopologyDiscovery(client)
    builder = TopologyBuilder()
    return TopologyPoller(discovery, builder, interval=interval)


async def _run_once() -> None:
    """Run a single discovery cycle and print a summary.

    Useful for testing: start the simulator, then run
    ``python -m collector.main`` to verify the collector finds all devices.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    poller = create_poller()
    logger.info("Running single discovery cycle...")
    await poller.poll_once()

    if poller.l2_topology is None:
        logger.error("Discovery returned no topology data.")
        return

    l2 = poller.l2_topology
    l3 = poller.l3_topology

    # Summarise L2
    infra = [n for n in l2.nodes if n.type in ("firewall", "core_switch", "floor_switch")]
    aps = [n for n in l2.nodes if n.type == "access_point"]
    endpoints = [n for n in l2.nodes if n.type == "endpoint"]
    lldp_edges = [e for e in l2.edges if e.protocol == "LLDP"]
    arp_edges = [e for e in l2.edges if e.protocol == "ARP"]
    wireless_edges = [e for e in l2.edges if e.protocol == "wireless"]

    print("\n=== L2 Topology Summary ===")
    print(f"  Infrastructure devices: {len(infra)}")
    print(f"  Access Points:          {len(aps)}")
    print(f"  Endpoints:              {len(endpoints)}")
    print(f"  LLDP edges:             {len(lldp_edges)}")
    print(f"  ARP edges:              {len(arp_edges)}")
    print(f"  Wireless edges:         {len(wireless_edges)}")

    if l3:
        print("\n=== L3 Topology Summary ===")
        for subnet in l3.subnets:
            print(f"  VLAN {subnet.vlan:3d} ({subnet.name:20s}): {subnet.cidr:20s} -- {subnet.device_count} devices")
        print(f"  Routes: {len(l3.routes)}")

    print()


if __name__ == "__main__":
    asyncio.run(_run_once())
