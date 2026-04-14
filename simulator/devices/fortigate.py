"""FortiGate 200G SNMP device implementation.

Builds the complete MIB tree for a FortiGate 200G firewall in an HA pair.
The primary and standby units share the same interface layout but differ
in their system name, management IP, LLDP uplink port, and HA role.
"""

from __future__ import annotations

from pysnmp.proto.rfc1902 import Integer32, IpAddress, OctetString

from simulator.constants import DEVICE_IPS, VLANS
from simulator.devices.base import (
    IF_TYPE_ETHERNET_CSMACD,
    IF_TYPE_L2VLAN,
    build_arp_entries,
    build_fortigate_ap_entries,
    build_fortigate_sta_entries,
    build_interface_entries,
    build_lldp_entries,
    build_system_mib,
    generate_mac,
    sort_mib_tree,
)

# ---------------------------------------------------------------------------
# FortiGate-specific OID prefixes
# ---------------------------------------------------------------------------

# ipRouteTable (1.3.6.1.2.1.4.21.1)
OID_IP_ROUTE_TABLE = (1, 3, 6, 1, 2, 1, 4, 21, 1)
OID_IP_ROUTE_DEST = OID_IP_ROUTE_TABLE + (1,)       # ipRouteDest
OID_IP_ROUTE_IF_INDEX = OID_IP_ROUTE_TABLE + (2,)   # ipRouteIfIndex
OID_IP_ROUTE_NEXT_HOP = OID_IP_ROUTE_TABLE + (7,)   # ipRouteNextHop
OID_IP_ROUTE_TYPE = OID_IP_ROUTE_TABLE + (8,)        # ipRouteType
OID_IP_ROUTE_MASK = OID_IP_ROUTE_TABLE + (11,)       # ipRouteMask

# FORTINET-FORTIGATE-MIB HA status
# fgHaSystemMode (1.3.6.1.4.1.12356.101.13.1.1.0) -- 1=standalone, 2=activePassive
OID_FG_HA_SYSTEM_MODE = (1, 3, 6, 1, 4, 1, 12356, 101, 13, 1, 1, 0)
# fgHaStatsIndex (1.3.6.1.4.1.12356.101.13.2.1.1.1.<idx>)
OID_FG_HA_STATS = (1, 3, 6, 1, 4, 1, 12356, 101, 13, 2, 1, 1)
# Column sub-OIDs within fgHaStatsEntry
FG_HA_STATS_INDEX = 1       # fgHaStatsIndex
FG_HA_STATS_SERIAL = 2      # fgHaStatsSerial
FG_HA_STATS_HOSTNAME = 11   # fgHaStatsHostname
FG_HA_STATS_SYNC_STATUS = 3 # fgHaStatsSyncStatus (0=unsync, 1=synced)
FG_HA_STATS_MASTER = 15     # fgHaStatsMasterSerial

# Route type values (RFC 1213)
ROUTE_TYPE_DIRECT = 3   # direct (connected)
ROUTE_TYPE_INDIRECT = 4  # indirect (via gateway)

# FortiGate system OID (Fortinet enterprise + product sub-tree)
FG_SYS_OBJECT_ID = "1.3.6.1.4.1.12356.101.1.200"

# FortiGate firmware string
FG_SYS_DESCR = "Fortinet FortiGate 200G v7.4.3 build3456"

# ---------------------------------------------------------------------------
# Interface definitions
# ---------------------------------------------------------------------------

# VLAN sub-interface index mapping: VLAN ID -> ifIndex
_VLAN_IF_INDEX = {10: 5, 20: 6, 30: 7, 40: 8, 50: 9, 60: 10}

# ifSpeed is Gauge32 (max 4,294,967,295).  For 10G links the standard
# convention is to report the Gauge32 max and put the true speed in
# ifHighSpeed (which we don't implement here).  1G fits in Gauge32.
_SPEED_10G = 4_294_967_295  # Gauge32 overflow sentinel for 10 Gbps
_SPEED_1G = 1_000_000_000

