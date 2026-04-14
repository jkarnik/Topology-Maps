"""Shared MIB builder utilities for the SNMP simulator.

Provides helper functions to build OID-value trees that pysnmp can serve.
Each function returns a list of (oid_tuple, pysnmp_value) pairs representing
a subtree of a standard MIB.
"""

from __future__ import annotations

import hashlib
from bisect import insort
from typing import Union

from pysnmp.proto.rfc1902 import (
    Counter32,
    Gauge32,
    Integer32,
    ObjectIdentifier,
    OctetString,
    TimeTicks,
)

# ---------------------------------------------------------------------------
# OID prefix constants (as tuples of ints)
# ---------------------------------------------------------------------------

# SNMPv2-MIB::system  (1.3.6.1.2.1.1)
OID_SYSTEM = (1, 3, 6, 1, 2, 1, 1)
OID_SYS_DESCR = OID_SYSTEM + (1, 0)         # sysDescr.0
OID_SYS_OBJECT_ID = OID_SYSTEM + (2, 0)     # sysObjectID.0
OID_SYS_UPTIME = OID_SYSTEM + (3, 0)        # sysUpTime.0
OID_SYS_NAME = OID_SYSTEM + (5, 0)          # sysName.0

# IF-MIB::ifTable  (1.3.6.1.2.1.2.2.1)
OID_IF_TABLE = (1, 3, 6, 1, 2, 1, 2, 2, 1)
OID_IF_INDEX = OID_IF_TABLE + (1,)           # ifIndex.<idx>
OID_IF_DESCR = OID_IF_TABLE + (2,)           # ifDescr.<idx>
OID_IF_TYPE = OID_IF_TABLE + (3,)            # ifType.<idx>
OID_IF_SPEED = OID_IF_TABLE + (5,)           # ifSpeed.<idx>
OID_IF_ADMIN_STATUS = OID_IF_TABLE + (7,)    # ifAdminStatus.<idx>
OID_IF_OPER_STATUS = OID_IF_TABLE + (8,)     # ifOperStatus.<idx>

# IF-MIB::ifNumber (1.3.6.1.2.1.2.1.0)
OID_IF_NUMBER = (1, 3, 6, 1, 2, 1, 2, 1, 0)

# LLDP-MIB::lldpRemTable  (1.0.8802.1.1.2.1.4.1.1)
OID_LLDP_REM_TABLE = (1, 0, 8802, 1, 1, 2, 1, 4, 1, 1)
OID_LLDP_REM_CHASSIS_ID = OID_LLDP_REM_TABLE + (5,)    # .5
OID_LLDP_REM_PORT_ID = OID_LLDP_REM_TABLE + (7,)       # .7
OID_LLDP_REM_SYS_NAME = OID_LLDP_REM_TABLE + (9,)      # .9

# Q-BRIDGE-MIB::dot1qVlanStaticTable  (1.3.6.1.2.1.17.7.1.4.3.1)
OID_VLAN_STATIC_TABLE = (1, 3, 6, 1, 2, 1, 17, 7, 1, 4, 3, 1)

# BRIDGE-MIB::dot1dTpFdbTable  (1.3.6.1.2.1.17.4.3.1)
OID_FDB_TABLE = (1, 3, 6, 1, 2, 1, 17, 4, 3, 1)
OID_FDB_ADDRESS = OID_FDB_TABLE + (1,)      # dot1dTpFdbAddress
OID_FDB_PORT = OID_FDB_TABLE + (2,)         # dot1dTpFdbPort
OID_FDB_STATUS = OID_FDB_TABLE + (3,)       # dot1dTpFdbStatus

# ipNetToMediaTable (ARP)  (1.3.6.1.2.1.4.22.1)
OID_ARP_TABLE = (1, 3, 6, 1, 2, 1, 4, 22, 1)
OID_ARP_PHYS_ADDRESS = OID_ARP_TABLE + (2,)    # ipNetToMediaPhysAddress
OID_ARP_NET_ADDRESS = OID_ARP_TABLE + (3,)     # ipNetToMediaNetAddress

# POWER-ETHERNET-MIB::pethPsePortTable  (1.3.6.1.2.1.105.1.1.1)
OID_POE_TABLE = (1, 3, 6, 1, 2, 1, 105, 1, 1, 1)

# FORTINET-FORTIGATE-MIB::fgWcApTable  (1.3.6.1.4.1.12356.101.14.4.4.1)
OID_FG_AP_TABLE = (1, 3, 6, 1, 4, 1, 12356, 101, 14, 4, 4, 1)

# FORTINET-FORTIGATE-MIB::fgWcStaTable  (1.3.6.1.4.1.12356.101.14.4.5.1)
OID_FG_STA_TABLE = (1, 3, 6, 1, 4, 1, 12356, 101, 14, 4, 5, 1)

