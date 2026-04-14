"""SNMP simulator entry point.

Creates the full SD-Branch topology state, builds MIB trees for all
seven infrastructure devices, starts their SNMP agents on localhost,
and runs until interrupted with Ctrl+C.

Usage::

    python -m simulator.main
"""

from __future__ import annotations

import asyncio
import logging
import signal

from simulator.constants import (
    APS_PER_FLOOR,
    AP_BASE_IP,
    AP_IP_START,
    DEVICE_FLOORS,
    DEVICE_IPS,
    DEVICE_MODELS,
    DEVICE_TYPES,
    SIMULATOR_REST_PORT,
    SNMP_PORTS,
)
from simulator.agent import SNMPAgent
from simulator.api import SimulatorAPI
from simulator.endpoint_generator import (
    populate_access_points,
    populate_wired_endpoints,
    populate_wireless_clients,
)
from simulator.roaming import RoamingSimulator
from simulator.topology_state import TopologyState, DeviceState, LLDPNeighbor
from simulator.devices.fortigate import build_fortigate_mib_tree
from simulator.devices.core_switch import build_core_switch_mib_tree
from simulator.devices.floor_switch import build_floor_switch_mib_tree

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Topology initialization
# ---------------------------------------------------------------------------

def _ap_id(floor: int, ap_index: int) -> str:
    """Return the device ID for an AP, e.g. ``'ap-1-01'``."""
    return f"ap-{floor}-{ap_index + 1:02d}"


def _ap_name(floor: int, ap_index: int) -> str:
    """Return the display name for an AP, e.g. ``'FortiAP-1'``.

    Must match the name used in ``endpoint_generator.populate_access_points``
    so the collector can correlate LLDP sysName with wireless controller data.
    """
    global_idx = (floor - 1) * APS_PER_FLOOR + (ap_index + 1)
    return f"FortiAP-{global_idx}"


def _ap_ip(floor: int, ap_index: int) -> str:
    """Return the IP address for an AP."""
    octet = AP_IP_START + (floor - 1) * APS_PER_FLOOR + ap_index
    return f"{AP_BASE_IP}.{octet}"


