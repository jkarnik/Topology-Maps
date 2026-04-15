import React, { useMemo, useCallback, useEffect } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  Handle,
  Position,
  useNodesState,
  useEdgesState,
  type NodeProps,
  type Edge as RFEdge,
  type Node as RFNode,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import DeviceNode from './DeviceNode';
import type {
  L2Topology,
  L3Topology,
  Device,
  Subnet,
} from '../types/topology';

/* ================================================================
   Props
   ================================================================ */

interface HybridViewProps {
  l2Topology: L2Topology | null;
  l3Topology: L3Topology | null;
  onSelectDevice?: (device: Device | null) => void;
  onSelectVlan?: (vlanId: number) => void;
  gatewayLabel?: string;
}

/* ================================================================
   VLAN color map (matches L3View)
   ================================================================ */

const vlanColors: Record<number, string> = {
  10: '#ff4757', // Payment/PCI — red
  20: '#4c9aff', // Operations — blue
  30: '#00e5c8', // Employee Wi-Fi — cyan
  40: '#f5a623', // Security — amber
  50: '#00d68f', // IoT — green
  60: '#b07aff', // Guest Wi-Fi — purple
};

function getVlanColor(vlanId: number): string {
  return vlanColors[vlanId] ?? 'var(--text-muted)';
}

