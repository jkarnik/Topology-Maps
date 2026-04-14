"""Builds L2 and L3 topology graphs from discovery data.

Transforms the raw discovery output (device info, LLDP edges, ARP/MAC
tables, wireless AP/station tables) into the Pydantic models that the
API serves: :class:`L2Topology` (physical graph) and :class:`L3Topology`
(logical / subnet graph).
"""

from __future__ import annotations

import ipaddress
import logging
from typing import Optional

from server.models import (
    Device,
    DeviceStatus,
    DeviceType,
    Edge,
    EndpointCategory,
    L2Topology,
    L3Topology,
    LinkProtocol,
    Route,
    RoutingPolicy,
    Subnet,
)
from simulator.constants import (
    AP_BASE_IP,
    AP_IP_START,
    APS_PER_FLOOR,
    DEVICE_FLOORS,
    DEVICE_IPS,
    DEVICE_TYPES,
    ROUTING_POLICIES,
    VLANS,
    WIRED_VLANS,
    WIRELESS_VLANS,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VLAN_CATEGORY_MAP: dict[int, EndpointCategory] = {
    10: EndpointCategory.PAYMENT,
    20: EndpointCategory.OPERATIONS,
    30: EndpointCategory.EMPLOYEE,
    40: EndpointCategory.SECURITY,
    50: EndpointCategory.IOT,
    60: EndpointCategory.GUEST,
}


def _device_type_enum(type_str: str) -> DeviceType:
    """Convert a device type string to a DeviceType enum value."""
    mapping = {
        "firewall": DeviceType.FIREWALL,
        "core_switch": DeviceType.CORE_SWITCH,
        "floor_switch": DeviceType.FLOOR_SWITCH,
        "access_point": DeviceType.ACCESS_POINT,
        "endpoint": DeviceType.ENDPOINT,
    }
    return mapping.get(type_str, DeviceType.ENDPOINT)


def _ip_in_vlan(ip: str) -> Optional[int]:
    """Determine which VLAN an IP address belongs to, or None."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return None
    for vlan_id, info in VLANS.items():
        try:
            net = ipaddress.ip_network(info["cidr"], strict=False)
            if addr in net:
                return vlan_id
        except ValueError:
            continue
    return None


def _ap_floor_from_ip(ip: str) -> Optional[int]:
    """Determine which floor an AP is on based on its IP address."""
    try:
        last_octet = int(ip.split(".")[-1])
    except (ValueError, IndexError):
        return None
    if last_octet < AP_IP_START:
        return None
    offset = last_octet - AP_IP_START
    floor = (offset // APS_PER_FLOOR) + 1
    if 1 <= floor <= 4:
        return floor
    return None


def _ap_device_id_from_name(ap_name: str) -> str:
    """Derive a device ID from an AP name like 'FortiAP-15'.

    Converts global AP index to floor/local-index form: ``ap-{floor}-{idx:02d}``.
    E.g. FortiAP-15 -> floor 2, local index 1 -> ``ap-2-01``.
    """
    try:
        global_idx = int(ap_name.split("-")[-1])
        floor = (global_idx - 1) // APS_PER_FLOOR + 1
        local_idx = (global_idx - 1) % APS_PER_FLOOR + 1
        return f"ap-{floor}-{local_idx:02d}"
    except (ValueError, IndexError):
        return ap_name.lower()


def _subnet_gateway(cidr: str) -> str:
    """Return the .1 address in a CIDR block as the gateway."""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        return str(net.network_address + 1)
    except ValueError:
        return ""


# ---------------------------------------------------------------------------
# TopologyBuilder
# ---------------------------------------------------------------------------

class TopologyBuilder:
    """Constructs L2 and L3 topology models from raw discovery data."""

    def build_l2(self, discovery_data: dict) -> L2Topology:
        """Build L2 physical topology from discovery data.

        Creates Device nodes for infrastructure, APs, and endpoints,
        and Edge connections from LLDP, ARP/MAC, and wireless data.
        """
        nodes: list[Device] = []
        edges: list[Edge] = []
        seen_node_ids: set[str] = set()
        seen_edge_ids: set[str] = set()

        # --- 1. Infrastructure devices (from SNMP discovery) ---
        for dev in discovery_data.get("devices", []):
            device_id = dev["device_id"]
            if device_id in seen_node_ids:
                continue
            seen_node_ids.add(device_id)

            nodes.append(Device(
                id=device_id,
                type=_device_type_enum(dev.get("type", "unknown")),
                model=dev.get("model", ""),
                ip=dev.get("ip", ""),
                status=DeviceStatus.UP,
                floor=dev.get("floor"),
            ))

        # --- 2. Access Points (from FortiGate wireless table) ---
        ap_name_to_id: dict[str, str] = {}
        for ap in discovery_data.get("wireless_aps", []):
            ap_name = ap.get("name", "")
            ap_id = _ap_device_id_from_name(ap_name)
            ap_name_to_id[ap_name] = ap_id

            if ap_id in seen_node_ids:
                continue
            seen_node_ids.add(ap_id)

            ap_ip = ap.get("ip", "")
            ap_floor = _ap_floor_from_ip(ap_ip)
            ap_status = DeviceStatus.UP if ap.get("status") == 1 else DeviceStatus.DOWN

            nodes.append(Device(
                id=ap_id,
                type=DeviceType.ACCESS_POINT,
                model="FortiAP 231G",
                ip=ap_ip,
                status=ap_status,
                floor=ap_floor,
            ))

        # --- 3. LLDP edges (infrastructure links) ---
        for edge_data in discovery_data.get("lldp_edges", []):
            source = edge_data["source"]
            target = edge_data.get("target", "")
            if not target:
                continue

            edge_id = f"{source}-{target}"
            reverse_id = f"{target}-{source}"
            if edge_id in seen_edge_ids or reverse_id in seen_edge_ids:
                continue
            seen_edge_ids.add(edge_id)

            # Determine link speed based on the devices involved
            speed = "1G"
            src_type = DEVICE_TYPES.get(source, "")
            tgt_type = DEVICE_TYPES.get(target, "")
            if "firewall" in (src_type, tgt_type) and "core_switch" in (src_type, tgt_type):
                speed = "10G"

            edges.append(Edge(
                id=edge_id,
                source=source,
                target=target,
                source_port=edge_data.get("source_port"),
                target_port=edge_data.get("target_port"),
                speed=speed,
                protocol=LinkProtocol.LLDP,
            ))

        # --- 4. AP-to-switch edges (from LLDP on floor switches) ---
        # Floor switches report APs as LLDP neighbors. We use the
        # lldp_edges that point from a floor switch to an AP sysName.
        # These were already collected as LLDP edges with the floor
        # switch as source; we need to match the AP sysName to our AP IDs.
        for edge_data in discovery_data.get("lldp_edges", []):
            source = edge_data["source"]
            target = edge_data.get("target", "")
            target_sys_name = edge_data.get("target_sys_name", "")

            # Check if the target is an AP (not in SNMP_PORTS, i.e. not infra)
            if target and target not in DEVICE_IPS:
                # This target was already resolved to an AP id or is unknown
                pass

            # Check if the target_sys_name matches an AP
            ap_id = ap_name_to_id.get(target_sys_name)
            if ap_id and DEVICE_TYPES.get(source) in ("floor_switch",):
                edge_id = f"{source}-{ap_id}"
                reverse_id = f"{ap_id}-{source}"
                if edge_id not in seen_edge_ids and reverse_id not in seen_edge_ids:
                    seen_edge_ids.add(edge_id)
                    edges.append(Edge(
                        id=edge_id,
                        source=source,
                        target=ap_id,
                        source_port=edge_data.get("source_port"),
                        target_port=edge_data.get("target_port"),
                        speed="1G",
                        protocol=LinkProtocol.LLDP,
                    ))

        # --- 5. Wired endpoints (from ARP/MAC on floor switches) ---
        for device_id, arp_list in discovery_data.get("arp_entries", {}).items():
            if DEVICE_TYPES.get(device_id) not in ("floor_switch",):
                continue

            floor = DEVICE_FLOORS.get(device_id)
            mac_list = discovery_data.get("mac_entries", {}).get(device_id, [])
            mac_to_port: dict[str, int] = {
                m["mac"]: m["port"] for m in mac_list if m.get("port")
            }

            for arp_entry in arp_list:
                ep_ip = arp_entry.get("ip", "")
                ep_mac = arp_entry.get("mac", "")
                if_index = arp_entry.get("if_index", 0)

                # Skip AP IPs (they are already nodes from the wireless table)
                vlan = _ip_in_vlan(ep_ip)
                if vlan in WIRELESS_VLANS:
                    continue

                # Skip infrastructure device IPs
                if ep_ip in DEVICE_IPS.values():
                    continue
                # Skip AP IPs in the management range
                if ep_ip.startswith(f"{AP_BASE_IP}."):
                    try:
                        last_octet = int(ep_ip.split(".")[-1])
                        if AP_IP_START <= last_octet <= AP_IP_START + APS_PER_FLOOR * 4:
                            continue
                    except ValueError:
                        pass

                ep_id = f"ep-{ep_mac.replace(':', '')}"
                if ep_id in seen_node_ids:
                    continue
                seen_node_ids.add(ep_id)

                category = _VLAN_CATEGORY_MAP.get(vlan) if vlan else None

                nodes.append(Device(
                    id=ep_id,
                    type=DeviceType.ENDPOINT,
                    model="",
                    ip=ep_ip,
                    status=DeviceStatus.UP,
                    floor=floor,
                    category=category,
                    mac=ep_mac,
                    vlan=vlan,
                ))

                # Edge: switch -> endpoint (via ARP)
                bridge_port = mac_to_port.get(ep_mac, if_index)
                edge_id = f"{device_id}-{ep_id}"
                if edge_id not in seen_edge_ids:
                    seen_edge_ids.add(edge_id)
                    edges.append(Edge(
                        id=edge_id,
                        source=device_id,
                        target=ep_id,
                        source_port=f"port{bridge_port}" if bridge_port else None,
                        speed="1G",
                        protocol=LinkProtocol.ARP,
                    ))

        # --- 6. Wireless clients (from FortiGate STA table) ---
        for client in discovery_data.get("wireless_clients", []):
            cl_mac = client.get("mac", "")
            cl_ip = client.get("ip", "")
            cl_ssid = client.get("ssid", "")
            cl_ap_name = client.get("ap_name", "")
            cl_vlan = client.get("vlan")

            cl_id = f"wl-{cl_mac.replace(':', '')}"
            if cl_id in seen_node_ids:
                continue
            seen_node_ids.add(cl_id)

            category = _VLAN_CATEGORY_MAP.get(cl_vlan) if cl_vlan else None
            ap_id = ap_name_to_id.get(cl_ap_name, "")
            ap_floor = _ap_floor_from_ip(
                next(
                    (a.get("ip", "") for a in discovery_data.get("wireless_aps", [])
                     if a.get("name") == cl_ap_name),
                    "",
                )
            )

            nodes.append(Device(
                id=cl_id,
                type=DeviceType.ENDPOINT,
                model="",
                ip=cl_ip,
                status=DeviceStatus.UP,
                floor=ap_floor,
                category=category,
                mac=cl_mac,
                vlan=cl_vlan,
                connected_ap=ap_id or None,
                ssid=cl_ssid or None,
            ))

            # Edge: AP -> wireless client
            if ap_id:
                edge_id = f"{ap_id}-{cl_id}"
                if edge_id not in seen_edge_ids:
                    seen_edge_ids.add(edge_id)
                    edges.append(Edge(
                        id=edge_id,
                        source=ap_id,
                        target=cl_id,
                        speed="WiFi6",
                        protocol=LinkProtocol.WIRELESS,
                    ))

        return L2Topology(nodes=nodes, edges=edges)

    def build_l3(self, discovery_data: dict) -> L3Topology:
        """Build L3 logical topology from discovery data.

        Creates Subnet entries from the VLAN configuration (enriched with
        device counts from discovery), and Route entries from the FortiGate's
        route table plus inter-VLAN routing policies.
        """
        subnets: list[Subnet] = []
        routes: list[Route] = []

        # --- 1. Subnets from VLAN config ---
        # Count devices per VLAN from discovery data
        vlan_device_counts: dict[int, int] = {}

        # Count wired endpoints per VLAN (from ARP entries on floor switches)
        for device_id, arp_list in discovery_data.get("arp_entries", {}).items():
            if DEVICE_TYPES.get(device_id) not in ("floor_switch",):
                continue
            for arp_entry in arp_list:
                ep_ip = arp_entry.get("ip", "")
                vlan = _ip_in_vlan(ep_ip)
                if vlan and vlan in WIRED_VLANS:
                    vlan_device_counts[vlan] = vlan_device_counts.get(vlan, 0) + 1

        # Count wireless clients per VLAN
        for client in discovery_data.get("wireless_clients", []):
            cl_vlan = client.get("vlan")
            if cl_vlan and cl_vlan in WIRELESS_VLANS:
                vlan_device_counts[cl_vlan] = vlan_device_counts.get(cl_vlan, 0) + 1

        for vlan_id, vlan_info in sorted(VLANS.items()):
            cidr = vlan_info["cidr"]
            gateway = _subnet_gateway(cidr)
            subnet_id = f"vlan{vlan_id}"

            subnets.append(Subnet(
                id=subnet_id,
                name=vlan_info["name"],
                vlan=vlan_id,
                cidr=cidr,
                gateway=gateway,
                device_count=vlan_device_counts.get(vlan_id, 0),
            ))

        # --- 2. Routes from FortiGate route table ---
        for route_data in discovery_data.get("routes", []):
            dest = route_data.get("dest", "")
            mask = route_data.get("mask", "")
            next_hop = route_data.get("next_hop", "")

            if not dest:
                continue

            # Determine which subnet this route connects to
            # Default route (0.0.0.0/0) goes to "internet"
            if dest == "0.0.0.0" and mask == "0.0.0.0":
                routes.append(Route(
                    from_subnet="fg-primary",
                    to_subnet="internet",
                    via="fg-primary",
                    policy=RoutingPolicy.ALLOW,
                ))
                continue

            # Connected routes map VLAN subnets to the FortiGate
            matched_vlan = None
            for vlan_id, vlan_info in VLANS.items():
                try:
                    vlan_net = ipaddress.ip_network(vlan_info["cidr"], strict=False)
                    route_net = ipaddress.ip_network(f"{dest}/{mask}", strict=False)
                    if vlan_net == route_net:
                        matched_vlan = vlan_id
                        break
                except ValueError:
                    continue

            if matched_vlan is not None:
                routes.append(Route(
                    from_subnet=f"vlan{matched_vlan}",
                    to_subnet="fg-primary",
                    via="fg-primary",
                    policy=RoutingPolicy.ALLOW,
                ))

        # --- 3. Inter-VLAN routing policies from constants ---
        for policy in ROUTING_POLICIES:
            from_vlan = policy["from_vlan"]
            to_vlan = policy["to_vlan"]
            action = policy["policy"]

            from_subnet = f"vlan{from_vlan}"
            to_subnet = str(to_vlan) if to_vlan == "internet" else f"vlan{to_vlan}"

            routes.append(Route(
                from_subnet=from_subnet,
                to_subnet=to_subnet,
                via="fg-primary",
                policy=RoutingPolicy.ALLOW if action == "allow" else RoutingPolicy.DENY,
            ))

        return L3Topology(subnets=subnets, routes=routes)
