"""MIB tree builder for FortiSwitch 448E-FPOE floor switches.

Each floor has one 448E-FPOE with 48 access ports (PoE) and 2 uplink ports.
Ports 1-14 connect to FortiAPs, remaining access ports connect to wired
endpoints (POS, cameras, operations PCs, IoT). Port 49 is the uplink to
the Core Switch; port 50 is a spare (admin down).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from simulator.constants import (
    AP_BASE_IP,
    AP_IP_START,
    APS_PER_FLOOR,
    DEVICE_IPS,
    VLANS,
)
from simulator.devices.base import (
    FDB_STATUS_LEARNED,
    IF_TYPE_ETHERNET_CSMACD,
    STATUS_DOWN,
    STATUS_UP,
    build_arp_entries,
    build_interface_entries,
    build_lldp_entries,
    build_mac_fwd_entries,
    build_poe_entries,
    build_system_mib,
    build_vlan_entries,
    generate_mac,
    sort_mib_tree,
)

if TYPE_CHECKING:
    from simulator.topology_state import TopologyState

# ---------------------------------------------------------------------------
# Constants for the floor switch
# ---------------------------------------------------------------------------

_TOTAL_ACCESS_PORTS = 48
_UPLINK_PORT_INDEX = 49
_SPARE_UPLINK_INDEX = 50
_TOTAL_PORTS = 50

_SYS_DESCR = "Fortinet FortiSwitch 448E-FPOE v7.4.3"
_SYS_OBJECT_ID = "1.3.6.1.4.1.12356.106.1.448"

_SPEED_1G = 1_000_000_000

# Port ranges for wired endpoint types (per-floor, after AP ports 1-14).
# Ports 15-20: POS terminals (VLAN 10)
# Ports 21-23: Operations PCs (VLAN 20)
# Ports 24-35: IP cameras (VLAN 40)
# Ports 36-48: IoT devices (VLAN 50)
_PORT_RANGES = {
    10: range(15, 21),   # POS: ports 15-20 (6 per floor)
    20: range(21, 24),   # Ops PCs: ports 21-23 (3 per floor)
    40: range(24, 36),   # Cameras: ports 24-35 (12 per floor)
    50: range(36, 49),   # IoT: ports 36-48 (13 per floor)
}

# PoE power draw per device type (watts)
_POE_WATTS = {
    "ap": 25.0,
    "pos": 10.0,
    "camera": 15.0,
    "ops_pc": 0.0,   # PCs typically not PoE-powered
    "iot": 5.0,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ap_ip(floor: int, ap_index: int) -> str:
    """Return the IP for AP number *ap_index* (0-based) on *floor* (1-based)."""
    octet = AP_IP_START + (floor - 1) * APS_PER_FLOOR + ap_index
    return f"{AP_BASE_IP}.{octet}"


def _ap_id(floor: int, ap_index: int) -> str:
    """Return the device ID for an AP, e.g. ``'ap-1-01'``."""
    return f"ap-{floor}-{ap_index + 1:02d}"


def _ap_name(floor: int, ap_index: int) -> str:
    """Return the display name for an AP, e.g. ``'AP-1-01'``."""
    return f"AP-{floor}-{ap_index + 1:02d}"


def _core_remote_port(floor: int) -> str:
    """Return the Core Switch port that this floor switch uplinks to.

    Floor 1 -> port3, Floor 2 -> port4, etc.
    """
    return f"port{3 + floor - 1}"


def _vlan_for_port(port_index: int) -> int | None:
    """Return the access VLAN for a wired endpoint port, or None for AP/uplink ports."""
    for vlan, rng in _PORT_RANGES.items():
        if port_index in rng:
            return vlan
    return None


def _device_type_for_port(port_index: int) -> str | None:
    """Return the device type string for a wired endpoint port."""
    if 15 <= port_index <= 20:
        return "pos"
    if 21 <= port_index <= 23:
        return "ops_pc"
    if 24 <= port_index <= 35:
        return "camera"
    if 36 <= port_index <= 48:
        return "iot"
    return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_floor_switch_mib_tree(
    device_id: str,
    floor: int,
    topology_state: TopologyState,
) -> list[tuple]:
    """Build the full MIB tree for a floor switch.

    Args:
        device_id: ``"floor-sw-1"`` through ``"floor-sw-4"``.
        floor: Floor number (1-4).
        topology_state: :class:`TopologyState` instance (used to pull
            dynamic LLDP/ARP/MAC data when available).

    Returns:
        Sorted list of ``(oid_tuple, pysnmp_value)`` pairs.
    """
    entries: list[tuple] = []

    # ------------------------------------------------------------------
    # 1. SNMPv2-MIB  (system)
    # ------------------------------------------------------------------
    entries.extend(build_system_mib(
        sys_descr=_SYS_DESCR,
        sys_name=f"FLOOR-SW-{floor}",
        sys_object_id=_SYS_OBJECT_ID,
    ))

    # ------------------------------------------------------------------
    # 2. IF-MIB  (interfaces)
    # ------------------------------------------------------------------
    interfaces = _build_interfaces(floor, topology_state, device_id)
    entries.extend(build_interface_entries(interfaces))

    # ------------------------------------------------------------------
    # 3. LLDP-MIB  (neighbors)
    # ------------------------------------------------------------------
    lldp_neighbors = _build_lldp_neighbors(floor, topology_state, device_id)
    entries.extend(build_lldp_entries(lldp_neighbors))

    # ------------------------------------------------------------------
    # 4. Q-BRIDGE-MIB  (VLANs)
    # ------------------------------------------------------------------
    entries.extend(build_vlan_entries(VLANS))

    # ------------------------------------------------------------------
    # 5. POWER-ETHERNET-MIB  (PoE)
    # ------------------------------------------------------------------
    poe_data = _build_poe_data(floor, topology_state, device_id)
    entries.extend(build_poe_entries(poe_data))

    # ------------------------------------------------------------------
    # 6. BRIDGE-MIB  (MAC forwarding)
    # ------------------------------------------------------------------
    mac_data = _build_mac_table(floor, topology_state, device_id)
    entries.extend(build_mac_fwd_entries(mac_data))

    # ------------------------------------------------------------------
    # 7. RFC1213-MIB  (ARP)
    # ------------------------------------------------------------------
    arp_data = _build_arp_table(floor, topology_state, device_id)
    entries.extend(build_arp_entries(arp_data))

    return sort_mib_tree(entries)


# ---------------------------------------------------------------------------
# Section builders (private)
# ---------------------------------------------------------------------------

def _build_interfaces(
    floor: int,
    topology_state: TopologyState,
    device_id: str,
) -> list[dict]:
    """Return the 50-element interface list for build_interface_entries."""
    ifaces: list[dict] = []

    # Ports 1-48: access ports
    for idx in range(1, _TOTAL_ACCESS_PORTS + 1):
        ifaces.append({
            "index": idx,
            "name": f"port{idx}",
            "speed": _SPEED_1G,
            "type": IF_TYPE_ETHERNET_CSMACD,
            "status": "up",
        })

    # Port 49: uplink to Core Switch (always up)
    ifaces.append({
        "index": _UPLINK_PORT_INDEX,
        "name": "port49",
        "speed": _SPEED_1G,
        "type": IF_TYPE_ETHERNET_CSMACD,
        "status": "up",
    })

    # Port 50: spare uplink (admin down)
    ifaces.append({
        "index": _SPARE_UPLINK_INDEX,
        "name": "port50",
        "speed": _SPEED_1G,
        "type": IF_TYPE_ETHERNET_CSMACD,
        "status": "down",
    })

    return ifaces


def _build_lldp_neighbors(
    floor: int,
    topology_state: TopologyState,
    device_id: str,
) -> list[dict]:
    """Build LLDP neighbor dicts for all directly connected LLDP peers.

    Returns a list suitable for :func:`build_lldp_entries`.
    """
    neighbors: list[dict] = []

    # --- Uplink: port49 -> Core Switch ---
    core_ip = DEVICE_IPS["core-sw"]
    core_mac = generate_mac("core-sw", 0)
    neighbors.append({
        "local_port_idx": _UPLINK_PORT_INDEX,
        "chassis_id": core_mac,
        "port_id": _core_remote_port(floor),
        "sys_name": "CORE-SW",
    })

    # --- APs on ports 1-14 ---
    # Prefer live state from topology_state; fall back to deterministic defaults.
    aps_on_floor = topology_state.get_aps_on_floor(floor) if topology_state else []
    aps_by_port: dict[str, object] = {}
    for ap in aps_on_floor:
        aps_by_port[ap.parent_port] = ap

    for ap_idx in range(APS_PER_FLOOR):
        port_idx = ap_idx + 1
        port_name = f"port{port_idx}"

        ap_info = aps_by_port.get(port_name)
        if ap_info is not None:
            ap_mac = generate_mac(ap_info.ap_id, 0)
            neighbors.append({
                "local_port_idx": port_idx,
                "chassis_id": ap_mac,
                "port_id": "eth0",
                "sys_name": ap_info.name,
            })
        else:
            # Deterministic fallback
            aid = _ap_id(floor, ap_idx)
            neighbors.append({
                "local_port_idx": port_idx,
                "chassis_id": generate_mac(aid, 0),
                "port_id": "eth0",
                "sys_name": _ap_name(floor, ap_idx),
            })

    return neighbors


def _build_poe_data(
    floor: int,
    topology_state: TopologyState,
    device_id: str,
) -> list[dict]:
    """Build PoE port entries for all 48 access ports.

    Uplink ports (49-50) are excluded since they are not PoE-capable on this model.
    Uses live ``poe_ports`` data from the topology state when available,
    falling back to static defaults for ports without overrides.
    """
    device_state = topology_state.get_device(device_id) if topology_state else None
    live_poe: dict[str, float] = {}
    if device_state and device_state.poe_ports:
        live_poe = device_state.poe_ports

    poe: list[dict] = []

    for port_idx in range(1, _TOTAL_ACCESS_PORTS + 1):
        port_name = f"port{port_idx}"
        if port_name in live_poe:
            watts = live_poe[port_name]
            status = "on" if watts > 0 else "off"
        elif port_idx <= APS_PER_FLOOR:
            # AP port
            watts = _POE_WATTS["ap"]
            status = "on"
        else:
            dtype = _device_type_for_port(port_idx)
            watts = _POE_WATTS.get(dtype or "", 0.0)
            status = "on" if watts > 0 else "off"

        poe.append({
            "group_index": 1,
            "port_index": port_idx,
            "power_watts": watts,
            "status": status,
        })

    return poe


def _build_mac_table(
    floor: int,
    topology_state: TopologyState,
    device_id: str,
) -> list[dict]:
    """Build MAC forwarding table entries.

    Uses live state from topology_state when available; otherwise generates
    placeholder entries for each wired endpoint port and AP port.
    """
    device_state = topology_state.get_device(device_id) if topology_state else None
    if device_state and device_state.mac_table:
        mac_entries: list[dict] = []

        # Always include AP MACs on ports 1-14
        for ap_idx in range(APS_PER_FLOOR):
            port_idx = ap_idx + 1
            aid = _ap_id(floor, ap_idx)
            mac_entries.append({
                "mac": generate_mac(aid, 0),
                "port": port_idx,
                "status": FDB_STATUS_LEARNED,
            })

        # Add wired endpoint MACs from live state
        mac_entries.extend([
            {"mac": e.mac, "port": int(e.port.replace("port", "")), "status": FDB_STATUS_LEARNED}
            for e in device_state.mac_table
        ])
        return mac_entries

    # Placeholder: one MAC per connected port
    mac_entries = []

    # APs on ports 1-14
    for ap_idx in range(APS_PER_FLOOR):
        port_idx = ap_idx + 1
        aid = _ap_id(floor, ap_idx)
        mac_entries.append({
            "mac": generate_mac(aid, 0),
            "port": port_idx,
            "status": FDB_STATUS_LEARNED,
        })

    # Wired endpoints on ports 15-48
    for port_idx in range(APS_PER_FLOOR + 1, _TOTAL_ACCESS_PORTS + 1):
        mac_entries.append({
            "mac": generate_mac(f"{device_id}-port{port_idx}", 0),
            "port": port_idx,
            "status": FDB_STATUS_LEARNED,
        })

    return mac_entries


def _build_arp_table(
    floor: int,
    topology_state: TopologyState,
    device_id: str,
) -> list[dict]:
    """Build ARP table entries.

    Uses live state from topology_state when available; otherwise generates
    placeholder entries for APs (whose IPs are deterministic).
    """
    device_state = topology_state.get_device(device_id) if topology_state else None
    if device_state and device_state.arp_table:
        arp_entries: list[dict] = []

        # Always include AP ARP entries on ports 1-14
        for ap_idx in range(APS_PER_FLOOR):
            port_idx = ap_idx + 1
            aid = _ap_id(floor, ap_idx)
            arp_entries.append({
                "if_index": port_idx,
                "ip": _ap_ip(floor, ap_idx),
                "mac": generate_mac(aid, 0),
            })

        # Add wired endpoint ARP entries from live state
        arp_entries.extend([
            {
                "if_index": int(e.port.replace("port", "")),
                "ip": e.ip,
                "mac": e.mac,
            }
            for e in device_state.arp_table
        ])
        return arp_entries

    # Placeholder: ARP entries for the 14 APs (known IPs)
    arp_entries = []
    for ap_idx in range(APS_PER_FLOOR):
        port_idx = ap_idx + 1
        aid = _ap_id(floor, ap_idx)
        arp_entries.append({
            "if_index": port_idx,
            "ip": _ap_ip(floor, ap_idx),
            "mac": generate_mac(aid, 0),
        })

    return arp_entries
