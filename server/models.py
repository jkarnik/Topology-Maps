"""Pydantic models for the Network Topology Simulator API."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DeviceType(str, Enum):
    FIREWALL = "firewall"
    CORE_SWITCH = "core_switch"
    FLOOR_SWITCH = "floor_switch"
    ACCESS_POINT = "access_point"
    ENDPOINT = "endpoint"


class DeviceStatus(str, Enum):
    UP = "up"
    DOWN = "down"
    DEGRADED = "degraded"


class EndpointCategory(str, Enum):
    PAYMENT = "payment"
    OPERATIONS = "operations"
    EMPLOYEE = "employee"
    SECURITY = "security"
    IOT = "iot"
    GUEST = "guest"


class LinkProtocol(str, Enum):
    LLDP = "LLDP"
    ARP = "ARP"
    WIRELESS = "wireless"


class RoutingPolicy(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


# --- Device Models ---

class Interface(BaseModel):
    name: str
    speed: str = "1G"
    status: DeviceStatus = DeviceStatus.UP
    throughput_mbps: float = 0.0
    poe_draw_watts: Optional[float] = None
    vlan: Optional[int] = None


class Device(BaseModel):
    id: str
    type: DeviceType
    model: str
    ip: str
    status: DeviceStatus = DeviceStatus.UP
    floor: Optional[int] = None
    category: Optional[EndpointCategory] = None
    mac: Optional[str] = None
    vlan: Optional[int] = None
    interfaces: list[Interface] = Field(default_factory=list)
    connected_ap: Optional[str] = None  # For wireless clients
    ssid: Optional[str] = None
    rssi: Optional[int] = None  # Signal strength in dBm


# --- Edge / Connection Models ---

class Edge(BaseModel):
    id: str
    source: str  # Device ID
    target: str  # Device ID
    source_port: Optional[str] = None
    target_port: Optional[str] = None
    speed: str = "1G"
    protocol: LinkProtocol = LinkProtocol.LLDP


# --- L2 Topology ---

class L2Topology(BaseModel):
    nodes: list[Device] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


# --- L3 Topology ---

class Subnet(BaseModel):
    id: str
    name: str
    vlan: int
    cidr: str
    gateway: str
    device_count: int = 0


class Route(BaseModel):
    from_subnet: str  # Subnet ID
    to_subnet: str  # Subnet ID or "internet"
    via: str  # Device ID (gateway)
    policy: RoutingPolicy = RoutingPolicy.ALLOW


class L3Topology(BaseModel):
    subnets: list[Subnet] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)


# --- Connection Edit ---

class PortRef(BaseModel):
    switch: str
    port: int


class ConnectionAction(str, Enum):
    MOVE = "move"
    CREATE = "create"
    DELETE = "delete"


class ConnectionEdit(BaseModel):
    action: ConnectionAction
    device: str
    from_port: Optional[PortRef] = Field(None, alias="from")
    to_port: Optional[PortRef] = Field(None, alias="to")

    model_config = {"populate_by_name": True}


# --- WebSocket Events ---

class WSEventType(str, Enum):
    TOPOLOGY_UPDATE = "topology_update"
    DEVICE_STATUS = "device_status"
    CONNECTION_CHANGE = "connection_change"
    METRICS_UPDATE = "metrics_update"


class WSEvent(BaseModel):
    type: WSEventType
    data: dict