# IF-MIB interface type values (IANAifType)
IF_TYPE_ETHERNET_CSMACD = 6
IF_TYPE_SOFTWARELOOPBACK = 24
IF_TYPE_TUNNEL = 131
IF_TYPE_L2VLAN = 135
IF_TYPE_IEEE80211 = 71

# Admin/Oper status
STATUS_UP = 1
STATUS_DOWN = 2

# Bridge FDB status values
FDB_STATUS_LEARNED = 3

# PoE column sub-OIDs
POE_ADMIN_ENABLE = 1        # pethPsePortAdminEnable
POE_POWER_PAIRS = 2         # pethPsePortPowerPairs
POE_DETECTION_STATUS = 3    # pethPsePortDetectionStatus
POE_POWER_CLASS = 4         # pethPsePortPowerClassifications
POE_POWER_PRIORITY = 5      # pethPsePortPowerPriority
# Note: actual power in milliwatts is in pethMainPseTable, but we add a
# commonly-used enterprise extension for per-port watts here as column 10.
POE_PORT_POWER_WATTS = 10   # non-standard, but widely used by vendors


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def generate_mac(seed: str, index: int) -> str:
    """Generate a deterministic MAC address from a seed string and index.

    Returns a colon-separated MAC like ``"02:ab:cd:ef:01:23"``.
    The first octet has its locally-administered bit set (0x02).
    """
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    octets = list(digest[:6])
    octets[0] = (octets[0] | 0x02) & 0xFE  # locally administered, unicast
    return ":".join(f"{b:02x}" for b in octets)


def mac_str_to_bytes(mac: str) -> bytes:
    """Convert a MAC string (colon- or dash-separated) to 6 raw bytes."""
    return bytes(int(o, 16) for o in mac.replace("-", ":").split(":"))


def ip_str_to_oid_suffix(ip: str) -> tuple[int, ...]:
    """Convert an IP address string to an OID index suffix tuple.

    ``"10.0.1.5"`` becomes ``(10, 0, 1, 5)``.
    """
    return tuple(int(p) for p in ip.split("."))


def mac_str_to_oid_suffix(mac: str) -> tuple[int, ...]:
    """Convert a MAC address string to an OID index suffix tuple.

    ``"02:ab:cd:ef:01:23"`` becomes ``(2, 171, 205, 239, 1, 35)``.
    """
    return tuple(int(o, 16) for o in mac.replace("-", ":").split(":"))


def oid_to_tuple(oid_str: str) -> tuple[int, ...]:
    """Convert a dotted OID string to a tuple of ints.

    Leading dot is stripped if present:
    ``".1.3.6.1.2.1.1.1.0"`` and ``"1.3.6.1.2.1.1.1.0"`` both work.
    """
    if oid_str.startswith("."):
        oid_str = oid_str[1:]
    return tuple(int(part) for part in oid_str.split("."))


def sort_mib_tree(entries: list[tuple]) -> list[tuple]:
    """Sort MIB entries by OID for proper GETNEXT/WALK traversal.

    Each entry is ``(oid_tuple, pysnmp_value)``.
    Returns a new sorted list.
    """
    return sorted(entries, key=lambda item: item[0])


# ---------------------------------------------------------------------------
# MIB subtree builders
# ---------------------------------------------------------------------------

def build_system_mib(
    sys_descr: str,
    sys_name: str,
    sys_object_id: str,
    uptime_ticks: int = 60000,
) -> list[tuple]:
    """Build SNMPv2-MIB system group entries.

    Parameters
    ----------
    sys_descr : str
        Human-readable device description.
    sys_name : str
        The administratively-assigned name.
    sys_object_id : str
        Dotted-notation OID for ``sysObjectID`` (e.g. ``"1.3.6.1.4.1.12356.101"``).
    uptime_ticks : int
        ``sysUpTime`` in hundredths of a second (default 600 s).

    Returns a list of four ``(oid_tuple, value)`` pairs.
    """
    return [
        (OID_SYS_DESCR, OctetString(sys_descr)),
        (OID_SYS_OBJECT_ID, ObjectIdentifier(oid_to_tuple(sys_object_id))),
        (OID_SYS_UPTIME, TimeTicks(uptime_ticks)),
        (OID_SYS_NAME, OctetString(sys_name)),
    ]


