"""Transform Meraki Dashboard API responses into internal topology models."""

from __future__ import annotations

from typing import Optional

from server.models import (
    Device,
    DeviceStatus,
    DeviceType,
    Edge,
    L2Topology,
    L3Topology,
    LinkProtocol,
    Route,
    RoutingPolicy,
    Subnet,
)

# Meraki productType → DeviceType
DEVICE_TYPE_MAP: dict[str, DeviceType] = {
    "appliance": DeviceType.FIREWALL,
    "switch": DeviceType.FLOOR_SWITCH,
    "wireless": DeviceType.ACCESS_POINT,
}

# Meraki device status string → DeviceStatus
STATUS_MAP: dict[str, DeviceStatus] = {
    "online": DeviceStatus.UP,
    "offline": DeviceStatus.DOWN,
    "alerting": DeviceStatus.ALERTING,
    "dormant": DeviceStatus.DOWN,
}


class MerakiTransformer:
    """Convert Meraki API payloads to L2/L3 topology models."""

    # ------------------------------------------------------------------
    # L2
    # ------------------------------------------------------------------

    def build_l2(
        self,
        devices: list[dict],
        device_statuses: list[dict],
        link_layer_data: list[dict],
    ) -> L2Topology:
        """Build an L2 topology from Meraki device and link-layer data.

        Args:
            devices: List of device objects from GET /organizations/{id}/devices.
            device_statuses: List of status objects from
                GET /organizations/{id}/devices/statuses.
            link_layer_data: List of link-layer topology objects from
                GET /networks/{id}/topology/linkLayer, one per network.

        Returns:
            L2Topology with nodes and edges populated.
        """
        # Index statuses by serial for O(1) lookup
        status_by_serial: dict[str, str] = {
            s["serial"]: s.get("status", "offline")
            for s in device_statuses
            if "serial" in s
        }

        nodes: list[Device] = []
        for dev in devices:
            serial = dev.get("serial", "")
            if not serial:
                continue

            product_type = dev.get("productType", "")
            device_type = DEVICE_TYPE_MAP.get(product_type, DeviceType.ENDPOINT)

            raw_status = status_by_serial.get(serial, "offline")
            status = STATUS_MAP.get(raw_status, DeviceStatus.DOWN)

            nodes.append(
                Device(
                    id=serial,
                    type=device_type,
                    model=dev.get("model", "Unknown"),
                    ip=dev.get("lanIp") or dev.get("wan1Ip") or "",
                    status=status,
                    mac=dev.get("mac"),
                )
            )

        edges = self._build_edges(link_layer_data)

        return L2Topology(nodes=nodes, edges=edges)

    def _build_edges(self, link_layer_data: list[dict]) -> list[Edge]:
        """Parse link-layer topology data into Edge objects.

        Each item in link_layer_data is a network's topology response, which
        contains a ``links`` list.  Each link has an ``ends`` list with exactly
        two entries; each end has a ``device.serial`` and optionally
        ``discovered.lldp.portId`` / ``discovered.cdp.portId``.
        """
        edges: list[Edge] = []
        seen: set[frozenset[str]] = set()  # deduplicate bidirectional links

        for network_topology in link_layer_data:
            links = network_topology.get("links", [])
            for link in links:
                ends = link.get("ends", [])
                if len(ends) < 2:
                    continue

                end_a, end_b = ends[0], ends[1]

                serial_a = _extract_serial(end_a)
                serial_b = _extract_serial(end_b)

                if not serial_a or not serial_b:
                    continue

                # Deduplicate: the API may return each link once or twice
                pair_key: frozenset[str] = frozenset({serial_a, serial_b})
                if pair_key in seen:
                    continue
                seen.add(pair_key)

                port_a = _extract_port(end_a)
                port_b = _extract_port(end_b)
                protocol = _detect_protocol(end_a, end_b)

                edge_id = f"{serial_a}:{port_a or 'x'}-{serial_b}:{port_b or 'x'}"
                edges.append(
                    Edge(
                        id=edge_id,
                        source=serial_a,
                        target=serial_b,
                        source_port=port_a,
                        target_port=port_b,
                        protocol=protocol,
                    )
                )

        return edges

    # ------------------------------------------------------------------
    # L3
    # ------------------------------------------------------------------

    def build_l3(
        self,
        vlans_by_network: dict[str, list[dict]],
        devices: list[dict],
    ) -> L3Topology:
        """Build an L3 topology from VLAN and device data.

        Args:
            vlans_by_network: Mapping of network_id → list of VLAN dicts from
                GET /networks/{id}/appliance/vlans.
            devices: List of device objects (used to find the appliance gateway).

        Returns:
            L3Topology with subnets and inter-VLAN routes through the appliance.
        """
        # Find the first appliance serial to use as the routing gateway
        gateway_serial: Optional[str] = None
        for dev in devices:
            if dev.get("productType") == "appliance" and dev.get("serial"):
                gateway_serial = dev["serial"]
                break

        subnets: list[Subnet] = []

        for _network_id, vlans in vlans_by_network.items():
            for vlan in vlans:
                vlan_id = vlan.get("id")
                if vlan_id is None:
                    continue

                subnet_id = f"vlan-{vlan_id}"
                cidr = vlan.get("subnet", "")
                gateway = vlan.get("applianceIp", "")
                name = vlan.get("name", f"VLAN {vlan_id}")
                device_count = len(vlan.get("fixedIpAssignments", {}))

                subnets.append(
                    Subnet(
                        id=subnet_id,
                        name=name,
                        vlan=int(vlan_id),
                        cidr=cidr,
                        gateway=gateway,
                        device_count=device_count,
                    )
                )

        routes: list[Route] = []
        if gateway_serial and len(subnets) > 1:
            # Create a full-mesh of inter-VLAN routes through the appliance
            for i, src in enumerate(subnets):
                for dst in subnets[i + 1 :]:
                    routes.append(
                        Route(
                            from_subnet=src.id,
                            to_subnet=dst.id,
                            via=gateway_serial,
                            policy=RoutingPolicy.ALLOW,
                        )
                    )

        return L3Topology(subnets=subnets, routes=routes)


# ------------------------------------------------------------------
# Private helpers
# ------------------------------------------------------------------

def _extract_serial(end: dict) -> Optional[str]:
    """Return the device serial from a link-layer end object."""
    device = end.get("device") or {}
    return device.get("serial")


def _extract_port(end: dict) -> Optional[str]:
    """Return the port ID from a link-layer end object (LLDP preferred, then CDP)."""
    discovered = end.get("discovered") or {}
    lldp = discovered.get("lldp") or {}
    lldp_port = lldp.get("portId")
    if lldp_port:
        return lldp_port
    cdp = discovered.get("cdp") or {}
    return cdp.get("portId")


def _detect_protocol(end_a: dict, end_b: dict) -> LinkProtocol:
    """Detect the link protocol used — LLDP if either end has LLDP data."""
    for end in (end_a, end_b):
        if (end.get("discovered") or {}).get("lldp"):
            return LinkProtocol.LLDP
    return LinkProtocol.LLDP  # default to LLDP for wired links
