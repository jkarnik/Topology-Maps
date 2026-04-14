"""In-memory topology state for the SNMP simulator.

This is the central state store that the simulator uses to generate
SNMP responses. When a connection edit comes in, this state is updated
and the SNMP agents read from it on the next query.
"""

from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLDPNeighbor:
    """An LLDP neighbor entry."""
    local_port: str
    remote_device_id: str
    remote_port: str
    remote_device_name: str
    remote_ip: str


@dataclass
class ARPEntry:
    """An ARP table entry (IP-to-MAC mapping)."""
    ip: str
    mac: str
    vlan: int
    port: str


@dataclass
class MACEntry:
    """A MAC forwarding table entry."""
    mac: str
    vlan: int
    port: str


@dataclass
class WirelessClient:
    """A wireless client connected to an AP."""
    mac: str
    ip: str
    ssid: str
    vlan: int
    ap_id: str
    rssi: int  # dBm, typically -30 to -90
    device_type: str  # "employee" or "guest"


@dataclass
class APInfo:
    """A managed access point."""
    ap_id: str
    name: str
    serial: str
    ip: str
    status: str  # "up" or "down"
    floor: int
    parent_switch: str
    parent_port: str
    client_count: int = 0


@dataclass
class DeviceState:
    """Complete state for a single device."""
    device_id: str
    device_type: str  # "firewall", "core_switch", "floor_switch"
    model: str
    ip: str
    snmp_port: int
    floor: Optional[int] = None
    lldp_neighbors: list[LLDPNeighbor] = field(default_factory=list)
    arp_table: list[ARPEntry] = field(default_factory=list)
    mac_table: list[MACEntry] = field(default_factory=list)
    interfaces: list[dict] = field(default_factory=list)
    vlan_ports: dict[int, list[str]] = field(default_factory=dict)
    poe_ports: dict[str, float] = field(default_factory=dict)  # port -> watts


class TopologyState:
    """Thread-safe in-memory topology state.

    All SNMP agents read from this state. The simulator REST API
    and roaming simulator write to it.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.devices: dict[str, DeviceState] = {}
        self.aps: dict[str, APInfo] = {}
        self.wireless_clients: list[WirelessClient] = []
        self._version: int = 0  # Incremented on every mutation

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def add_device(self, device: DeviceState) -> None:
        """Add or replace a device in the state."""
        with self._lock:
            self.devices[device.device_id] = device
            self._version += 1

    def get_device(self, device_id: str) -> Optional[DeviceState]:
        """Get a device by ID."""
        with self._lock:
            return self.devices.get(device_id)

    def add_ap(self, ap: APInfo) -> None:
        """Register an access point."""
        with self._lock:
            self.aps[ap.ap_id] = ap
            self._version += 1

    def get_ap(self, ap_id: str) -> Optional[APInfo]:
        """Get AP info by ID."""
        with self._lock:
            return self.aps.get(ap_id)

    def get_aps_on_floor(self, floor: int) -> list[APInfo]:
        """Get all APs on a given floor."""
        with self._lock:
            return [ap for ap in self.aps.values() if ap.floor == floor]

    def add_wireless_client(self, client: WirelessClient) -> None:
        """Add a wireless client."""
        with self._lock:
            self.wireless_clients.append(client)
            # Update AP client count
            if client.ap_id in self.aps:
                self.aps[client.ap_id].client_count += 1
            self._version += 1

    def get_clients_for_ap(self, ap_id: str) -> list[WirelessClient]:
        """Get all wireless clients connected to a specific AP."""
        with self._lock:
            return [c for c in self.wireless_clients if c.ap_id == ap_id]

    def move_wireless_client(self, client_mac: str, new_ap_id: str, new_rssi: int) -> bool:
        """Move a wireless client to a different AP. Returns True if successful."""
        with self._lock:
            for client in self.wireless_clients:
                if client.mac == mac_match(client.mac, client_mac):
                    old_ap_id = client.ap_id
                    if old_ap_id == new_ap_id:
                        return False
                    # Update old AP count
                    if old_ap_id in self.aps:
                        self.aps[old_ap_id].client_count = max(0, self.aps[old_ap_id].client_count - 1)
                    # Update client
                    client.ap_id = new_ap_id
                    client.rssi = new_rssi
                    # Update new AP count
                    if new_ap_id in self.aps:
                        self.aps[new_ap_id].client_count += 1
                    self._version += 1
                    return True
            return False

    def move_connection(
        self,
        device_id: str,
        from_switch: str,
        from_port: int,
        to_switch: str,
        to_port: int,
    ) -> bool:
        """Move a device's physical connection from one switch/port to another.

        Updates LLDP tables on the affected switches and the device.
        Returns True if successful.
        """
        with self._lock:
            # Find and remove from source switch LLDP table
            src_switch = self.devices.get(from_switch)
            dst_switch = self.devices.get(to_switch)
            device = None

            # Find the device — it could be an AP or endpoint
            if device_id in self.aps:
                ap = self.aps[device_id]
                device_name = ap.name
                device_ip = ap.ip
            else:
                # Check if it's a device
                dev = self.devices.get(device_id)
                if dev:
                    device_name = device_id
                    device_ip = dev.ip
                else:
                    return False

            if not src_switch or not dst_switch:
                return False

            # Remove from source switch LLDP
            src_port_name = f"port{from_port}"
            src_switch.lldp_neighbors = [
                n for n in src_switch.lldp_neighbors
                if not (n.local_port == src_port_name and n.remote_device_id == device_id)
            ]

            # Add to destination switch LLDP
            dst_port_name = f"port{to_port}"
            dst_switch.lldp_neighbors.append(
                LLDPNeighbor(
                    local_port=dst_port_name,
                    remote_device_id=device_id,
                    remote_port="eth0",
                    remote_device_name=device_name,
                    remote_ip=device_ip,
                )
            )

            # Update AP parent if applicable
            if device_id in self.aps:
                self.aps[device_id].parent_switch = to_switch
                self.aps[device_id].parent_port = dst_port_name

            # Move ARP/MAC entries
            for entry in src_switch.arp_table[:]:
                if entry.port == src_port_name:
                    src_switch.arp_table.remove(entry)
                    entry.port = dst_port_name
                    dst_switch.arp_table.append(entry)

            for entry in src_switch.mac_table[:]:
                if entry.port == src_port_name:
                    src_switch.mac_table.remove(entry)
                    entry.port = dst_port_name
                    dst_switch.mac_table.append(entry)

            self._version += 1
            return True

    def get_all_wireless_clients(self) -> list[WirelessClient]:
        """Get all wireless clients."""
        with self._lock:
            return list(self.wireless_clients)

    def get_all_aps(self) -> list[APInfo]:
        """Get all APs."""
        with self._lock:
            return list(self.aps.values())


def mac_match(mac1: str, mac2: str) -> str:
    """Normalize and compare MAC addresses. Returns mac1 if they match."""
    if mac1.lower().replace("-", ":") == mac2.lower().replace("-", ":"):
        return mac1
    return ""