def init_topology_state() -> TopologyState:
    """Initialize the topology state with all infrastructure device connections.

    Creates :class:`DeviceState` objects for all seven infrastructure devices
    (two FortiGates, one core switch, four floor switches) and populates
    their LLDP neighbor tables to reflect the physical topology.

    The physical topology is::

        FortiGate Primary (port5) <--> Core Switch (port1)
        FortiGate Standby (port5) <--> Core Switch (port2)
        Core Switch (port3) <--> Floor Switch 1 (port49)
        Core Switch (port4) <--> Floor Switch 2 (port49)
        Core Switch (port5) <--> Floor Switch 3 (port49)
        Core Switch (port6) <--> Floor Switch 4 (port49)

    Each floor switch also has 14 APs connected on ports 1-14.
    """
    state = TopologyState()

    # ------------------------------------------------------------------
    # FortiGate Primary
    # ------------------------------------------------------------------
    fg_primary = DeviceState(
        device_id="fg-primary",
        device_type=DEVICE_TYPES["fg-primary"],
        model=DEVICE_MODELS["fg-primary"],
        ip=DEVICE_IPS["fg-primary"],
        snmp_port=SNMP_PORTS["fg-primary"],
        interfaces=[
            {"name": "WAN1", "index": 1, "status": "up"},
            {"name": "WAN2", "index": 2, "status": "up"},
            {"name": "port5", "index": 3, "status": "up"},
            {"name": "HA-link", "index": 4, "status": "up"},
        ],
        lldp_neighbors=[
            LLDPNeighbor(
                local_port="port5",
                remote_device_id="core-sw",
                remote_port="port1",
                remote_device_name="CORE-SW",
                remote_ip=DEVICE_IPS["core-sw"],
            ),
            LLDPNeighbor(
                local_port="HA-link",
                remote_device_id="fg-standby",
                remote_port="HA-link",
                remote_device_name="FG-STANDBY",
                remote_ip=DEVICE_IPS["fg-standby"],
            ),
        ],
    )
    state.add_device(fg_primary)

    # ------------------------------------------------------------------
    # FortiGate Standby
    # ------------------------------------------------------------------
    fg_standby = DeviceState(
        device_id="fg-standby",
        device_type=DEVICE_TYPES["fg-standby"],
        model=DEVICE_MODELS["fg-standby"],
        ip=DEVICE_IPS["fg-standby"],
        snmp_port=SNMP_PORTS["fg-standby"],
        interfaces=[
            {"name": "WAN1", "index": 1, "status": "up"},
            {"name": "WAN2", "index": 2, "status": "up"},
            {"name": "port5", "index": 3, "status": "up"},
            {"name": "HA-link", "index": 4, "status": "up"},
        ],
        lldp_neighbors=[
            LLDPNeighbor(
                local_port="port5",
                remote_device_id="core-sw",
                remote_port="port2",
                remote_device_name="CORE-SW",
                remote_ip=DEVICE_IPS["core-sw"],
            ),
            LLDPNeighbor(
                local_port="HA-link",
                remote_device_id="fg-primary",
                remote_port="HA-link",
                remote_device_name="FG-PRIMARY",
                remote_ip=DEVICE_IPS["fg-primary"],
            ),
        ],
    )
    state.add_device(fg_standby)

    # ------------------------------------------------------------------
    # Core Switch
    # ------------------------------------------------------------------
    core_sw_neighbors = [
        # Uplinks to FortiGates
        LLDPNeighbor(
            local_port="port1",
            remote_device_id="fg-primary",
            remote_port="port5",
            remote_device_name="FG-PRIMARY",
            remote_ip=DEVICE_IPS["fg-primary"],
        ),
        LLDPNeighbor(
            local_port="port2",
            remote_device_id="fg-standby",
            remote_port="port5",
            remote_device_name="FG-STANDBY",
            remote_ip=DEVICE_IPS["fg-standby"],
        ),
    ]
    # Downlinks to floor switches: port3 -> floor-sw-1, ..., port6 -> floor-sw-4
    for floor_num in range(1, 5):
        floor_sw_id = f"floor-sw-{floor_num}"
        core_port = f"port{2 + floor_num}"  # port3, port4, port5, port6
        core_sw_neighbors.append(
            LLDPNeighbor(
                local_port=core_port,
                remote_device_id=floor_sw_id,
                remote_port="port49",
                remote_device_name=f"FLOOR-SW-{floor_num}",
                remote_ip=DEVICE_IPS[floor_sw_id],
            )
        )

    core_sw_interfaces = [
        {"name": "port1", "index": 1, "status": "up"},
        {"name": "port2", "index": 2, "status": "up"},
        {"name": "port3", "index": 3, "status": "up"},
        {"name": "port4", "index": 4, "status": "up"},
        {"name": "port5", "index": 5, "status": "up"},
        {"name": "port6", "index": 6, "status": "up"},
    ]
    # Ports 7-24 are unused / admin-down
    for i in range(7, 25):
        core_sw_interfaces.append({"name": f"port{i}", "index": i, "status": "down"})

    core_sw = DeviceState(
        device_id="core-sw",
        device_type=DEVICE_TYPES["core-sw"],
        model=DEVICE_MODELS["core-sw"],
        ip=DEVICE_IPS["core-sw"],
        snmp_port=SNMP_PORTS["core-sw"],
        interfaces=core_sw_interfaces,
        lldp_neighbors=core_sw_neighbors,
    )
    state.add_device(core_sw)

    # ------------------------------------------------------------------
    # Floor Switches (4)
    # ------------------------------------------------------------------
    for floor_num in range(1, 5):
        floor_sw_id = f"floor-sw-{floor_num}"
        core_remote_port = f"port{2 + floor_num}"  # port3..port6

        floor_neighbors: list[LLDPNeighbor] = [
            # Uplink to Core Switch on port49
            LLDPNeighbor(
                local_port="port49",
                remote_device_id="core-sw",
                remote_port=core_remote_port,
                remote_device_name="CORE-SW",
                remote_ip=DEVICE_IPS["core-sw"],
            ),
        ]

        # APs on ports 1-14
        for ap_idx in range(APS_PER_FLOOR):
            port_idx = ap_idx + 1
            aid = _ap_id(floor_num, ap_idx)
            floor_neighbors.append(
                LLDPNeighbor(
                    local_port=f"port{port_idx}",
                    remote_device_id=aid,
                    remote_port="eth0",
                    remote_device_name=_ap_name(floor_num, ap_idx),
                    remote_ip=_ap_ip(floor_num, ap_idx),
                )
            )

        # Build interface list: ports 1-48 (access), port49 (uplink), port50 (spare)
        floor_interfaces: list[dict] = []
        for idx in range(1, 49):
            floor_interfaces.append({"name": f"port{idx}", "index": idx, "status": "up"})
        floor_interfaces.append({"name": "port49", "index": 49, "status": "up"})
        floor_interfaces.append({"name": "port50", "index": 50, "status": "down"})

        floor_sw = DeviceState(
            device_id=floor_sw_id,
            device_type=DEVICE_TYPES[floor_sw_id],
            model=DEVICE_MODELS[floor_sw_id],
            ip=DEVICE_IPS[floor_sw_id],
            snmp_port=SNMP_PORTS[floor_sw_id],
            floor=DEVICE_FLOORS[floor_sw_id],
            interfaces=floor_interfaces,
            lldp_neighbors=floor_neighbors,
        )
        state.add_device(floor_sw)

    # ------------------------------------------------------------------
    # Populate endpoints, APs, and wireless clients
    # ------------------------------------------------------------------
    populate_wired_endpoints(state)
    populate_access_points(state)
    populate_wireless_clients(state)

    logger.info(
        "Topology populated: %d APs, %d wireless clients, wired endpoints in %d floor switches",
        len(state.get_all_aps()),
        len(state.get_all_wireless_clients()),
        sum(1 for did in state.devices if did.startswith("floor-sw-")),
    )

    return state


