import { Node, Edge as RFEdge } from '@xyflow/react';
import { L2Topology, Device, DeviceType } from '../types/topology';

// Layout constants
// Firewalls render as a 190px-tall hexagon (DeviceNode.tsx) — the gap must
// clear that or the source/target handles invert and the bezier edge
// loops back on itself instead of curving down to the next tier.
const TIER_GAP_Y = 220;       // Vertical gap between tiers
const NODE_GAP_X = 80;        // Horizontal gap between nodes in same tier
const ENDPOINT_GAP_X = 30;    // Tighter gap for endpoint nodes
const STACK_NODE_W = 220;     // Width for switchStackNode (and non-stacked floor switches)

// Per-type node dimensions (width x height)
const NODE_DIMENSIONS: Record<DeviceType, { width: number; height: number }> = {
  firewall:      { width: 190, height: 80 },
  core_switch:   { width: 200, height: 65 },
  floor_switch:  { width: STACK_NODE_W, height: 70 },
  access_point:  { width: 90,  height: 90 },
  endpoint:      { width: 100, height: 36 },
};

// Tier order: firewalls at top, then core, floor switches, APs, endpoints at bottom
const TIER_ORDER: Record<DeviceType, number> = {
  firewall: 0,
  core_switch: 1,
  floor_switch: 2,
  access_point: 3,
  endpoint: 4,
};

