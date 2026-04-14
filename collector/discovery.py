"""Network discovery via SNMP LLDP and ARP walking.

Starting from a seed device (typically the FortiGate primary), the
discovery engine queries each device's SNMP agent for system identity,
LLDP neighbors, ARP/MAC tables, and (on the FortiGate) wireless AP and
station tables.  It follows LLDP links recursively to discover every
infrastructure device in the topology.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from collector.snmp_client import SNMPClient
from simulator.constants import (
    DEVICE_IPS,
    DEVICE_MODELS,
    DEVICE_TYPES,
    DEVICE_FLOORS,
    SNMP_PORTS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OID prefix strings used for WALK / GET
# ---------------------------------------------------------------------------

# System MIB
_OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
_OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"

# LLDP remote table
_OID_LLDP_REM_TABLE = "1.0.8802.1.1.2.1.4.1.1"
_OID_LLDP_REM_CHASSIS_ID = "1.0.8802.1.1.2.1.4.1.1.5"
_OID_LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
_OID_LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"

# ARP table (ipNetToMediaTable)
_OID_ARP_TABLE = "1.3.6.1.2.1.4.22.1"
_OID_ARP_PHYS_ADDR = "1.3.6.1.2.1.4.22.1.2"
_OID_ARP_NET_ADDR = "1.3.6.1.2.1.4.22.1.3"

# MAC forwarding table (dot1dTpFdbTable)
_OID_FDB_TABLE = "1.3.6.1.2.1.17.4.3.1"
_OID_FDB_ADDRESS = "1.3.6.1.2.1.17.4.3.1.1"
_OID_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"
_OID_FDB_STATUS = "1.3.6.1.2.1.17.4.3.1.3"

# FortiGate wireless controller tables
_OID_FG_AP_TABLE = "1.3.6.1.4.1.12356.101.14.4.4.1"
_OID_FG_STA_TABLE = "1.3.6.1.4.1.12356.101.14.4.5.1"

# IP route table
_OID_IP_ROUTE_TABLE = "1.3.6.1.2.1.4.21.1"

# FortiGate AP sub-OIDs
_FG_AP_SERIAL = "3"
_FG_AP_NAME = "4"
_FG_AP_IP = "5"
_FG_AP_STATUS = "7"
_FG_AP_STA_COUNT = "8"

# FortiGate STA sub-OIDs
_FG_STA_MAC = "2"
_FG_STA_IP = "3"
_FG_STA_SSID = "4"
_FG_STA_AP_NAME = "5"
_FG_STA_VLAN = "6"


# ---------------------------------------------------------------------------
# Reverse-lookup helpers
# ---------------------------------------------------------------------------

def _build_sysname_to_device_map() -> dict[str, str]:
    """Build a mapping from uppercase SNMP sysName to device_id.

    The simulator uses names like ``"FG-PRIMARY"`` / ``"CORE-SW"`` /
    ``"FLOOR-SW-1"`` etc.
    """
    mapping: dict[str, str] = {}
    for device_id in SNMP_PORTS:
        # Convention: sysName is device_id uppercased with underscores preserved
        sys_name = device_id.upper()
        mapping[sys_name] = device_id
    return mapping


def _build_ip_to_device_map() -> dict[str, str]:
    """Build a mapping from IP address to device_id."""
    return {ip: did for did, ip in DEVICE_IPS.items()}


_SYSNAME_MAP = _build_sysname_to_device_map()
_IP_MAP = _build_ip_to_device_map()


def _resolve_device_id(sys_name: str, chassis_id: str = "") -> Optional[str]:
    """Resolve an LLDP neighbor's sysName to our device_id.

    Falls back to chassis_id matching if sysName lookup fails.
    """
    # Direct sysName match
    normalised = sys_name.strip().upper()
    if normalised in _SYSNAME_MAP:
        return _SYSNAME_MAP[normalised]

    # Try with underscores replaced by dashes
    alt = normalised.replace("_", "-")
    if alt in _SYSNAME_MAP:
        return _SYSNAME_MAP[alt]

    return None


# ---------------------------------------------------------------------------
# Value extraction helpers
# ---------------------------------------------------------------------------

def _bytes_to_mac(raw: bytes) -> str:
    """Convert raw 6-byte MAC to colon-separated string."""
    if len(raw) == 6:
        return ":".join(f"{b:02x}" for b in raw)
    # Fallback: already a string representation
    return raw.hex() if isinstance(raw, bytes) else str(raw)


def _bytes_to_ip(raw: bytes) -> str:
    """Convert raw 4-byte IP address to dotted string."""
    if len(raw) == 4:
        return ".".join(str(b) for b in raw)
    return str(raw)


def _extract_value(val) -> str:
    """Extract a usable Python string from a pysnmp value object."""
    # OctetString -> try to get raw bytes first
    if hasattr(val, "asOctets"):
        raw = bytes(val.asOctets())
        # If it looks like printable ASCII, return as string
        try:
            text = raw.decode("ascii")
            if text.isprintable():
                return text
        except (UnicodeDecodeError, ValueError):
            pass
        return raw.hex()
    if hasattr(val, "prettyPrint"):
        return val.prettyPrint()
    return str(val)


def _extract_raw_bytes(val) -> bytes:
    """Extract raw bytes from a pysnmp OctetString value."""
    if hasattr(val, "asOctets"):
        return bytes(val.asOctets())
    if isinstance(val, bytes):
        return val
    return str(val).encode()


def _extract_int(val) -> int:
    """Extract an integer from a pysnmp Integer/Gauge value."""
    return int(val)


# ---------------------------------------------------------------------------
# TopologyDiscovery
# ---------------------------------------------------------------------------

class TopologyDiscovery:
    """Discovers the full network topology by walking SNMP agents.

    Starting from a seed device, it recursively follows LLDP neighbor
    tables to find all infrastructure devices, then collects ARP, MAC,
    and wireless data from each.
    """

    def __init__(self, client: SNMPClient):
        self.client = client

    async def discover_from_seed(self, seed_device_id: str = "fg-primary") -> dict:
        """Discover full topology starting from seed device.

        Returns a dict with:
        - ``devices``: list of discovered device dicts
        - ``lldp_edges``: list of LLDP neighbor pair dicts
        - ``arp_entries``: dict of device_id -> list of ARP entry dicts
        - ``mac_entries``: dict of device_id -> list of MAC entry dicts
        - ``wireless_aps``: list of AP dicts (from FortiGate)
        - ``wireless_clients``: list of wireless client dicts
        - ``routes``: list of route dicts (from FortiGate)
        """
        visited: set[str] = set()
        devices: list[dict] = []
        lldp_edges: list[dict] = []
        arp_entries: dict[str, list[dict]] = {}
        mac_entries: dict[str, list[dict]] = {}
        wireless_aps: list[dict] = []
        wireless_clients: list[dict] = []
        routes: list[dict] = []

        # BFS queue: (device_id, snmp_port)
        queue: list[tuple[str, int]] = [
            (seed_device_id, SNMP_PORTS[seed_device_id])
        ]

        while queue:
            device_id, port = queue.pop(0)
            if device_id in visited:
                continue
            visited.add(device_id)

            logger.info("Discovering device: %s (port %d)", device_id, port)

            # 1. Get system identity
            device_info = await self._get_device_info(device_id, port)
            if device_info is None:
                logger.warning("Could not reach device %s on port %d", device_id, port)
                continue
            devices.append(device_info)

            # 2. Walk LLDP neighbors and queue new devices
            neighbors = await self._walk_lldp_neighbors(port)
            for neighbor in neighbors:
                edge = {
                    "source": device_id,
                    "target_sys_name": neighbor["sys_name"],
                    "source_port": neighbor.get("local_port"),
                    "target_port": neighbor.get("remote_port"),
                }

                # Resolve neighbor to a device_id
                target_id = _resolve_device_id(neighbor["sys_name"])
                if target_id is not None:
                    edge["target"] = target_id
                    if target_id not in visited and target_id in SNMP_PORTS:
                        queue.append((target_id, SNMP_PORTS[target_id]))
                else:
                    logger.debug(
                        "Unresolved LLDP neighbor sysName=%r from %s (likely AP/endpoint)",
                        neighbor["sys_name"], device_id,
                    )
                # Always keep the edge — topology builder uses
                # target_sys_name to match APs from the wireless table
                lldp_edges.append(edge)

            # 3. Walk ARP table
            arp = await self._walk_arp_table(port)
            if arp:
                arp_entries[device_id] = arp

            # 4. Walk MAC forwarding table
            mac = await self._walk_mac_table(port)
            if mac:
                mac_entries[device_id] = mac

            # 5. On FortiGate primary, walk wireless tables and routes
            if device_id == "fg-primary":
                wireless_aps = await self._walk_ap_table(port)
                wireless_clients = await self._walk_sta_table(port)
                routes = await self._walk_route_table(port)

        return {
            "devices": devices,
            "lldp_edges": lldp_edges,
            "arp_entries": arp_entries,
            "mac_entries": mac_entries,
            "wireless_aps": wireless_aps,
            "wireless_clients": wireless_clients,
            "routes": routes,
        }

    # ------------------------------------------------------------------
    # Device identity
    # ------------------------------------------------------------------

    async def _get_device_info(self, device_id: str, port: int) -> Optional[dict]:
        """GET sysDescr.0 and sysName.0 to identify a device."""
        descr_result = await self.client.get(port, _OID_SYS_DESCR)
        name_result = await self.client.get(port, _OID_SYS_NAME)

        if descr_result is None and name_result is None:
            return None

        sys_descr = _extract_value(descr_result[1]) if descr_result else ""
        sys_name = _extract_value(name_result[1]) if name_result else ""

        return {
            "device_id": device_id,
            "sys_descr": sys_descr,
            "sys_name": sys_name,
            "ip": DEVICE_IPS.get(device_id, ""),
            "model": DEVICE_MODELS.get(device_id, ""),
            "type": DEVICE_TYPES.get(device_id, "unknown"),
            "floor": DEVICE_FLOORS.get(device_id),
            "snmp_port": port,
        }

    # ------------------------------------------------------------------
    # LLDP neighbor discovery
    # ------------------------------------------------------------------

    async def _walk_lldp_neighbors(self, port: int) -> list[dict]:
        """Walk the LLDP remote table and return a list of neighbor dicts.

        Each dict has: sys_name, chassis_id, remote_port, local_port
        (where local_port is derived from the OID index).
        """
        # Walk each LLDP column separately
        chassis_rows = await self.client.walk(port, _OID_LLDP_REM_CHASSIS_ID)
        port_rows = await self.client.walk(port, _OID_LLDP_REM_PORT_ID)
        name_rows = await self.client.walk(port, _OID_LLDP_REM_SYS_NAME)

        # Index by the OID suffix (timeMark.localPort.remIndex)
        def _suffix(oid_str: str, prefix: str) -> str:
            normalised = oid_str.lstrip(".")
            p = prefix.lstrip(".")
            if normalised.startswith(p + "."):
                return normalised[len(p) + 1:]
            return normalised

        chassis_map: dict[str, bytes] = {}
        for oid_str, val in chassis_rows:
            suffix = _suffix(oid_str, _OID_LLDP_REM_CHASSIS_ID)
            chassis_map[suffix] = _extract_raw_bytes(val)

        port_map: dict[str, str] = {}
        for oid_str, val in port_rows:
            suffix = _suffix(oid_str, _OID_LLDP_REM_PORT_ID)
            port_map[suffix] = _extract_value(val)

        name_map: dict[str, str] = {}
        for oid_str, val in name_rows:
            suffix = _suffix(oid_str, _OID_LLDP_REM_SYS_NAME)
            name_map[suffix] = _extract_value(val)

        # Combine into neighbor list
        neighbors: list[dict] = []
        for suffix in chassis_map:
            sys_name = name_map.get(suffix, "")
            remote_port = port_map.get(suffix, "")
            chassis_id = _bytes_to_mac(chassis_map[suffix])

            # Extract local port index from the suffix (format: timeMark.localPort.remIndex)
            parts = suffix.split(".")
            local_port_idx = parts[1] if len(parts) >= 2 else "0"

            neighbors.append({
                "sys_name": sys_name,
                "chassis_id": chassis_id,
                "remote_port": remote_port,
                "local_port": f"port{local_port_idx}",
            })

        return neighbors

    # ------------------------------------------------------------------
    # ARP table
    # ------------------------------------------------------------------

    async def _walk_arp_table(self, port: int) -> list[dict]:
        """Walk ipNetToMediaTable and return ARP entries.

        Each entry has: if_index, ip, mac.
        """
        phys_rows = await self.client.walk(port, _OID_ARP_PHYS_ADDR)
        net_rows = await self.client.walk(port, _OID_ARP_NET_ADDR)

        def _suffix(oid_str: str, prefix: str) -> str:
            normalised = oid_str.lstrip(".")
            p = prefix.lstrip(".")
            if normalised.startswith(p + "."):
                return normalised[len(p) + 1:]
            return normalised

        phys_map: dict[str, bytes] = {}
        for oid_str, val in phys_rows:
            suffix = _suffix(oid_str, _OID_ARP_PHYS_ADDR)
            phys_map[suffix] = _extract_raw_bytes(val)

        net_map: dict[str, str] = {}
        for oid_str, val in net_rows:
            suffix = _suffix(oid_str, _OID_ARP_NET_ADDR)
            # The netAddress value is an OctetString containing the IP as text
            # or as 4 raw bytes, depending on the agent.
            raw = _extract_raw_bytes(val)
            if len(raw) == 4:
                net_map[suffix] = _bytes_to_ip(raw)
            else:
                net_map[suffix] = _extract_value(val)

        entries: list[dict] = []
        for suffix in phys_map:
            # suffix format: ifIndex.ip1.ip2.ip3.ip4
            parts = suffix.split(".")
            if_index = int(parts[0]) if parts else 0
            ip = net_map.get(suffix, ".".join(parts[1:5]) if len(parts) >= 5 else "")
            mac = _bytes_to_mac(phys_map[suffix])
            entries.append({"if_index": if_index, "ip": ip, "mac": mac})

        return entries

    # ------------------------------------------------------------------
    # MAC forwarding table
    # ------------------------------------------------------------------

    async def _walk_mac_table(self, port: int) -> list[dict]:
        """Walk dot1dTpFdbTable and return MAC forwarding entries.

        Each entry has: mac, port, status.
        """
        addr_rows = await self.client.walk(port, _OID_FDB_ADDRESS)
        port_rows = await self.client.walk(port, _OID_FDB_PORT)
        status_rows = await self.client.walk(port, _OID_FDB_STATUS)

        def _suffix(oid_str: str, prefix: str) -> str:
            normalised = oid_str.lstrip(".")
            p = prefix.lstrip(".")
            if normalised.startswith(p + "."):
                return normalised[len(p) + 1:]
            return normalised

        addr_map: dict[str, bytes] = {}
        for oid_str, val in addr_rows:
            suffix = _suffix(oid_str, _OID_FDB_ADDRESS)
            addr_map[suffix] = _extract_raw_bytes(val)

        port_map: dict[str, int] = {}
        for oid_str, val in port_rows:
            suffix = _suffix(oid_str, _OID_FDB_PORT)
            port_map[suffix] = _extract_int(val)

        status_map: dict[str, int] = {}
        for oid_str, val in status_rows:
            suffix = _suffix(oid_str, _OID_FDB_STATUS)
            status_map[suffix] = _extract_int(val)

        entries: list[dict] = []
        for suffix in addr_map:
            mac = _bytes_to_mac(addr_map[suffix])
            bridge_port = port_map.get(suffix, 0)
            status = status_map.get(suffix, 0)
            entries.append({"mac": mac, "port": bridge_port, "status": status})

        return entries

    # ------------------------------------------------------------------
    # FortiGate wireless AP table
    # ------------------------------------------------------------------

    async def _walk_ap_table(self, port: int) -> list[dict]:
        """Walk fgWcApTable and return AP dicts.

        Each dict has: index, serial, name, ip, status, client_count.
        """
        all_rows = await self.client.walk(port, _OID_FG_AP_TABLE)
        if not all_rows:
            return []

        # Group by row index (the last component of the OID suffix)
        # OID structure: prefix.column.rowIndex
        rows_by_index: dict[int, dict] = {}

        prefix_len = len(_OID_FG_AP_TABLE.split("."))
        for oid_str, val in all_rows:
            parts = oid_str.lstrip(".").split(".")
            if len(parts) <= prefix_len + 1:
                continue
            column = parts[prefix_len]
            row_index = int(parts[prefix_len + 1])

            if row_index not in rows_by_index:
                rows_by_index[row_index] = {"index": row_index}

            raw = _extract_raw_bytes(val)
            if column == _FG_AP_SERIAL:
                rows_by_index[row_index]["serial"] = _extract_value(val)
            elif column == _FG_AP_NAME:
                rows_by_index[row_index]["name"] = _extract_value(val)
            elif column == _FG_AP_IP:
                rows_by_index[row_index]["ip"] = _bytes_to_ip(raw) if len(raw) == 4 else _extract_value(val)
            elif column == _FG_AP_STATUS:
                rows_by_index[row_index]["status"] = _extract_int(val)
            elif column == _FG_AP_STA_COUNT:
                rows_by_index[row_index]["client_count"] = _extract_int(val)

        return sorted(rows_by_index.values(), key=lambda r: r.get("index", 0))

    # ------------------------------------------------------------------
    # FortiGate wireless station table
    # ------------------------------------------------------------------

    async def _walk_sta_table(self, port: int) -> list[dict]:
        """Walk fgWcStaTable and return wireless client dicts.

        Each dict has: index, mac, ip, ssid, ap_name, vlan.
        """
        all_rows = await self.client.walk(port, _OID_FG_STA_TABLE)
        if not all_rows:
            return []

        rows_by_index: dict[int, dict] = {}
        prefix_len = len(_OID_FG_STA_TABLE.split("."))

        for oid_str, val in all_rows:
            parts = oid_str.lstrip(".").split(".")
            if len(parts) <= prefix_len + 1:
                continue
            column = parts[prefix_len]
            row_index = int(parts[prefix_len + 1])

            if row_index not in rows_by_index:
                rows_by_index[row_index] = {"index": row_index}

            raw = _extract_raw_bytes(val)
            if column == _FG_STA_MAC:
                rows_by_index[row_index]["mac"] = _bytes_to_mac(raw) if len(raw) == 6 else _extract_value(val)
            elif column == _FG_STA_IP:
                rows_by_index[row_index]["ip"] = _bytes_to_ip(raw) if len(raw) == 4 else _extract_value(val)
            elif column == _FG_STA_SSID:
                rows_by_index[row_index]["ssid"] = _extract_value(val)
            elif column == _FG_STA_AP_NAME:
                rows_by_index[row_index]["ap_name"] = _extract_value(val)
            elif column == _FG_STA_VLAN:
                rows_by_index[row_index]["vlan"] = _extract_int(val)

        return sorted(rows_by_index.values(), key=lambda r: r.get("index", 0))

    # ------------------------------------------------------------------
    # IP route table (FortiGate)
    # ------------------------------------------------------------------

    async def _walk_route_table(self, port: int) -> list[dict]:
        """Walk ipRouteTable and return route dicts.

        Each dict has: dest, mask, next_hop, if_index, type.
        """
        all_rows = await self.client.walk(port, _OID_IP_ROUTE_TABLE)
        if not all_rows:
            return []

        # Columns: 1=dest, 2=ifIndex, 7=nextHop, 8=type, 11=mask
        rows_by_dest: dict[str, dict] = {}
        prefix_len = len(_OID_IP_ROUTE_TABLE.split("."))

        for oid_str, val in all_rows:
            parts = oid_str.lstrip(".").split(".")
            if len(parts) < prefix_len + 5:
                continue
            column = parts[prefix_len]
            dest_suffix = ".".join(parts[prefix_len + 1: prefix_len + 5])

            if dest_suffix not in rows_by_dest:
                rows_by_dest[dest_suffix] = {}

            if column == "1":  # ipRouteDest
                raw = _extract_raw_bytes(val)
                rows_by_dest[dest_suffix]["dest"] = _bytes_to_ip(raw) if len(raw) == 4 else _extract_value(val)
            elif column == "2":  # ipRouteIfIndex
                rows_by_dest[dest_suffix]["if_index"] = _extract_int(val)
            elif column == "7":  # ipRouteNextHop
                raw = _extract_raw_bytes(val)
                rows_by_dest[dest_suffix]["next_hop"] = _bytes_to_ip(raw) if len(raw) == 4 else _extract_value(val)
            elif column == "8":  # ipRouteType
                rows_by_dest[dest_suffix]["type"] = _extract_int(val)
            elif column == "11":  # ipRouteMask
                raw = _extract_raw_bytes(val)
                rows_by_dest[dest_suffix]["mask"] = _bytes_to_ip(raw) if len(raw) == 4 else _extract_value(val)

        return list(rows_by_dest.values())