function getVlanGlow(vlanId: number): string {
  const color = vlanColors[vlanId];
  if (!color) return 'rgba(85, 102, 119, 0.1)';
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, 0.12)`;
}

/* ================================================================
   VlanGroupNode — custom node for VLAN container boxes
   ================================================================ */

type VlanGroupNodeData = {
  subnet: Subnet;
  vlanColor: string;
  vlanGlow: string;
  deviceCount: number;
  onSelectVlan?: (vlanId: number) => void;
};

const VlanGroupNode: React.FC<NodeProps> = ({ data }) => {
  const { subnet, vlanColor, vlanGlow, deviceCount, onSelectVlan } =
    data as VlanGroupNodeData;

  return (
    <div
      onClick={() => onSelectVlan?.(subnet.vlan)}
      style={{
        width: 240,
        height: 130,
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
        borderLeft: `4px solid ${vlanColor}`,
        borderRadius: 8,
        padding: '14px 16px',
        cursor: onSelectVlan ? 'pointer' : 'default',
        boxShadow: `0 2px 12px ${vlanGlow}, 0 1px 3px rgba(0,0,0,0.4)`,
        transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
        fontFamily: "'JetBrains Mono', monospace",
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        gap: 6,
      }}
      onMouseEnter={(e) => {
        if (!onSelectVlan) return;
        e.currentTarget.style.borderColor = vlanColor;
        e.currentTarget.style.borderLeftColor = vlanColor;
        const r = parseInt(vlanColor.slice(1, 3), 16);
        const g = parseInt(vlanColor.slice(3, 5), 16);
        const b = parseInt(vlanColor.slice(5, 7), 16);
        e.currentTarget.style.boxShadow = `0 4px 20px rgba(${r}, ${g}, ${b}, 0.3), 0 1px 4px rgba(0,0,0,0.5)`;
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-subtle)';
        e.currentTarget.style.borderLeftColor = vlanColor;
        e.currentTarget.style.boxShadow = `0 2px 12px ${vlanGlow}, 0 1px 3px rgba(0,0,0,0.4)`;
      }}
    >
      {/* Target handle — edges from floor switches arrive here */}
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 6, height: 6, background: vlanColor, border: 'none', opacity: 0 }}
      />

      {/* VLAN name */}
      <div
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: 'var(--text-primary)',
          lineHeight: 1.3,
        }}
      >
        {subnet.name}
      </div>

      {/* VLAN ID pill + CIDR */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: vlanColor,
            background: vlanGlow,
            padding: '2px 7px',
            borderRadius: 4,
            border: `1px solid ${vlanColor}`,
            whiteSpace: 'nowrap',
          }}
        >
          VLAN {subnet.vlan}
        </span>
        <span
          style={{
            fontSize: 10,
            color: 'var(--text-muted)',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {subnet.cidr}
        </span>
      </div>

      {/* Device count */}
      <div
        style={{
          fontSize: 10,
          color: 'var(--text-secondary)',
          display: 'flex',
          alignItems: 'center',
          gap: 4,
        }}
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <line x1="8" y1="21" x2="16" y2="21" />
          <line x1="12" y1="17" x2="12" y2="21" />
        </svg>
        {deviceCount} device{deviceCount !== 1 ? 's' : ''}
      </div>

      {/* Source handle — inter-VLAN routing edges originate here */}
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 6, height: 6, background: vlanColor, border: 'none', opacity: 0 }}
      />
    </div>
  );
};

/* ================================================================
   Node type registrations (outside component to avoid re-renders)
   ================================================================ */

const nodeTypes = {
  deviceNode: DeviceNode,
  vlanGroupNode: VlanGroupNode,
};

/* ================================================================
   Layout constants
   ================================================================ */

const TIER_0_Y = 0;       // Firewalls/FortiGate pair
const TIER_1_Y = 180;     // Core switches (or floor switches if no core)
const TIER_2_Y = 360;     // Floor switches (skipped when no core switches)
const TIER_AP_Y = 530;    // Access points (between switches and VLANs)
const TIER_VLAN_Y_BASE = 700; // VLAN group boxes (shifts up when no core)

const VLAN_BOX_W = 240;
const VLAN_BOX_H = 130;
const VLAN_H_GAP = 30;
const VLAN_V_GAP = 30;
const VLAN_COLS = 3;

/* ================================================================
   Graph builder
   ================================================================ */

function buildHybridGraph(
  l2: L2Topology,
  l3: L3Topology,
  _onSelectDevice?: (device: Device | null) => void,
  onSelectVlan?: (vlanId: number) => void,
): { nodes: RFNode[]; edges: RFEdge[] } {
  const nodes: RFNode[] = [];
  const edges: RFEdge[] = [];

  /* ------ 1. Index L2 devices by id and type ------ */

  const deviceMap = new Map<string, Device>();
  const firewalls: Device[] = [];
  const coreSwitches: Device[] = [];
  const floorSwitches: Device[] = [];
  const accessPoints: Device[] = [];
  const endpoints: Device[] = [];

  for (const d of l2.nodes) {
    deviceMap.set(d.id, d);
    switch (d.type) {
      case 'firewall':
        firewalls.push(d);
        break;
      case 'core_switch':
        coreSwitches.push(d);
        break;
      case 'floor_switch':
        floorSwitches.push(d);
        break;
      case 'access_point':
        accessPoints.push(d);
        break;
      case 'endpoint':
        endpoints.push(d);
        break;
    }
  }

  /* ------ Determine effective tier layout ------ */
  // Meraki case: no core switches → collapse tiers upward
  const hasCoreSwitches = coreSwitches.length > 0;
  // Y positions for floor switches and VLAN boxes depend on whether core switches exist
  const effectiveFloorSwitchY = hasCoreSwitches ? TIER_2_Y : TIER_1_Y;
  const effectiveApY = hasCoreSwitches ? TIER_AP_Y : TIER_AP_Y - (TIER_2_Y - TIER_1_Y);
  const effectiveVlanY = hasCoreSwitches ? TIER_VLAN_Y_BASE : TIER_VLAN_Y_BASE - (TIER_2_Y - TIER_1_Y);

  /* ------ 2. Tier 0 — Firewall pair ------ */

  // Sort so primary comes first (convention: "fg-primary" before "fg-standby")
  firewalls.sort((a, b) => a.id.localeCompare(b.id));

  const fwSpacing = 240;
  const fwTotalWidth = firewalls.length * 180 + (firewalls.length - 1) * (fwSpacing - 180);
  const fwStartX = (VLAN_COLS * (VLAN_BOX_W + VLAN_H_GAP) - VLAN_H_GAP) / 2 - fwTotalWidth / 2;

  firewalls.forEach((fw, i) => {
    nodes.push({
      id: fw.id,
      type: 'deviceNode',
      position: { x: fwStartX + i * fwSpacing, y: TIER_0_Y },
      data: { device: fw },
      draggable: true,
    });
  });

  // HA-link edge between firewalls (if two exist)
  if (firewalls.length === 2) {
    edges.push({
      id: 'ha-link',
      source: firewalls[0].id,
      target: firewalls[1].id,
      style: {
        stroke: 'var(--accent-red)',
        strokeWidth: 1.5,
        strokeDasharray: '4 3',
        opacity: 0.6,
      },
      label: 'HA',
      labelStyle: {
        fill: 'var(--accent-red)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 9,
        fontWeight: 600,
      },
      labelBgStyle: {
        fill: 'var(--bg-primary)',
        fillOpacity: 0.85,
      },
      labelBgPadding: [3, 3] as [number, number],
      labelBgBorderRadius: 3,
    });
  }

  const gridTotalWidth = VLAN_COLS * (VLAN_BOX_W + VLAN_H_GAP) - VLAN_H_GAP;

  /* ------ 3. Tier 1 — Core Switches (only when they exist) ------ */

  if (hasCoreSwitches) {
    const coreCenterX = gridTotalWidth / 2 - 110; // 220/2 = 110

    coreSwitches.forEach((cs, i) => {
      nodes.push({
        id: cs.id,
        type: 'deviceNode',
        position: { x: coreCenterX + i * 260, y: TIER_1_Y },
        data: { device: cs },
        draggable: true,
      });
    });

    // Edges: FortiGates -> Core Switch(es) — only where L2 edges exist
    for (const fw of firewalls) {
      for (const cs of coreSwitches) {
        const l2Edge = l2.edges.find(
          (e) =>
            (e.source === fw.id && e.target === cs.id) ||
            (e.source === cs.id && e.target === fw.id),
        );
        if (!l2Edge) continue;
        edges.push({
          id: `infra-${fw.id}-${cs.id}`,
          source: fw.id,
          target: cs.id,
          style: {
            stroke: 'var(--accent-cyan)',
            strokeWidth: 2,
            opacity: 0.7,
          },
          label: l2Edge.speed ?? '10G',
          labelStyle: {
            fill: 'var(--text-muted)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
          },
          labelBgStyle: {
            fill: 'var(--bg-primary)',
            fillOpacity: 0.85,
          },
          labelBgPadding: [3, 3] as [number, number],
          labelBgBorderRadius: 3,
        });
      }
    }
  }

  /* ------ 4. Floor Switches (Tier 1 when no core, Tier 2 otherwise) ------ */

  // Sort floor switches by id for consistent ordering
  floorSwitches.sort((a, b) => a.id.localeCompare(b.id));

  const fsSpacing = 210;
  const fsTotalWidth =
    floorSwitches.length * 190 + (floorSwitches.length - 1) * (fsSpacing - 190);
  const fsStartX = gridTotalWidth / 2 - fsTotalWidth / 2;

  floorSwitches.forEach((fs, i) => {
    nodes.push({
      id: fs.id,
      type: 'deviceNode',
      position: { x: fsStartX + i * fsSpacing, y: effectiveFloorSwitchY },
      data: { device: fs },
      draggable: true,
    });
  });

  if (hasCoreSwitches) {
    // Edges: Core Switches -> Floor Switches (only where L2 edges exist)
    for (const cs of coreSwitches) {
      for (const fs of floorSwitches) {
        const l2Edge = l2.edges.find(
          (e) =>
            (e.source === cs.id && e.target === fs.id) ||
            (e.source === fs.id && e.target === cs.id),
        );
        if (!l2Edge) continue;
        edges.push({
          id: `infra-${cs.id}-${fs.id}`,
          source: cs.id,
          target: fs.id,
          style: {
            stroke: 'var(--accent-cyan)',
            strokeWidth: 1.5,
            opacity: 0.6,
          },
          label: l2Edge.speed ?? '1G',
          labelStyle: {
            fill: 'var(--text-muted)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
          },
          labelBgStyle: {
            fill: 'var(--bg-primary)',
            fillOpacity: 0.85,
          },
          labelBgPadding: [3, 3] as [number, number],
          labelBgBorderRadius: 3,
        });
      }
    }
  } else {
    // Meraki: Firewalls connect directly to floor switches using actual L2 edges
    for (const fw of firewalls) {
      for (const fs of floorSwitches) {
        const l2Edge = l2.edges.find(
          (e) =>
            (e.source === fw.id && e.target === fs.id) ||
            (e.source === fs.id && e.target === fw.id),
        );
        if (!l2Edge) continue;
        edges.push({
          id: `infra-${fw.id}-${fs.id}`,
          source: fw.id,
          target: fs.id,
          style: {
            stroke: 'var(--accent-cyan)',
            strokeWidth: 2,
            opacity: 0.7,
          },
          label: l2Edge.speed ?? '1G',
          labelStyle: {
            fill: 'var(--text-muted)',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 9,
          },
          labelBgStyle: {
            fill: 'var(--bg-primary)',
            fillOpacity: 0.85,
          },
          labelBgPadding: [3, 3] as [number, number],
          labelBgBorderRadius: 3,
        });
      }
    }
  }

  /* ------ 4b. Stack edges ------ */

  for (const l2Edge of l2.edges) {
    if (l2Edge.protocol === 'stack') {
      edges.push({
        id: `stack-${l2Edge.source}-${l2Edge.target}`,
        source: l2Edge.source,
        target: l2Edge.target,
        style: {
          stroke: 'var(--accent-green)',
          strokeWidth: 2,
          strokeDasharray: '6 3',
          opacity: 0.8,
        },
        label: 'stack',
        labelStyle: {
          fill: 'var(--accent-green)',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          fontWeight: 600,
        },
        labelBgStyle: {
          fill: 'var(--bg-primary)',
          fillOpacity: 0.85,
        },
        labelBgPadding: [3, 3] as [number, number],
        labelBgBorderRadius: 3,
      });
    }
  }

  /* ------ 5. Access Points tier (between switches and VLANs) ------ */

  const floorSwitchIds = new Set(floorSwitches.map((fs) => fs.id));

  // Build AP -> parent floor switch mapping from L2 edges
  const apToFloorSwitch = new Map<string, string>();
  for (const edge of l2.edges) {
    if (floorSwitchIds.has(edge.source) && deviceMap.get(edge.target)?.type === 'access_point') {
      apToFloorSwitch.set(edge.target, edge.source);
    } else if (
      floorSwitchIds.has(edge.target) &&
      deviceMap.get(edge.source)?.type === 'access_point'
    ) {
      apToFloorSwitch.set(edge.source, edge.target);
    }
  }

  accessPoints.sort((a, b) => a.id.localeCompare(b.id));

  const apSpacing = 200;
  const apTotalWidth = accessPoints.length * 180 + (accessPoints.length - 1) * (apSpacing - 180);
  const apStartX = accessPoints.length > 0 ? gridTotalWidth / 2 - apTotalWidth / 2 : 0;

  accessPoints.forEach((ap, i) => {
    nodes.push({
      id: ap.id,
      type: 'deviceNode',
      position: { x: apStartX + i * apSpacing, y: effectiveApY },
      data: { device: ap },
      draggable: true,
    });
  });

  // Edges: Floor Switches -> APs (only where L2 edges exist)
  for (const ap of accessPoints) {
    const fsId = apToFloorSwitch.get(ap.id);
    if (!fsId) continue;
    const l2Edge = l2.edges.find(
      (e) =>
        (e.source === fsId && e.target === ap.id) ||
        (e.source === ap.id && e.target === fsId),
    );
    edges.push({
      id: `infra-${fsId}-${ap.id}`,
      source: fsId,
      target: ap.id,
      style: {
        stroke: 'var(--accent-cyan)',
        strokeWidth: 1.5,
        opacity: 0.6,
      },
      label: l2Edge?.speed ?? undefined,
      labelStyle: {
        fill: 'var(--text-muted)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 9,
      },
      labelBgStyle: {
        fill: 'var(--bg-primary)',
        fillOpacity: 0.85,
      },
      labelBgPadding: [3, 3] as [number, number],
      labelBgBorderRadius: 3,
    });
  }

  /* ------ 6. VLAN Group Boxes ------ */

  // Build endpoint -> floor-switch mapping from L2 edges
  // Includes direct connections and AP-mediated connections
  const endpointToFloorSwitch = new Map<string, string>();
  for (const edge of l2.edges) {
    if (floorSwitchIds.has(edge.source) && deviceMap.get(edge.target)?.type === 'endpoint') {
      endpointToFloorSwitch.set(edge.target, edge.source);
    } else if (
      floorSwitchIds.has(edge.target) &&
      deviceMap.get(edge.source)?.type === 'endpoint'
    ) {
      endpointToFloorSwitch.set(edge.source, edge.target);
    }
    // AP -> floor switch -> endpoint chains (wireless clients)
    if (floorSwitchIds.has(edge.source) && deviceMap.get(edge.target)?.type === 'access_point') {
      const apId = edge.target;
      for (const ep of endpoints) {
        if (ep.connected_ap === apId) {
          endpointToFloorSwitch.set(ep.id, edge.source);
        }
      }
    } else if (
      floorSwitchIds.has(edge.target) &&
      deviceMap.get(edge.source)?.type === 'access_point'
    ) {
      const apId = edge.source;
      for (const ep of endpoints) {
        if (ep.connected_ap === apId) {
          endpointToFloorSwitch.set(ep.id, edge.target);
        }
      }
    }
  }

  // vlanId -> set of floor switch IDs (or AP IDs for wireless VLANs)
  const vlanToSwitchOrAp = new Map<number, Set<string>>();
  // vlanId -> actual endpoint count from L2 data
  const vlanDeviceCounts = new Map<number, number>();

  for (const ep of endpoints) {
    if (ep.vlan == null) continue;
    const fsId = endpointToFloorSwitch.get(ep.id);
    if (fsId) {
      if (!vlanToSwitchOrAp.has(ep.vlan)) {
        vlanToSwitchOrAp.set(ep.vlan, new Set());
      }
      vlanToSwitchOrAp.get(ep.vlan)!.add(fsId);
    }
    // Count endpoints per VLAN
    vlanDeviceCounts.set(ep.vlan, (vlanDeviceCounts.get(ep.vlan) ?? 0) + 1);
  }

  // Also connect AP nodes to VLAN boxes for wireless client VLANs
  for (const ep of endpoints) {
    if (ep.vlan == null || ep.connected_ap == null) continue;
    if (!vlanToSwitchOrAp.has(ep.vlan)) {
      vlanToSwitchOrAp.set(ep.vlan, new Set());
    }
    // Use AP id as the edge source so the visual goes AP -> VLAN
    vlanToSwitchOrAp.get(ep.vlan)!.add(ep.connected_ap);
  }

  // Fallback: match by floor number when no L2 edge found
  for (const ep of endpoints) {
    if (ep.vlan == null || ep.floor == null) continue;
    const matchingFs = floorSwitches.find((fs) => fs.floor === ep.floor);
    if (matchingFs) {
      if (!vlanToSwitchOrAp.has(ep.vlan)) {
        vlanToSwitchOrAp.set(ep.vlan, new Set());
      }
      vlanToSwitchOrAp.get(ep.vlan)!.add(matchingFs.id);
    }
  }

  // Create VLAN group nodes in a 3xN grid
  const subnets = l3.subnets;
  subnets.forEach((subnet, i) => {
    const col = i % VLAN_COLS;
    const row = Math.floor(i / VLAN_COLS);
    const x = col * (VLAN_BOX_W + VLAN_H_GAP);
    const y = effectiveVlanY + row * (VLAN_BOX_H + VLAN_V_GAP);
    const color = getVlanColor(subnet.vlan);
    const glow = getVlanGlow(subnet.vlan);
    const deviceCount = vlanDeviceCounts.get(subnet.vlan) ?? subnet.device_count;

    nodes.push({
      id: `vlan-${subnet.vlan}`,
      type: 'vlanGroupNode',
      position: { x, y },
      data: {
        subnet,
        vlanColor: color,
        vlanGlow: glow,
        deviceCount,
        onSelectVlan,
      },
      draggable: true,
    });
  });

  // Edges: Switches/APs -> VLAN groups
  const addedSwitchVlanEdges = new Set<string>();
  const apIds = new Set(accessPoints.map((ap) => ap.id));
  for (const subnet of subnets) {
    const srcSet = vlanToSwitchOrAp.get(subnet.vlan);
    if (!srcSet) continue;
    const color = getVlanColor(subnet.vlan);
    for (const srcId of srcSet) {
      const edgeKey = `${srcId}-vlan-${subnet.vlan}`;
      if (addedSwitchVlanEdges.has(edgeKey)) continue;
      addedSwitchVlanEdges.add(edgeKey);

      // Only emit this edge if the source node actually exists in the graph
      const srcIsFloorSwitch = floorSwitchIds.has(srcId);
      const srcIsAp = apIds.has(srcId);
      if (!srcIsFloorSwitch && !srcIsAp) continue;

      edges.push({
        id: `fs-vlan-${srcId}-${subnet.vlan}`,
        source: srcId,
        target: `vlan-${subnet.vlan}`,
        style: {
          stroke: color,
          strokeWidth: 1.5,
          opacity: 0.5,
        },
      });
    }
  }

  /* ------ 7. Inter-VLAN Routing Policy Edges ------ */

  // Build a subnet id -> vlan id mapping for route resolution
  const subnetIdToVlan = new Map<string, number>();
  for (const s of subnets) {
    subnetIdToVlan.set(s.id, s.vlan);
  }

  l3.routes.forEach((route, i) => {
    // Skip gateway routes
    if (route.from_subnet === 'gateway' || route.to_subnet === 'gateway') return;

    const fromVlan = subnetIdToVlan.get(route.from_subnet);
    const toVlan = subnetIdToVlan.get(route.to_subnet);
    if (fromVlan == null || toVlan == null) return;

    const isAllow = route.policy === 'allow';

    edges.push({
      id: `route-${i}`,
      source: `vlan-${fromVlan}`,
      target: `vlan-${toVlan}`,
      style: {
        stroke: isAllow ? 'var(--accent-green)' : 'var(--accent-red)',
        strokeWidth: 1.5,
        strokeDasharray: '6 4',
        opacity: 0.6,
      },
      label: isAllow ? 'allow' : 'deny',
      labelStyle: {
        fill: isAllow ? 'var(--accent-green)' : 'var(--accent-red)',
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 9,
        fontWeight: 600,
      },
      labelBgStyle: {
        fill: 'var(--bg-primary)',
        fillOpacity: 0.85,
      },
      labelBgPadding: [3, 4] as [number, number],
      labelBgBorderRadius: 3,
    });
  });

  return { nodes, edges };
}

/* ================================================================
   MiniMap node color helper
   ================================================================ */

function miniMapNodeColor(node: RFNode): string {
  if (node.type === 'vlanGroupNode') {
    const d = node.data as VlanGroupNodeData;
    return d.vlanColor;
  }
  if (node.type === 'deviceNode') {
    const d = node.data as { device: Device };
    switch (d.device.type) {
      case 'firewall':
        return '#ff4757';
      case 'core_switch':
        return '#4c9aff';
      case 'floor_switch':
        return '#f5a623';
      default:
        return '#556677';
    }
  }
  return '#556677';
}

/* ================================================================
   Main Component
   ================================================================ */

const HybridView: React.FC<HybridViewProps> = ({
  l2Topology,
  l3Topology,
  onSelectDevice,
  onSelectVlan,
  gatewayLabel: _gatewayLabel,
}) => {
  const graph = useMemo(() => {
    if (!l2Topology || !l3Topology) return { nodes: [], edges: [] };
    return buildHybridGraph(l2Topology, l3Topology, onSelectDevice, onSelectVlan);
  }, [l2Topology, l3Topology, onSelectDevice, onSelectVlan]);

  const [nodes, setNodes, onNodesChange] = useNodesState(graph.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(graph.edges);

  useEffect(() => {
    setNodes(graph.nodes);
    setEdges(graph.edges);
  }, [graph, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: React.MouseEvent, node: RFNode) => {
      if (node.type === 'deviceNode' && onSelectDevice) {
        const d = node.data as { device: Device };
        onSelectDevice(d.device);
      }
      // VLAN group clicks are handled inside the VlanGroupNode via onSelectVlan
    },
    [onSelectDevice],
  );

  const handlePaneClick = useCallback(() => {
    onSelectDevice?.(null);
  }, [onSelectDevice]);

  if (!l2Topology || !l3Topology) {
    return (
      <div
        className="flex items-center justify-center h-full"
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          color: 'var(--text-muted)',
        }}
      >
        NO TOPOLOGY DATA AVAILABLE
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={handleNodeClick}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.2}
        maxZoom={2}
        proOptions={{ hideAttribution: true }}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={24}
          size={1}
          color="rgba(136, 153, 170, 0.08)"
        />
        <Controls
          showInteractive={false}
          style={{ bottom: 16, right: 16, left: 'auto' }}
        />
        <MiniMap
          nodeColor={miniMapNodeColor}
          maskColor="rgba(10, 14, 20, 0.7)"
          style={{
            bottom: 16,
            right: 60,
            width: 140,
            height: 90,
          }}
        />
      </ReactFlow>

      {/* Legend */}
      <div
        style={{
          position: 'absolute',
          bottom: 16,
          right: 16,
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-subtle)',
          borderRadius: 6,
          padding: '10px 14px',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 9,
          zIndex: 20,
          pointerEvents: 'none',
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: 'var(--text-muted)',
            letterSpacing: '0.1em',
            marginBottom: 8,
          }}
        >
          HYBRID VIEW
        </div>

        {/* Physical L2 connection */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: 5,
          }}
        >
          <div
            style={{
              width: 20,
              height: 0,
              borderTop: '2px solid var(--accent-cyan)',
            }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>Physical L2</span>
        </div>

        {/* Routing allowed */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            marginBottom: 5,
          }}
        >
          <div
            style={{
              width: 20,
              height: 0,
              borderTop: '2px dashed var(--accent-green)',
            }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>Routing allowed</span>
        </div>

        {/* Routing denied */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <div
            style={{
              width: 20,
              height: 0,
              borderTop: '2px dashed var(--accent-red)',
            }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>Routing denied</span>
        </div>
      </div>
    </div>
  );
};

export default HybridView;