def build_interface_entries(interfaces: list[dict]) -> list[tuple]:
    """Build IF-MIB ifTable entries.

    Each *interface* dict must contain:

    * ``name`` (str) -- e.g. ``"port1"``, ``"internal"``.
    * ``speed`` (int) -- bits per second (e.g. ``1_000_000_000``).
    * ``type`` (int) -- IANAifType integer (use the ``IF_TYPE_*`` constants).
    * ``status`` (str) -- ``"up"`` or ``"down"``.

    An optional ``index`` key overrides the auto-assigned 1-based index.

    Returns a flat list of ``(oid_tuple, value)`` pairs covering
    ``ifNumber``, ``ifIndex``, ``ifDescr``, ``ifType``, ``ifSpeed``,
    ``ifAdminStatus``, and ``ifOperStatus`` for every interface.
    """
    entries: list[tuple] = []
    entries.append((OID_IF_NUMBER, Integer32(len(interfaces))))

    for seq, iface in enumerate(interfaces, start=1):
        idx = iface.get("index", seq)
        admin = STATUS_UP if iface["status"] == "up" else STATUS_DOWN
        oper = admin  # mirror admin for simulation

        entries.extend([
            (OID_IF_INDEX + (idx,), Integer32(idx)),
            (OID_IF_DESCR + (idx,), OctetString(iface["name"])),
            (OID_IF_TYPE + (idx,), Integer32(iface["type"])),
            (OID_IF_SPEED + (idx,), Gauge32(iface["speed"])),
            (OID_IF_ADMIN_STATUS + (idx,), Integer32(admin)),
            (OID_IF_OPER_STATUS + (idx,), Integer32(oper)),
        ])

    return entries


def build_lldp_entries(neighbors: list[dict]) -> list[tuple]:
    """Build LLDP-MIB lldpRemTable entries.

    Each *neighbor* dict must contain:

    * ``local_port_idx`` (int) -- ifIndex of the local port.
    * ``chassis_id`` (str) -- remote chassis identifier (usually a MAC string).
    * ``port_id`` (str) -- remote port identifier.
    * ``sys_name`` (str) -- remote system name.

    The LLDP table is indexed by ``(timeMark, localPortNum, index)``.
    We use ``timeMark=0`` and ``index=1`` for simplicity.
    """
    entries: list[tuple] = []
    for neighbor in neighbors:
        lp = neighbor["local_port_idx"]
        # Index: timeMark(0) . localPortNum . remIndex(1)
        idx_suffix = (0, lp, 1)

        chassis_id_raw = neighbor["chassis_id"]
        # If it looks like a MAC, store as raw bytes; otherwise keep as string
        if ":" in chassis_id_raw or "-" in chassis_id_raw:
            chassis_val = OctetString(mac_str_to_bytes(chassis_id_raw))
        else:
            chassis_val = OctetString(chassis_id_raw)

        entries.extend([
            (OID_LLDP_REM_CHASSIS_ID + idx_suffix, chassis_val),
            (OID_LLDP_REM_PORT_ID + idx_suffix, OctetString(neighbor["port_id"])),
            (OID_LLDP_REM_SYS_NAME + idx_suffix, OctetString(neighbor["sys_name"])),
        ])

    return entries


def build_arp_entries(entries_data: list[dict]) -> list[tuple]:
    """Build ipNetToMediaTable (ARP) entries.

    Each dict must contain:

    * ``if_index`` (int) -- interface index.
    * ``ip`` (str) -- IP address.
    * ``mac`` (str) -- MAC address (colon-separated).

    The table is indexed by ``(ifIndex, ipAddress)``.
    """
    result: list[tuple] = []
    for entry in entries_data:
        idx_suffix = (entry["if_index"],) + ip_str_to_oid_suffix(entry["ip"])
        result.extend([
            (OID_ARP_PHYS_ADDRESS + idx_suffix, OctetString(mac_str_to_bytes(entry["mac"]))),
            (OID_ARP_NET_ADDRESS + idx_suffix, OctetString(entry["ip"])),
        ])
    return result


def build_mac_fwd_entries(entries_data: list[dict]) -> list[tuple]:
    """Build BRIDGE-MIB dot1dTpFdbTable entries.

    Each dict must contain:

    * ``mac`` (str) -- MAC address (colon-separated).
    * ``port`` (int) -- bridge port number.
    * ``status`` (int) -- FDB status (3 = learned).

    The table is indexed by the MAC address as 6 decimal octets.
    """
    result: list[tuple] = []
    for entry in entries_data:
        idx_suffix = mac_str_to_oid_suffix(entry["mac"])
        result.extend([
            (OID_FDB_ADDRESS + idx_suffix, OctetString(mac_str_to_bytes(entry["mac"]))),
            (OID_FDB_PORT + idx_suffix, Integer32(entry["port"])),
            (OID_FDB_STATUS + idx_suffix, Integer32(entry["status"])),
        ])
    return result


