"""Endpoint and wireless client population for the SNMP simulator.

Generates all ~1,200 wired endpoints, 56 access points, and ~940 wireless
clients and registers them in the :class:`TopologyState`.  Called once at
startup from :func:`simulator.main.init_topology_state`.
"""

from __future__ import annotations

import random

from simulator.constants import (
    APS_PER_FLOOR,
    AP_BASE_IP,
    AP_IP_START,
    ENDPOINT_COUNTS,
    TOTAL_FLOORS,
)
from simulator.devices.base import generate_mac
from simulator.topology_state import (
    APInfo,
    ARPEntry,
    MACEntry,
    TopologyState,
    WirelessClient,
)

# ---------------------------------------------------------------------------
# VLAN-to-port-range mapping (per floor switch, matching floor_switch.py)
# ---------------------------------------------------------------------------

_PORT_RANGES = {
    10: (15, 20),   # POS / Payment: ports 15-20 (6 ports)
    20: (21, 23),   # Operations PCs: ports 21-23 (3 ports)
    40: (24, 35),   # IP Cameras: ports 24-35 (12 ports)
    50: (36, 48),   # IoT devices: ports 36-48 (13 ports)
}

# Per-floor endpoint targets (derived from total counts / 4 floors)
_PER_FLOOR = {
    10: ENDPOINT_COUNTS[10] // TOTAL_FLOORS,   # 10 POS per floor
    20: ENDPOINT_COUNTS[20] // TOTAL_FLOORS,   # 3 ops PCs per floor
    40: -1,  # placeholder -- computed below with rounding
    50: -1,  # placeholder
}

# Handle uneven division for cameras and IoT
_CAMERAS_TOTAL = ENDPOINT_COUNTS[40]   # 50
_IOT_TOTAL = ENDPOINT_COUNTS[50]       # 110

# PoE power draw per device category (watts)
_POE_WATTS = {
    10: 10.0,   # POS terminals
    20: 0.0,    # Ops PCs (not PoE-powered)
    40: 15.0,   # IP cameras
    50: 5.0,    # IoT sensors / signage
}

# Category labels used in MAC seed strings
_CATEGORY_LABELS = {
    10: "pos",
    20: "opspc",
    40: "camera",
    50: "iot",
}


# ---------------------------------------------------------------------------
# Wired endpoints
# ---------------------------------------------------------------------------

def populate_wired_endpoints(state: TopologyState) -> None:
    """Add all wired endpoints to floor switch ARP/MAC tables and PoE ports.

    Distributes endpoints across 4 floor switches according to the VLAN
    port ranges and total endpoint counts defined in ``constants.py``.
    """
    for floor in range(1, TOTAL_FLOORS + 1):
        device_id = f"floor-sw-{floor}"
        device = state.get_device(device_id)
        if device is None:
            continue

        for vlan, (port_start, port_end) in _PORT_RANGES.items():
            # Determine how many endpoints this floor gets for this VLAN
            count = _per_floor_count(vlan, floor)
            port_count = port_end - port_start + 1
            category = _CATEGORY_LABELS[vlan]

            for i in range(count):
                # Distribute endpoints across available ports (wrap around)
                port_num = port_start + (i % port_count)
                port_name = f"port{port_num}"

                # Deterministic MAC and IP
                global_index = (floor - 1) * count + i
                mac = generate_mac(f"{category}-{floor}-{i}", global_index)
                ip = _ip_for_vlan(vlan, floor, i)

                device.arp_table.append(ARPEntry(
                    ip=ip,
                    mac=mac,
                    vlan=vlan,
                    port=port_name,
                ))
                device.mac_table.append(MACEntry(
                    mac=mac,
                    vlan=vlan,
                    port=port_name,
                ))

                # Set PoE wattage for the port (may overwrite if multiple
                # endpoints share a port -- that is fine, keeps the last value)
                watts = _POE_WATTS[vlan]
                if watts > 0:
                    device.poe_ports[port_name] = watts


def _per_floor_count(vlan: int, floor: int) -> int:
    """Return the number of endpoints for *vlan* on *floor*.

    For VLANs whose total is not evenly divisible by 4, the remainder
    endpoints are distributed to the first floors.
    """
    total = ENDPOINT_COUNTS[vlan]
    base = total // TOTAL_FLOORS
    remainder = total % TOTAL_FLOORS
    return base + (1 if floor <= remainder else 0)