_FORTIGATE_INTERFACES = [
    {"name": "WAN1", "speed": _SPEED_10G, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up", "index": 1},
    {"name": "WAN2", "speed": _SPEED_10G, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up", "index": 2},
    {"name": "port5", "speed": _SPEED_10G, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up", "index": 3},
    {"name": "HA-link", "speed": _SPEED_1G, "type": IF_TYPE_ETHERNET_CSMACD, "status": "up", "index": 4},
    {"name": "vlan10", "speed": _SPEED_10G, "type": IF_TYPE_L2VLAN, "status": "up", "index": 5},
    {"name": "vlan20", "speed": _SPEED_10G, "type": IF_TYPE_L2VLAN, "status": "up", "index": 6},
    {"name": "vlan30", "speed": _SPEED_10G, "type": IF_TYPE_L2VLAN, "status": "up", "index": 7},
    {"name": "vlan40", "speed": _SPEED_10G, "type": IF_TYPE_L2VLAN, "status": "up", "index": 8},
    {"name": "vlan50", "speed": _SPEED_10G, "type": IF_TYPE_L2VLAN, "status": "up", "index": 9},
    {"name": "vlan60", "speed": _SPEED_10G, "type": IF_TYPE_L2VLAN, "status": "up", "index": 10},
]

# ---------------------------------------------------------------------------
# IP route definitions
# ---------------------------------------------------------------------------

# Each route: (dest, mask, next_hop, if_index, route_type)
# VLAN subnets are directly connected via the VLAN sub-interface.
# Default route goes out WAN1 (ifIndex 1).
_ROUTES = [
    ("10.10.10.0", "255.255.255.0", "0.0.0.0", _VLAN_IF_INDEX[10], ROUTE_TYPE_DIRECT),
    ("10.10.20.0", "255.255.255.0", "0.0.0.0", _VLAN_IF_INDEX[20], ROUTE_TYPE_DIRECT),
    ("10.10.30.0", "255.255.254.0", "0.0.0.0", _VLAN_IF_INDEX[30], ROUTE_TYPE_DIRECT),
    ("10.10.40.0", "255.255.255.0", "0.0.0.0", _VLAN_IF_INDEX[40], ROUTE_TYPE_DIRECT),
    ("10.10.50.0", "255.255.254.0", "0.0.0.0", _VLAN_IF_INDEX[50], ROUTE_TYPE_DIRECT),
    ("172.16.0.0", "255.255.240.0", "0.0.0.0", _VLAN_IF_INDEX[60], ROUTE_TYPE_DIRECT),
    ("0.0.0.0", "0.0.0.0", "198.51.100.1", 1, ROUTE_TYPE_INDIRECT),  # default via WAN1
]


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _ip_to_oid_suffix(ip: str) -> tuple[int, ...]:
    """Convert a dotted IP to an OID index suffix."""
    return tuple(int(p) for p in ip.split("."))


def _build_route_entries(routes: list[tuple]) -> list[tuple]:
    """Build ipRouteTable entries from route tuples.

    Each route is (dest, mask, next_hop, if_index, route_type).
    The table is indexed by ipRouteDest.
    """
    result: list[tuple] = []
    for dest, mask, next_hop, if_index, route_type in routes:
        idx = _ip_to_oid_suffix(dest)
        result.extend([
            (OID_IP_ROUTE_DEST + idx, IpAddress(dest)),
            (OID_IP_ROUTE_IF_INDEX + idx, Integer32(if_index)),
            (OID_IP_ROUTE_NEXT_HOP + idx, IpAddress(next_hop)),
            (OID_IP_ROUTE_TYPE + idx, Integer32(route_type)),
            (OID_IP_ROUTE_MASK + idx, IpAddress(mask)),
        ])
    return result


def _build_ha_entries(is_primary: bool, sys_name: str) -> list[tuple]:
    """Build Fortinet HA MIB entries.

    Sets the HA system mode to active-passive (2) and populates a
    single-row fgHaStatsEntry for this unit.
    """
    ha_index = 1 if is_primary else 2
    serial = "FG200G0000000001" if is_primary else "FG200G0000000002"
    master_serial = "FG200G0000000001"  # primary is always master
    sync_status = 1  # synced

    result: list[tuple] = [
        # HA mode: 2 = active-passive
        (OID_FG_HA_SYSTEM_MODE, Integer32(2)),
        # HA stats row for this unit
        (OID_FG_HA_STATS + (FG_HA_STATS_INDEX, ha_index), Integer32(ha_index)),
        (OID_FG_HA_STATS + (FG_HA_STATS_SERIAL, ha_index), OctetString(serial)),
        (OID_FG_HA_STATS + (FG_HA_STATS_SYNC_STATUS, ha_index), Integer32(sync_status)),
        (OID_FG_HA_STATS + (FG_HA_STATS_HOSTNAME, ha_index), OctetString(sys_name)),
        (OID_FG_HA_STATS + (FG_HA_STATS_MASTER, ha_index), OctetString(master_serial)),
    ]
    return result


def _build_wireless_ap_entries(topology_state) -> list[tuple]:
    """Build fgWcApTable entries from the topology state.

    One row per managed AP (56 total).  Uses
    :func:`~simulator.devices.base.build_fortigate_ap_entries` for the
    actual OID generation.
    """
    aps = topology_state.get_all_aps() if topology_state else []
    if not aps:
        return []

    ap_dicts: list[dict] = []
    for seq, ap in enumerate(aps, start=1):
        ap_dicts.append({
            "index": seq,
            "serial": ap.serial,
            "name": ap.name,
            "ip": ap.ip,
            "status": 1 if ap.status == "up" else 2,
            "client_count": ap.client_count,
        })
    return build_fortigate_ap_entries(ap_dicts)


def _build_wireless_sta_entries(topology_state) -> list[tuple]:
    """Build fgWcStaTable entries from the topology state.

    One row per wireless client (~940 total).  Uses
    :func:`~simulator.devices.base.build_fortigate_sta_entries` for the
    actual OID generation.
    """
    clients = topology_state.get_all_wireless_clients() if topology_state else []
    if not clients:
        return []

    # Build a mapping from ap_id -> AP name for the ap_name column
    aps = topology_state.get_all_aps() if topology_state else []
    ap_name_map: dict[str, str] = {ap.ap_id: ap.name for ap in aps}

    sta_dicts: list[dict] = []
    for seq, client in enumerate(clients, start=1):
        sta_dicts.append({
            "index": seq,
            "mac": client.mac,
            "ip": client.ip,
            "ssid": client.ssid,
            "ap_name": ap_name_map.get(client.ap_id, "Unknown"),
            "vlan": client.vlan,
        })
    return build_fortigate_sta_entries(sta_dicts)


def _build_fortigate_arp_entries(device_id: str) -> list[tuple]:
    """Build sample ARP entries for the FortiGate's VLAN gateway addresses.

    Each VLAN gets an ARP entry for a sample host (the .1 gateway address
    of each subnet is the FortiGate itself, so we use a .10 host as a
    representative endpoint).
    """
    # Sample ARP entries: one host per VLAN mapped to the VLAN sub-interface
    sample_hosts = [
        {"if_index": _VLAN_IF_INDEX[10], "ip": "10.10.10.10", "mac": generate_mac(device_id + "-arp", 10)},
        {"if_index": _VLAN_IF_INDEX[20], "ip": "10.10.20.10", "mac": generate_mac(device_id + "-arp", 20)},
        {"if_index": _VLAN_IF_INDEX[30], "ip": "10.10.30.10", "mac": generate_mac(device_id + "-arp", 30)},
        {"if_index": _VLAN_IF_INDEX[40], "ip": "10.10.40.10", "mac": generate_mac(device_id + "-arp", 40)},
        {"if_index": _VLAN_IF_INDEX[50], "ip": "10.10.50.10", "mac": generate_mac(device_id + "-arp", 50)},
        {"if_index": _VLAN_IF_INDEX[60], "ip": "172.16.0.10", "mac": generate_mac(device_id + "-arp", 60)},
    ]
    return build_arp_entries(sample_hosts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_fortigate_mib_tree(device_id: str, topology_state) -> list[tuple]:
    """Build the full MIB tree for a FortiGate device.

    Args:
        device_id: ``"fg-primary"`` or ``"fg-standby"``.
        topology_state: :class:`~simulator.topology_state.TopologyState`
            instance to read current state from.

    Returns:
        Sorted list of ``(oid_tuple, pysnmp_value)`` pairs ready to be
        served by :class:`~simulator.agent.SNMPAgent`.
    """
    is_primary = device_id == "fg-primary"
    sys_name = "FG-PRIMARY" if is_primary else "FG-STANDBY"
    core_sw_ip = DEVICE_IPS["core-sw"]

    # -- 1. SNMPv2-MIB system group --
    entries = build_system_mib(
        sys_descr=FG_SYS_DESCR,
        sys_name=sys_name,
        sys_object_id=FG_SYS_OBJECT_ID,
    )

    # -- 2. IF-MIB interfaces --
    entries.extend(build_interface_entries(_FORTIGATE_INTERFACES))

    # -- 3. LLDP-MIB neighbors --
    # Map port names to ifIndex for building LLDP entries.
    _PORT_NAME_TO_IF_INDEX = {
        "WAN1": 1,
        "WAN2": 2,
        "port5": 3,
        "HA-link": 4,
    }

    device_state = topology_state.get_device(device_id) if topology_state else None
    if device_state and device_state.lldp_neighbors:
        # Build LLDP entries from live topology state so all neighbors
        # (core switch uplink + HA-link peer) are included.
        lldp_neighbors = []
        for neighbor in device_state.lldp_neighbors:
            local_port_idx = _PORT_NAME_TO_IF_INDEX.get(neighbor.local_port)
            if local_port_idx is None:
                continue  # skip unknown ports
            lldp_neighbors.append({
                "local_port_idx": local_port_idx,
                "chassis_id": generate_mac(neighbor.remote_device_id, 0),
                "port_id": neighbor.remote_port,
                "sys_name": neighbor.remote_device_name,
            })
    else:
        # Fallback: hardcode only the core-switch uplink neighbor.
        remote_port = "port1" if is_primary else "port2"
        lldp_neighbors = [
            {
                "local_port_idx": 3,  # port5
                "chassis_id": generate_mac("core-sw", 0),
                "port_id": remote_port,
                "sys_name": "CORE-SW",
            },
        ]
    entries.extend(build_lldp_entries(lldp_neighbors))

    # -- 4. IP-MIB ipRouteTable --
    entries.extend(_build_route_entries(_ROUTES))

    # -- 5. ARP table (ipNetToMediaTable) --
    entries.extend(_build_fortigate_arp_entries(device_id))

    # -- 6. FORTINET-FORTIGATE-MIB HA status --
    entries.extend(_build_ha_entries(is_primary, sys_name))

    # -- 7. FORTINET-FORTIGATE-MIB wireless controller tables --
    # Only the primary FortiGate acts as the wireless controller.
    if is_primary:
        entries.extend(_build_wireless_ap_entries(topology_state))
        entries.extend(_build_wireless_sta_entries(topology_state))

    return sort_mib_tree(entries)
