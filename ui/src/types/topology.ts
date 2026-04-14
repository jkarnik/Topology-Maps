// Device types
export type DeviceType = 'firewall' | 'core_switch' | 'floor_switch' | 'access_point' | 'endpoint';
export type DeviceStatus = 'up' | 'down' | 'degraded';
export type EndpointCategory = 'payment' | 'operations' | 'employee' | 'security' | 'iot' | 'guest';
export type LinkProtocol = 'LLDP' | 'ARP' | 'wireless';
export type RoutingPolicy = 'allow' | 'deny';

export interface DeviceInterface {
  name: string;
  speed: string;
  status: DeviceStatus;
  throughput_mbps: number;
  poe_draw_watts: number | null;
  vlan: number | null;
}

export interface Device {
  id: string;
  type: DeviceType;
  model: string;
  ip: string;
  status: DeviceStatus;
  floor: number | null;
  category: EndpointCategory | null;
  mac: string | null;
  vlan: number | null;
  interfaces: DeviceInterface[];
  connected_ap: string | null;
  ssid: string | null;
  rssi: number | null;
}

export interface Edge {
  id: string;
  source: string;
  target: string;
  source_port: string | null;
  target_port: string | null;
  speed: string;
  protocol: LinkProtocol;
}

export interface L2Topology {
  nodes: Device[];
  edges: Edge[];
}

export interface Subnet {
  id: string;
  name: string;
  vlan: number;
  cidr: string;
  gateway: string;
  device_count: number;
}

export interface Route {
  from_subnet: string;
  to_subnet: string;
  via: string;
  policy: RoutingPolicy;
}

export interface L3Topology {
  subnets: Subnet[];
  routes: Route[];
}

export interface WSEvent {
  type: 'topology_update' | 'device_status' | 'connection_change' | 'metrics_update';
  data: Record<string, unknown>;
}

export interface TopologyUpdate {
  l2: L2Topology | null;
  l3: L3Topology | null;
}

// View modes
export type ViewMode = 'l2' | 'l3';

// Drill-down state
export interface DrillDownState {
  path: { id: string; label: string }[];
  currentDeviceId: string | null;
  currentVlanId: number | null;
}