def _ip_for_vlan(vlan: int, floor: int, index: int) -> str:
    """Return an IP address for endpoint *index* on *floor* in *vlan*."""
    # Compute a global sequential index across all floors
    per_floor_before = sum(
        _per_floor_count(vlan, f) for f in range(1, floor)
    )
    seq = per_floor_before + index

    if vlan == 10:
        return f"10.10.10.{11 + seq}"
    elif vlan == 20:
        return f"10.10.20.{11 + seq}"
    elif vlan == 40:
        return f"10.10.40.{11 + seq}"
    elif vlan == 50:
        # /23 subnet -> 10.10.50.0 - 10.10.51.255
        host = 11 + seq
        third_octet = 50 + (host >> 8)
        fourth_octet = host & 0xFF
        return f"10.10.{third_octet}.{fourth_octet}"
    else:
        return f"10.10.{vlan}.{11 + seq}"


# ---------------------------------------------------------------------------
# Access points
# ---------------------------------------------------------------------------

def populate_access_points(state: TopologyState) -> None:
    """Register all 56 APs in the topology state as APInfo objects.

    APs are already present in floor switch LLDP tables (set up in
    ``init_topology_state``).  This function creates the corresponding
    :class:`APInfo` records so the FortiGate wireless controller tables
    and wireless client distribution can reference them.
    """
    for floor in range(1, TOTAL_FLOORS + 1):
        for idx in range(1, APS_PER_FLOOR + 1):
            global_idx = (floor - 1) * APS_PER_FLOOR + idx
            ap = APInfo(
                ap_id=f"ap-{floor}-{idx:02d}",
                name=f"FortiAP-{global_idx}",
                serial=f"FAP431K{global_idx:04d}",
                ip=f"{AP_BASE_IP}.{AP_IP_START + (floor - 1) * APS_PER_FLOOR + idx - 1}",
                status="up",
                floor=floor,
                parent_switch=f"floor-sw-{floor}",
                parent_port=f"port{idx}",
            )
            state.add_ap(ap)


# ---------------------------------------------------------------------------
# Wireless clients
# ---------------------------------------------------------------------------

def populate_wireless_clients(state: TopologyState) -> None:
    """Create and add all wireless clients (employees + guests).

    Employees (VLAN 30):
        90 total, distributed evenly across all 56 APs.

    Guests (VLAN 60):
        ~850 total, distributed across all 56 APs (~15 per AP).
    """
    # Use a fixed seed so results are reproducible across runs
    rng = random.Random(42)

    all_aps = state.get_all_aps()
    if not all_aps:
        return

    total_aps = len(all_aps)

    # --- Employee handhelds (VLAN 30) ---
    employee_count = ENDPOINT_COUNTS[30]  # 90
    for i in range(employee_count):
        ap = all_aps[i % total_aps]
        mac = generate_mac(f"employee-{i}", i)
        ip = f"10.10.30.{i + 1}"
        rssi = rng.randint(-65, -45)

        state.add_wireless_client(WirelessClient(
            mac=mac,
            ip=ip,
            ssid="Corp-WiFi",
            vlan=30,
            ap_id=ap.ap_id,
            rssi=rssi,
            device_type="employee",
        ))

    # --- Guest devices (VLAN 60) ---
    guest_count = ENDPOINT_COUNTS[60]  # 850
    for i in range(guest_count):
        ap = all_aps[i % total_aps]
        mac = generate_mac(f"guest-{i}", i)
        # Guest IP: spread across 172.16.0.0/20 (172.16.0.1 - 172.16.15.254)
        # Offset by 1 to avoid .0 host addresses
        host_num = i + 1
        third_octet = (host_num >> 8) & 0xF
        fourth_octet = host_num & 0xFF
        if fourth_octet == 0:
            # Skip .0 addresses by bumping into next /24
            third_octet += 1
            fourth_octet = 1
        ip = f"172.16.{third_octet}.{fourth_octet}"
        rssi = rng.randint(-75, -50)

        state.add_wireless_client(WirelessClient(
            mac=mac,
            ip=ip,
            ssid="Guest-WiFi",
            vlan=60,
            ap_id=ap.ap_id,
            rssi=rssi,
            device_type="guest",
        ))
