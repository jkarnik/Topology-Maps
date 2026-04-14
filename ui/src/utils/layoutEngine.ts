import { Node, Edge as RFEdge } from '@xyflow/react';
import { L2Topology, Device, DeviceType } from '../types/topology';

// Layout constants
const TIER_GAP_Y = 180;       // Vertical gap between tiers
const NODE_GAP_X = 80;        // Horizontal gap between nodes in same tier
const ENDPOINT_GAP_X = 30;    // Tighter gap for endpoint nodes

// Per-type node dimensions (width x height)
const NODE_DIMENSIONS: Record<DeviceType, { width: number; height: number }> = {
  firewall:      { width: 190, height: 80 },   // hexagonal shape needs more room
  core_switch:   { width: 200, height: 65 },   // wide rack unit
  floor_switch:  { width: 180, height: 70 },   // standard switch
  access_point:  { width: 90,  height: 90 },   // circle needs equal dimensions
  endpoint:      { width: 100, height: 36 },   // small pill
};

// Tier order: firewalls at top, then core, floor switches, APs, endpoints at bottom
const TIER_ORDER: Record<DeviceType, number> = {
  firewall: 0,
  core_switch: 1,
  floor_switch: 2,
  access_point: 3,
  endpoint: 4,
};

interface LayoutResult {
  nodes: Node[];
  edges: RFEdge[];
}

/**
 * Layout the full L2 topology as a hierarchical tree.
 *
 * @param pinnedDeviceIds - Device IDs that must always appear even if a tier
 *   is truncated to MAX_NODES_PER_TIER (e.g. devices with animations or
 *   involved in pending edits).
 */
export function layoutL2Topology(
  topology: L2Topology,
  drillDownDeviceId?: string | null,
  pinnedDeviceIds?: Set<string>,
): LayoutResult {
  // If drilling down into a specific device, filter to show only that device and its children
  let devices = topology.nodes;
  let connections = topology.edges;

  if (drillDownDeviceId) {
    // Find the target device and all devices directly connected to it
    const targetDevice = devices.find(d => d.id === drillDownDeviceId);
    if (targetDevice) {
      const childEdges = connections.filter(
        e => e.source === drillDownDeviceId || e.target === drillDownDeviceId
      );
      const childIds = new Set(
        childEdges.flatMap(e => [e.source, e.target])
      );
      devices = devices.filter(d => childIds.has(d.id));
      connections = childEdges;
    }
  }

  // Group devices by tier
  const tiers: Map<number, Device[]> = new Map();
  for (const device of devices) {
    const tier = TIER_ORDER[device.type] ?? 4;
    if (!tiers.has(tier)) tiers.set(tier, []);
    tiers.get(tier)!.push(device);
  }

  // For drill-down view, we may only have 2-3 tiers. Renumber them from 0.
  const sortedTierKeys = [...tiers.keys()].sort((a, b) => a - b);

  // Position nodes
  const nodes: Node[] = [];
  let maxTierWidth = 0;

  // First pass: calculate tier widths to center everything
  const tierWidths: Map<number, number> = new Map();
  for (const tierKey of sortedTierKeys) {
    const tierDevices = tiers.get(tierKey)!;
    const representativeType = tierDevices[0]?.type ?? 'endpoint';
    const isSmallType = representativeType === 'endpoint' || representativeType === 'access_point';
    const gap = isSmallType ? ENDPOINT_GAP_X : NODE_GAP_X;
    const nodeW = NODE_DIMENSIONS[representativeType].width;
    const width = tierDevices.length * nodeW + (tierDevices.length - 1) * gap;
    tierWidths.set(tierKey, width);
    maxTierWidth = Math.max(maxTierWidth, width);
  }

  // If we have a LOT of endpoints/APs, limit how many we show
  const MAX_NODES_PER_TIER = 60;

  // Second pass: assign positions
  const pinned = pinnedDeviceIds ?? new Set<string>();

  for (let i = 0; i < sortedTierKeys.length; i++) {
    const tierKey = sortedTierKeys[i];
    let tierDevices = tiers.get(tierKey)!;

    // Limit large tiers — but always include pinned devices
    if (tierDevices.length > MAX_NODES_PER_TIER) {
      const pinnedInTier = tierDevices.filter(d => pinned.has(d.id));
      const unpinnedInTier = tierDevices.filter(d => !pinned.has(d.id));
      const remainingSlots = Math.max(0, MAX_NODES_PER_TIER - pinnedInTier.length);
      tierDevices = [...pinnedInTier, ...unpinnedInTier.slice(0, remainingSlots)];
    }

    const representativeType = tierDevices[0]?.type ?? 'endpoint';
    const isSmallType = representativeType === 'endpoint' || representativeType === 'access_point';
    const gap = isSmallType ? ENDPOINT_GAP_X : NODE_GAP_X;
    const nodeW = NODE_DIMENSIONS[representativeType].width;
    const nodeH = NODE_DIMENSIONS[representativeType].height;
    const tierWidth = tierDevices.length * nodeW + (tierDevices.length - 1) * gap;
    const startX = (maxTierWidth - tierWidth) / 2;
    const y = i * TIER_GAP_Y;

    // Sort devices within tier for consistent ordering
    tierDevices.sort((a, b) => a.id.localeCompare(b.id));

    for (let j = 0; j < tierDevices.length; j++) {
      const device = tierDevices[j];
      nodes.push({
        id: device.id,
        type: 'deviceNode',
        position: { x: startX + j * (nodeW + gap), y },
        data: { device },
        style: { width: nodeW, height: nodeH },
      });
    }
  }

  // Build React Flow edges
  const edges: RFEdge[] = connections
    .filter(e => {
      // Only include edges where both nodes are in our layout
      const nodeIds = new Set(nodes.map(n => n.id));
      return nodeIds.has(e.source) && nodeIds.has(e.target);
    })
    .map(e => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: 'connectionEdge',
      data: { edge: e },
      animated: e.protocol === 'wireless',
    }));

  return { nodes, edges };
}

/**
 * For drill-down: get only the subtree rooted at a specific device.
 */
export function getSubtreeDeviceIds(topology: L2Topology, rootId: string): Set<string> {
  const result = new Set<string>([rootId]);
  const edgeMap = new Map<string, string[]>();

  for (const edge of topology.edges) {
    if (!edgeMap.has(edge.source)) edgeMap.set(edge.source, []);
    edgeMap.get(edge.source)!.push(edge.target);
  }

  const queue = [rootId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    const children = edgeMap.get(current) ?? [];
    for (const child of children) {
      if (!result.has(child)) {
        result.add(child);
        queue.push(child);
      }
    }
  }

  return result;
}
