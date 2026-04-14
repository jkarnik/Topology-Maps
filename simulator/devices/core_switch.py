"""MIB tree builder for the FortiSwitch 1024E core switch.

Generates a complete SNMP MIB tree covering SNMPv2-MIB (system), IF-MIB
(interfaces), LLDP-MIB (neighbors), Q-BRIDGE-MIB (VLANs), and BRIDGE-MIB
(MAC forwarding) for the single core switch in the SD-Branch topology.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simulator.constants import VLANS
from simulator.devices.base import (
    FDB_STATUS_LEARNED,
    IF_TYPE_ETHERNET_CSMACD,
    build_interface_entries,
    build_lldp_entries,
    build_mac_fwd_entries,
    build_system_mib,
    build_vlan_entries,
    generate_mac,
    sort_mib_tree,
)

if TYPE_CHECKING:
    from simulator.topology_state import TopologyState

# ---- Device constants -------------------------------------------------------

_SYS_DESCR = "Fortinet FortiSwitch 1024E v7.4.3"
_SYS_NAME = "CORE-SW"
_SYS_OBJECT_ID = "1.3.6.1.4.1.12356.106.1.1024"

_TOTAL_PORTS = 24

# Ports 1-2 are 10G SFP+ uplinks; ports 3-6 are 1G downlinks; 7-24 unused.
# ifSpeed is Gauge32 (max 4294967295).  For 10G links the standard practice
# (RFC 2863) is to report 4294967295 in ifSpeed and put the real value in
# ifHighSpeed.  base.py doesn't emit ifHighSpeed, so we use the max marker.
_GAUGE32_MAX = 4_294_967_295

_PORT_DEFINITIONS: list[dict] = [
    # Uplinks to FortiGates (10G SFP+)
    {"index": 1, "name": "port1", "speed": _GAUGE32_MAX, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up"},
    {"index": 2, "name": "port2", "speed": _GAUGE32_MAX, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up"},
    # Downlinks to floor switches
    {"index": 3, "name": "port3", "speed": 1_000_000_000, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up"},
    {"index": 4, "name": "port4", "speed": 1_000_000_000, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up"},
    {"index": 5, "name": "port5", "speed": 1_000_000_000, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up"},
    {"index": 6, "name": "port6", "speed": 1_000_000_000, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up"},
]

# Fill in unused ports 7-24 as 1G admin-down.
for _i in range(7, _TOTAL_PORTS + 1):
    _PORT_DEFINITIONS.append({
        "index": _i,
        "name": f"port{_i}",
        "speed": 1_000_000_000,
        "type": IF_TYPE_ETHERNET_CSMACD,
        "status": "down",
    })

# LLDP neighbor definitions (static topology)
_LLDP_NEIGHBORS: list[dict] = [
    {"local_port_idx": 1, "chassis_id": generate_mac("fg-primary", 0), "port_id": "port5", "sys_name": "FG-PRIMARY"},
    {"local_port_idx": 2, "chassis_id": generate_mac("fg-standby", 0), "port_id": "port5", "sys_name": "FG-STANDBY"},
    {"local_port_idx": 3, "chassis_id": generate_mac("floor-sw-1", 0), "port_id": "port49", "sys_name": "FLOOR-SW-1"},
    {"local_port_idx": 4, "chassis_id": generate_mac("floor-sw-2", 0), "port_id": "port49", "sys_name": "FLOOR-SW-2"},
    {"local_port_idx": 5, "chassis_id": generate_mac("floor-sw-3", 0), "port_id": "port49", "sys_name": "FLOOR-SW-3"},
    {"local_port_idx": 6, "chassis_id": generate_mac("floor-sw-4", 0), "port_id": "port49", "sys_name": "FLOOR-SW-4"},
]


# ---- Internal helpers --------------------------------------------------------

def _build_lldp_from_state(topology_state: TopologyState, device_id: str) -> list[dict]:
    """Build LLDP neighbor dicts from live topology state."""
    device = topology_state.get_device(device_id)
    if device is None or not device.lldp_neighbors:
        return _LLDP_NEIGHBORS  # fall back to static definitions

    neighbors: list[dict] = []
    for n in device.lldp_neighbors:
        # Derive the ifIndex from the port name (e.g. "port3" -> 3)
        try:
            local_idx = int(n.local_port.replace("port", ""))
        except ValueError:
            continue
        neighbors.append({
            "local_port_idx": local_idx,
            "chassis_id": generate_mac(n.remote_device_id, 0),
            "port_id": n.remote_port,
            "sys_name": n.remote_device_name.upper(),
        })
    return neighbors


def _build_mac_fwd_from_state(topology_state: TopologyState, device_id: str) -> list[dict]:
    """Build MAC forwarding entries from live topology state, or generate samples."""
    device = topology_state.get_device(device_id)
    if device is not None and device.mac_table:
        entries: list[dict] = []
        for m in device.mac_table:
            try:
                port_num = int(m.port.replace("port", ""))
            except ValueError:
                continue
            entries.append({"mac": m.mac, "port": port_num, "status": FDB_STATUS_LEARNED})
        return entries

    # Fallback: generate sample MAC entries using the static helper.
    return _generate_sample_mac_entries()


def _generate_sample_mac_entries() -> list[dict]:
    """Generate sample MAC forwarding entries for each active port.

    Produces three learned MAC addresses per active port to simulate
    hosts reachable behind each connected device.
    """
    port_device_map = {
        1: "fg-primary",
        2: "fg-standby",
        3: "floor-sw-1",
        4: "floor-sw-2",
        5: "floor-sw-3",
        6: "floor-sw-4",
    }
    entries: list[dict] = []
    for port_idx, remote_device in port_device_map.items():
        for j in range(3):
            mac = generate_mac(f"{remote_device}-host", j)
            entries.append({"mac": mac, "port": port_idx, "status": FDB_STATUS_LEARNED})
    return entries


# ---- Public API --------------------------------------------------------------

def build_core_switch_mib_tree(device_id: str, topology_state: TopologyState) -> list[tuple]:
    """Build the full MIB tree for the core switch.

    Combines system MIB, interface table, LLDP neighbors, VLAN table,
    and MAC forwarding table into a single sorted OID tree that pysnmp
    can serve.

    Args:
        device_id: Device identifier, expected to be ``"core-sw"``.
        topology_state: :class:`TopologyState` instance holding live
            network state. If ``None`` or empty, static defaults are used.

    Returns:
        Sorted list of ``(oid_tuple, pysnmp_value)`` pairs.
    """
    entries: list[tuple] = []

    # 1. SNMPv2-MIB system group
    entries.extend(build_system_mib(
        sys_descr=_SYS_DESCR,
        sys_name=_SYS_NAME,
        sys_object_id=_SYS_OBJECT_ID,
    ))

    # 2. IF-MIB interface table (all 24 ports)
    entries.extend(build_interface_entries(_PORT_DEFINITIONS))

    # 3. LLDP-MIB neighbor table
    if topology_state is not None:
        lldp_data = _build_lldp_from_state(topology_state, device_id)
    else:
        lldp_data = _LLDP_NEIGHBORS
    entries.extend(build_lldp_entries(lldp_data))

    # 4. Q-BRIDGE-MIB VLAN table -- all 6 VLANs trunked
    entries.extend(build_vlan_entries(VLANS))

    # 5. BRIDGE-MIB MAC forwarding table
    if topology_state is not None:
        mac_data = _build_mac_fwd_from_state(topology_state, device_id)
    else:
        # Without live state, generate sample MAC entries per active port.
        mac_data = _generate_sample_mac_entries()
    entries.extend(build_mac_fwd_entries(mac_data))

    return sort_mib_tree(entries)
