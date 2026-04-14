import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  Position,
  type NodeProps,
  type Edge as RFEdge,
  type Node as RFNode,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { L3Topology, Subnet } from '../types/topology';

/* ---------- Props ---------- */

interface L3ViewProps {
  topology: L3Topology | null;
  onSelectVlan?: (vlanId: number) => void;
}

/* ---------- VLAN color map ---------- */

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
  // Convert hex to rgba with low alpha
  const r = parseInt(color.slice(1, 3), 16);
  const g = parseInt(color.slice(3, 5), 16);
  const b = parseInt(color.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, 0.12)`;
}

/* ---------- Gateway Node ---------- */

type GatewayNodeData = {
  label: string;
};

const GatewayNode: React.FC<NodeProps> = ({ data }) => {
  const { label } = data as GatewayNodeData;
  return (
    <div
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--device-firewall)',
        borderRadius: 8,
        padding: '14px 24px',
        boxShadow: '0 4px 20px rgba(255, 71, 87, 0.15), 0 1px 4px rgba(0,0,0,0.4)',
        fontFamily: "'JetBrains Mono', monospace",
        textAlign: 'center',
        minWidth: 160,
      }}
    >
      {/* Firewall icon */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 6 }}>
        <svg
          width="28"
          height="28"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--device-firewall)"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 2L3 7v6c0 5.25 3.75 10.15 9 11.25C17.25 23.15 21 18.25 21 13V7l-9-5z" />
          <path d="M12 8v4" />
          <path d="M12 16h.01" />
        </svg>
      </div>
      <div
        style={{
          fontSize: 13,
          fontWeight: 700,
          color: 'var(--text-primary)',
          letterSpacing: '0.04em',
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 10,
          color: 'var(--text-muted)',
          marginTop: 2,
          letterSpacing: '0.06em',
        }}
      >
        GATEWAY
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 6, height: 6, background: 'var(--device-firewall)', border: 'none', opacity: 0 }}
      />
    </div>
  );
};

/* ---------- VLAN Block Node ---------- */

type VlanNodeData = {
  subnet: Subnet;
  onSelect?: (vlanId: number) => void;
};

const VlanBlockNode: React.FC<NodeProps> = ({ data }) => {
  const { subnet, onSelect } = data as VlanNodeData;
  const color = getVlanColor(subnet.vlan);
  const glow = getVlanGlow(subnet.vlan);

  return (
    <div
      onClick={() => onSelect?.(subnet.vlan)}
      style={{
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border-subtle)',
        borderLeft: `4px solid ${color}`,
        borderRadius: 6,
        padding: '14px 16px',
        minWidth: 180,
        cursor: onSelect ? 'pointer' : 'default',
        boxShadow: `0 2px 12px ${glow}, 0 1px 3px rgba(0,0,0,0.4)`,
        transition: 'box-shadow 0.2s ease, border-color 0.2s ease',
        fontFamily: "'JetBrains Mono', monospace",
      }}
      onMouseEnter={(e) => {
        if (onSelect) {
          e.currentTarget.style.borderColor = color;
          e.currentTarget.style.borderLeftColor = color;
          const r = parseInt(color.slice(1, 3), 16);
          const g = parseInt(color.slice(3, 5), 16);
          const b = parseInt(color.slice(5, 7), 16);
          e.currentTarget.style.boxShadow = `0 4px 20px rgba(${r}, ${g}, ${b}, 0.25), 0 1px 4px rgba(0,0,0,0.5)`;
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border-subtle)';
        e.currentTarget.style.borderLeftColor = color;
        e.currentTarget.style.boxShadow = `0 2px 12px ${glow}, 0 1px 3px rgba(0,0,0,0.4)`;
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 6, height: 6, background: color, border: 'none', opacity: 0 }}
      />

      {/* VLAN name */}
      <div
        style={{
          fontSize: 12,
          fontWeight: 700,
          color: 'var(--text-primary)',
          lineHeight: 1.3,
        }}
      >
        {subnet.name}
      </div>

      {/* VLAN ID + CIDR */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          marginTop: 4,
        }}
      >
        <span
          style={{
            fontSize: 10,
            fontWeight: 600,
            color,
            background: glow,
            padding: '1px 6px',
            borderRadius: 3,
            border: `1px solid ${color}`,
          }}
        >
          VLAN {subnet.vlan}
        </span>
        <span
          style={{
            fontSize: 10,
            color: 'var(--text-muted)',
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
          marginTop: 8,
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
        {subnet.device_count} device{subnet.device_count !== 1 ? 's' : ''}
      </div>

      {/* Gateway label */}
      <div
        style={{
          fontSize: 9,
          color: 'var(--text-muted)',
          marginTop: 6,
          letterSpacing: '0.04em',
        }}
      >
        GW {subnet.gateway}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 6, height: 6, background: color, border: 'none', opacity: 0 }}
      />
    </div>
  );
};

/* ---------- Node type registrations ---------- */

const nodeTypes = {
  gatewayNode: GatewayNode,
  vlanBlockNode: VlanBlockNode,
};

/* ---------- Layout helper ---------- */

function buildL3Graph(
  topology: L3Topology,
  onSelectVlan?: (vlanId: number) => void,
): { nodes: RFNode[]; edges: RFEdge[] } {
  const nodes: RFNode[] = [];
  const edges: RFEdge[] = [];

  // Gateway node at top center
  const subnets = topology.subnets;
  const cols = Math.min(subnets.length, 3);
  const totalWidth = cols * 220;

  nodes.push({
    id: 'gateway',
    type: 'gatewayNode',
    position: { x: totalWidth / 2 - 80, y: 0 },
    data: { label: 'FortiGate' },
    draggable: true,
  });

  // VLAN blocks in a grid
  const CARD_W = 200;
  const H_GAP = 20;
  const V_GAP = 40;
  const TOP_OFFSET = 160;

  subnets.forEach((subnet, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = col * (CARD_W + H_GAP);
    const y = TOP_OFFSET + row * (140 + V_GAP);

    nodes.push({
      id: subnet.id,
      type: 'vlanBlockNode',
      position: { x, y },
      data: { subnet, onSelect: onSelectVlan },
      draggable: true,
    });

    // Edge from gateway to each subnet
    edges.push({
      id: `gw-${subnet.id}`,
      source: 'gateway',
      target: subnet.id,
      style: {
        stroke: getVlanColor(subnet.vlan),
        strokeWidth: 2,
        opacity: 0.5,
      },
      animated: true,
    });
  });

  // Inter-VLAN routing policy edges
  topology.routes.forEach((route, i) => {
    // Only add edges between subnets (not gateway routes)
    if (route.from_subnet !== 'gateway' && route.to_subnet !== 'gateway') {
      const isAllow = route.policy === 'allow';
      edges.push({
        id: `route-${i}`,
        source: route.from_subnet,
        target: route.to_subnet,
        style: {
          stroke: isAllow ? 'var(--accent-green)' : 'var(--accent-red)',
          strokeWidth: 1.5,
          strokeDasharray: '6 4',
          opacity: 0.6,
        },
        label: isAllow ? undefined : 'X',
        labelStyle: {
          fill: 'var(--accent-red)',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 12,
          fontWeight: 700,
        },
        labelBgStyle: {
          fill: 'var(--bg-primary)',
          fillOpacity: 0.8,
        },
        labelBgPadding: [4, 4] as [number, number],
        labelBgBorderRadius: 3,
      });
    }
  });

  return { nodes, edges };
}

/* ---------- Main Component ---------- */

const L3View: React.FC<L3ViewProps> = ({ topology, onSelectVlan }) => {
  const graph = useMemo(() => {
    if (!topology) return { nodes: [], edges: [] };
    return buildL3Graph(topology, onSelectVlan);
  }, [topology, onSelectVlan]);

  const handlePaneClick = useCallback(() => {
    // no-op, could deselect in future
  }, []);

  if (!topology) {
    return (
      <div
        className="flex items-center justify-center h-full"
        style={{ fontFamily: "'JetBrains Mono', monospace", color: 'var(--text-muted)' }}
      >
        NO L3 DATA AVAILABLE
      </div>
    );
  }

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={graph.nodes}
        edges={graph.edges}
        nodeTypes={nodeTypes}
        onPaneClick={handlePaneClick}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        minZoom={0.3}
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
          style={{ bottom: 16, left: 16 }}
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
        }}
      >
        <div
          style={{
            fontSize: 10,
            fontWeight: 600,
            color: 'var(--text-muted)',
            letterSpacing: '0.1em',
            marginBottom: 6,
          }}
        >
          ROUTING
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
          <div
            style={{
              width: 20,
              height: 0,
              borderTop: '2px dashed var(--accent-green)',
            }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>Allow</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <div
            style={{
              width: 20,
              height: 0,
              borderTop: '2px dashed var(--accent-red)',
            }}
          />
          <span style={{ color: 'var(--text-secondary)' }}>Deny</span>
        </div>
      </div>
    </div>
  );
};

export default L3View;