interface SwitchUnit {
  virtualId: string;
  members: Device[];
  stackName: string | null;
}

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
  let devices = topology.nodes;
  let connections = topology.edges;

  if (drillDownDeviceId) {
    const targetDevice = devices.find(d => d.id === drillDownDeviceId);
    if (targetDevice) {
      const childEdges = connections.filter(
        e => e.source === drillDownDeviceId || e.target === drillDownDeviceId
      );
      const childIds = new Set(childEdges.flatMap(e => [e.source, e.target]));
      devices = devices.filter(d => childIds.has(d.id));
      connections = childEdges;
    }
  }

  // ----- Stack grouping -----
  // Meraki stack names are only unique within a network — "Core Stack" is
  // a generic convention many sites reuse — so the All-Networks view must
  // key on (network, stack_name) or it merges different sites' stacks
  // into one virtual node.
  const stackKey = (device: Device): string => `${device.network_id ?? ''}::${device.stack_name}`;
  const stackGroups = new Map<string, Device[]>();
  for (const device of devices) {
    if (device.stack_name) {
      const key = stackKey(device);
      if (!stackGroups.has(key)) stackGroups.set(key, []);
      stackGroups.get(key)!.push(device);
    }
  }

  const memberToVirtualId = new Map<string, string>();
  for (const [, members] of stackGroups) {
    const active = members.find(m => m.stack_role === 'active') ?? members[0];
    const virtualId = `stack-${active.id}`;
    for (const m of members) {
      memberToVirtualId.set(m.id, virtualId);
    }
  }

  const resolveId = (id: string): string => memberToVirtualId.get(id) ?? id;

  // ----- Group devices by tier -----
  const tiers: Map<number, Device[]> = new Map();
  for (const device of devices) {
    const tier = TIER_ORDER[device.type] ?? 4;
    if (!tiers.has(tier)) tiers.set(tier, []);
    tiers.get(tier)!.push(device);
  }

  const sortedTierKeys = [...tiers.keys()].sort((a, b) => a - b);

  // ----- Build switch units for any tier with stacked switches -----
  // Meraki stacks exist at both the core and distribution layer, so this
  // groups whichever tier's devices share a stack_name (e.g. a "Core
  // Stack" pair as well as per-floor "Dist" stacks) into one visual unit —
  // not just the floor_switch tier. Devices resolve to a virtual node ID
  // when stacked, so building this per-tier keeps edge resolution below
  // consistent with the nodes actually rendered for that tier.
  function buildSwitchUnits(tierDevices: Device[]): SwitchUnit[] {
    const units: SwitchUnit[] = [];
    const seenVirtualIds = new Set<string>();
    for (const d of tierDevices) {
      const vId = resolveId(d.id);
      if (seenVirtualIds.has(vId)) continue;
      seenVirtualIds.add(vId);
      if (d.stack_name) {
        const members = stackGroups.get(stackKey(d)) ?? [d];
        units.push({ virtualId: vId, members, stackName: d.stack_name });
      } else {
        units.push({ virtualId: vId, members: [d], stackName: null });
      }
    }
    units.sort((a, b) => a.virtualId.localeCompare(b.virtualId));
    return units;
  }

  const tierSwitchUnits = new Map<number, SwitchUnit[]>();
  for (const tierKey of sortedTierKeys) {
    const tierDevices = tiers.get(tierKey)!;
    if (tierDevices.some(d => d.stack_name)) {
      tierSwitchUnits.set(tierKey, buildSwitchUnits(tierDevices));
    }
  }

  // ----- AP parent mapping (for sort) -----
  const floorSwitchTierDevices = tiers.get(TIER_ORDER.floor_switch) ?? [];
  const floorSwitchDeviceIds = new Set(floorSwitchTierDevices.map(d => d.id));
  const apDeviceIds = new Set((tiers.get(TIER_ORDER.access_point) ?? []).map(d => d.id));
  const apToParentSwitch = new Map<string, string>();
  for (const edge of connections) {
    if (edge.protocol === 'stack') continue;
    if (floorSwitchDeviceIds.has(edge.source) && apDeviceIds.has(edge.target)) {
      apToParentSwitch.set(edge.target, resolveId(edge.source));
    } else if (floorSwitchDeviceIds.has(edge.target) && apDeviceIds.has(edge.source)) {
      apToParentSwitch.set(edge.source, resolveId(edge.target));
    }
  }

  // ----- First pass: calculate tier widths -----
  let maxTierWidth = 0;
  for (const tierKey of sortedTierKeys) {
    const tierDevices = tiers.get(tierKey)!;
    const representativeType = tierDevices[0]?.type ?? 'endpoint';
    const switchUnitsForTier = tierSwitchUnits.get(tierKey);
    let width: number;

    if (switchUnitsForTier) {
      width = switchUnitsForTier.length * STACK_NODE_W + Math.max(0, switchUnitsForTier.length - 1) * NODE_GAP_X;
    } else {
      const isSmallType = representativeType === 'endpoint' || representativeType === 'access_point';
      const gap = isSmallType ? ENDPOINT_GAP_X : NODE_GAP_X;
      const nodeW = NODE_DIMENSIONS[representativeType].width;
      width = tierDevices.length * nodeW + Math.max(0, tierDevices.length - 1) * gap;
    }
    maxTierWidth = Math.max(maxTierWidth, width);
  }

  // ----- Second pass: assign positions -----
  const MAX_NODES_PER_TIER = 60;
  const pinned = pinnedDeviceIds ?? new Set<string>();
  const nodes: Node[] = [];

  for (let i = 0; i < sortedTierKeys.length; i++) {
    const tierKey = sortedTierKeys[i];
    let tierDevices = tiers.get(tierKey)!;
    const representativeType = tierDevices[0]?.type ?? 'endpoint';
    const y = i * TIER_GAP_Y;
    const switchUnitsForTier = tierSwitchUnits.get(tierKey);

    if (switchUnitsForTier) {
      const tierWidth = switchUnitsForTier.length * STACK_NODE_W + Math.max(0, switchUnitsForTier.length - 1) * NODE_GAP_X;
      const startX = (maxTierWidth - tierWidth) / 2;

      for (let j = 0; j < switchUnitsForTier.length; j++) {
        const unit = switchUnitsForTier[j];
        const x = startX + j * (STACK_NODE_W + NODE_GAP_X);
        if (unit.stackName) {
          nodes.push({
            id: unit.virtualId,
            type: 'switchStackNode',
            position: { x, y },
            data: { stackName: unit.stackName, members: unit.members },
            style: { width: STACK_NODE_W },
          });
        } else {
          const device = unit.members[0];
          nodes.push({
            id: device.id,
            type: 'deviceNode',
            position: { x, y },
            data: { device },
            style: { width: STACK_NODE_W, height: NODE_DIMENSIONS[device.type].height },
          });
        }
      }
    } else {
      if (tierDevices.length > MAX_NODES_PER_TIER) {
        const pinnedInTier = tierDevices.filter(d => pinned.has(d.id));
        const unpinnedInTier = tierDevices.filter(d => !pinned.has(d.id));
        const remainingSlots = Math.max(0, MAX_NODES_PER_TIER - pinnedInTier.length);
        tierDevices = [...pinnedInTier, ...unpinnedInTier.slice(0, remainingSlots)];
      }

      const isSmallType = representativeType === 'endpoint' || representativeType === 'access_point';
      const gap = isSmallType ? ENDPOINT_GAP_X : NODE_GAP_X;
      const nodeW = NODE_DIMENSIONS[representativeType].width;
      const nodeH = NODE_DIMENSIONS[representativeType].height;

      if (representativeType === 'access_point') {
        tierDevices.sort((a, b) => {
          const pa = apToParentSwitch.get(a.id) ?? '';
          const pb = apToParentSwitch.get(b.id) ?? '';
          return pa !== pb ? pa.localeCompare(pb) : a.id.localeCompare(b.id);
        });
      } else if (representativeType === 'endpoint') {
        tierDevices.sort((a, b) => {
          const pa = a.connected_ap ?? '';
          const pb = b.connected_ap ?? '';
          return pa !== pb ? pa.localeCompare(pb) : a.id.localeCompare(b.id);
        });
      } else {
        tierDevices.sort((a, b) => a.id.localeCompare(b.id));
      }

      const tierWidth = tierDevices.length * nodeW + Math.max(0, tierDevices.length - 1) * gap;
      const startX = (maxTierWidth - tierWidth) / 2;

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
  }

  // ----- Build React Flow edges -----
  const nodeIds = new Set(nodes.map(n => n.id));
  const seenEdgePairs = new Set<string>();
  const edges: RFEdge[] = [];
  const deviceTierById = new Map<string, number>();
  for (const device of devices) {
    deviceTierById.set(device.id, TIER_ORDER[device.type] ?? 4);
  }

  for (const e of connections) {
    if (e.protocol === 'stack') continue;
    // LLDP direction reflects whichever side happened to report the link,
    // not visual hierarchy — a link can come in as core→firewall just as
    // easily as firewall→core. Every node only exposes a Bottom-exit /
    // Top-entry handle, so normalize to the higher tier as source or the
    // edge is forced to loop back on itself to satisfy the handle
    // directions.
    const srcTier = deviceTierById.get(e.source) ?? 0;
    const tgtTier = deviceTierById.get(e.target) ?? 0;
    const [higherId, lowerId] = srcTier <= tgtTier ? [e.source, e.target] : [e.target, e.source];
    const src = resolveId(higherId);
    const tgt = resolveId(lowerId);
    if (src === tgt) continue;
    if (!nodeIds.has(src) || !nodeIds.has(tgt)) continue;
    const pairKey = [src, tgt].sort().join('--');
    if (seenEdgePairs.has(pairKey)) continue;
    seenEdgePairs.add(pairKey);
    edges.push({
      id: `${src}-${tgt}`,
      source: src,
      target: tgt,
      type: 'connectionEdge',
      data: { edge: e },
      animated: e.protocol === 'wireless',
    });
  }

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