def build_poe_entries(ports: list[dict]) -> list[tuple]:
    """Build POWER-ETHERNET-MIB pethPsePortTable entries.

    Each dict must contain:

    * ``group_index`` (int) -- PSE group index (usually 1).
    * ``port_index`` (int) -- port index within the group.
    * ``power_watts`` (float) -- power delivered in watts.
    * ``status`` (str) -- ``"on"`` or ``"off"``.

    The table is indexed by ``(pethPsePortGroupIndex, pethPsePortIndex)``.
    """
    result: list[tuple] = []
    for port in ports:
        gi = port["group_index"]
        pi = port["port_index"]
        idx_suffix = (gi, pi)

        is_on = port["status"] == "on"
        # pethPsePortAdminEnable: true(1) / false(2)
        admin = Integer32(1 if is_on else 2)
        # pethPsePortDetectionStatus: deliveringPower(3) / disabled(1) / searching(2)
        detection = Integer32(3 if is_on else 1)
        # Per-port power in watts (non-standard column 10, widely used)
        power_mw = int(port["power_watts"] * 1000)

        result.extend([
            (OID_POE_TABLE + (POE_ADMIN_ENABLE,) + idx_suffix, admin),
            (OID_POE_TABLE + (POE_DETECTION_STATUS,) + idx_suffix, detection),
            (OID_POE_TABLE + (POE_PORT_POWER_WATTS,) + idx_suffix, Gauge32(power_mw)),
        ])

    return result


def build_vlan_entries(vlans: dict[int, dict]) -> list[tuple]:
    """Build Q-BRIDGE-MIB dot1qVlanStaticTable entries.

    *vlans* is a mapping of ``{vlan_id: {"name": str, ...}}``.
    The table is indexed by VLAN ID.

    Column sub-OIDs:
    * 1 -- dot1qVlanStaticName
    * 4 -- dot1qVlanStaticRowStatus (1 = active)
    """
    result: list[tuple] = []
    for vid, info in sorted(vlans.items()):
        result.extend([
            (OID_VLAN_STATIC_TABLE + (1, vid), OctetString(info.get("name", f"VLAN{vid}"))),
            (OID_VLAN_STATIC_TABLE + (4, vid), Integer32(1)),  # active
        ])
    return result


def build_fortigate_ap_entries(aps: list[dict]) -> list[tuple]:
    """Build FORTINET-FORTIGATE-MIB fgWcApTable entries.

    Each dict must contain:

    * ``index`` (int) -- row index (1-based).
    * ``serial`` (str) -- AP serial number.
    * ``name`` (str) -- AP name.
    * ``ip`` (str) -- AP IP address.
    * ``status`` (int) -- 1 = online, 2 = offline.
    * ``client_count`` (int) -- number of connected clients.

    Column sub-OIDs (from Fortinet MIB):
    * 3 -- fgWcApSerial
    * 4 -- fgWcApName
    * 5 -- fgWcApIp (IpAddress as OctetString of 4 bytes)
    * 7 -- fgWcApStatus
    * 8 -- fgWcApStationCount
    """
    result: list[tuple] = []
    for ap in aps:
        idx = ap["index"]
        ip_bytes = bytes(int(o) for o in ap["ip"].split("."))
        result.extend([
            (OID_FG_AP_TABLE + (3, idx), OctetString(ap["serial"])),
            (OID_FG_AP_TABLE + (4, idx), OctetString(ap["name"])),
            (OID_FG_AP_TABLE + (5, idx), OctetString(ip_bytes)),
            (OID_FG_AP_TABLE + (7, idx), Integer32(ap["status"])),
            (OID_FG_AP_TABLE + (8, idx), Gauge32(ap["client_count"])),
        ])
    return result


def build_fortigate_sta_entries(clients: list[dict]) -> list[tuple]:
    """Build FORTINET-FORTIGATE-MIB fgWcStaTable entries.

    Each dict must contain:

    * ``index`` (int) -- row index (1-based).
    * ``mac`` (str) -- client MAC address.
    * ``ip`` (str) -- client IP address.
    * ``ssid`` (str) -- SSID the client is associated with.
    * ``ap_name`` (str) -- name of the AP the client is on.
    * ``vlan`` (int) -- VLAN ID.

    Column sub-OIDs (from Fortinet MIB):
    * 2 -- fgWcStaMac
    * 3 -- fgWcStaIp (IpAddress as OctetString)
    * 4 -- fgWcStaSSID
    * 5 -- fgWcStaApName
    * 6 -- fgWcStaVlanId
    """
    result: list[tuple] = []
    for client in clients:
        idx = client["index"]
        ip_bytes = bytes(int(o) for o in client["ip"].split("."))
        result.extend([
            (OID_FG_STA_TABLE + (2, idx), OctetString(mac_str_to_bytes(client["mac"]))),
            (OID_FG_STA_TABLE + (3, idx), OctetString(ip_bytes)),
            (OID_FG_STA_TABLE + (4, idx), OctetString(client["ssid"])),
            (OID_FG_STA_TABLE + (5, idx), OctetString(client["ap_name"])),
            (OID_FG_STA_TABLE + (6, idx), Integer32(client["vlan"])),
        ])
    return result