# ---------------------------------------------------------------------------
# MIB tree construction
# ---------------------------------------------------------------------------

def build_mib_trees(state: TopologyState) -> dict[str, list[tuple]]:
    """Build MIB trees for all devices.

    Returns a mapping of ``device_id -> sorted MIB tree``.
    """
    trees: dict[str, list[tuple]] = {}
    for device_id in SNMP_PORTS:
        if device_id.startswith("fg-"):
            trees[device_id] = build_fortigate_mib_tree(device_id, state)
        elif device_id == "core-sw":
            trees[device_id] = build_core_switch_mib_tree(device_id, state)
        elif device_id.startswith("floor-sw-"):
            floor = DEVICE_FLOORS[device_id]
            trees[device_id] = build_floor_switch_mib_tree(device_id, floor, state)
    return trees


# ---------------------------------------------------------------------------
# Async runner
# ---------------------------------------------------------------------------

async def run_simulator() -> None:
    """Start all SNMP agents and run until cancelled."""
    state = init_topology_state()
    trees = build_mib_trees(state)

    agents: list[SNMPAgent] = []
    for device_id, port in SNMP_PORTS.items():
        agent = SNMPAgent(device_id, port, trees[device_id])
        agents.append(agent)

    # Start all agents
    for agent in agents:
        await agent.start()

    logger.info("All %d SNMP agents started", len(agents))

    # Start roaming simulator
    roaming = RoamingSimulator(state)
    await roaming.start()

    # Start internal REST API
    api = SimulatorAPI(topology_state=state, agent_count=len(agents))
    await api.start(SIMULATOR_REST_PORT)

    # Wait for shutdown signal (Ctrl+C / SIGTERM)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    await stop_event.wait()

    # Graceful shutdown
    await api.stop()
    await roaming.stop()
    logger.info("Stopping all SNMP agents...")
    for agent in agents:
        await agent.stop()
    logger.info("All agents stopped")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        pass  # Graceful exit on Ctrl+C in terminals that raise before the handler fires
