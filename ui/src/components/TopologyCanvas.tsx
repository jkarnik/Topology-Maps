import { useCallback, useMemo, useEffect } from 'react';
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  type NodeMouseHandler,
  type OnConnect,
  type EdgeMouseHandler,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import DeviceNode from './DeviceNode';
import { ConnectionEdge } from './ConnectionEdge';
import { layoutL2Topology } from '../utils/layoutEngine';
import type { L2Topology, Device, DrillDownState } from '../types/topology';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyEdgeComponent = React.ComponentType<any>;

/* ---------- Props ---------- */

interface TopologyCanvasProps {
  topology: L2Topology | null;
  selectedDevice: Device | null;
  onSelectDevice: (device: Device | null) => void;
  drillDown: DrillDownState;
  onDrillInto: (deviceId: string, label: string) => void;
  onDrillBack: (index: number) => void;
  onDrillReset: () => void;
  editMode?: boolean;
  onEditConnect?: (source: string, target: string) => void;
  onEditDisconnect?: (edgeId: string, source: string, target: string) => void;
  deviceAnimations?: Map<string, 'new' | 'removing'>;
  pinnedDeviceIds?: Set<string>;
}

/* ---------- Custom type registrations (outside component to avoid re-renders) ---------- */

const nodeTypes = { deviceNode: DeviceNode };
const edgeTypes = { connectionEdge: ConnectionEdge as AnyEdgeComponent };

/* ---------- Drillable device types ---------- */

const DRILLABLE_TYPES = new Set(['floor_switch', 'access_point']);

/* ---------- Component ---------- */

export default function TopologyCanvas({
  topology,
  selectedDevice: _selectedDevice,
  onSelectDevice,
  drillDown,
  onDrillInto,
  onDrillBack,
  onDrillReset,
  editMode = false,
  onEditConnect,
  onEditDisconnect,
  deviceAnimations,
  pinnedDeviceIds,
}: TopologyCanvasProps) {
  // Compute layout whenever topology or drill-down state changes
  const layoutResult = useMemo(() => {
    if (!topology) return { nodes: [], edges: [] };
    const result = layoutL2Topology(topology, drillDown.currentDeviceId, pinnedDeviceIds);

    // Inject animationState into each node's data
    if (deviceAnimations && deviceAnimations.size > 0) {
      return {
        ...result,
        nodes: result.nodes.map(n => ({
          ...n,
          data: {
            ...n.data,
            animationState: deviceAnimations.get(n.id) ?? null,
          },
        })),
      };
    }

    return result;
  }, [topology, drillDown.currentDeviceId, pinnedDeviceIds, deviceAnimations]);

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutResult.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutResult.edges);

  // Sync layout result into state when it changes
  useEffect(() => {
    setNodes(layoutResult.nodes);
    setEdges(layoutResult.edges);
  }, [layoutResult, setNodes, setEdges]);

  // Single click: select device for detail panel
  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      const device = (node.data as { device: Device }).device;
      onSelectDevice(device);
    },
    [onSelectDevice],
  );

  // Double-click: drill into floor switches and access points
  const handleNodeDoubleClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      const device = (node.data as { device: Device }).device;
      if (DRILLABLE_TYPES.has(device.type)) {
        onDrillInto(device.id, device.id);
      }
    },
    [onDrillInto],
  );

  // Click on empty canvas to deselect
  const handlePaneClick = useCallback(() => {
    onSelectDevice(null);
  }, [onSelectDevice]);

  // Edit mode: handle new connection via drag between handles
  const handleConnect: OnConnect = useCallback(
    (connection) => {
      if (!editMode || !onEditConnect) return;
      if (connection.source && connection.target) {
        onEditConnect(connection.source, connection.target);
      }
    },
    [editMode, onEditConnect],
  );

  // Edit mode: click edge to disconnect
  const handleEdgeClick: EdgeMouseHandler = useCallback(
    (_event, edge) => {
      if (!editMode || !onEditDisconnect) return;
      onEditDisconnect(edge.id, edge.source, edge.target);
    },
    [editMode, onEditDisconnect],
  );

  // MiniMap node color by device type
  const miniMapNodeColor = useCallback((node: { data: Record<string, unknown> }) => {
    const device = node.data.device as Device | undefined;
    if (!device) return 'var(--text-muted)';
    const colorMap: Record<string, string> = {
      firewall: 'var(--device-firewall)',
      core_switch: 'var(--device-core-switch)',
      floor_switch: 'var(--device-floor-switch)',
      access_point: 'var(--device-ap)',
      endpoint: 'var(--device-endpoint)',
    };
    return colorMap[device.type] ?? 'var(--text-muted)';
  }, []);

  const hasBreadcrumbs = drillDown.path.length > 0;

  return (
    <div
      className={`topology-canvas${editMode ? ' edit-mode-active' : ''}`}
      style={{ width: '100%', height: '100%' }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeClick={handleNodeClick}
        onNodeDoubleClick={handleNodeDoubleClick}
        onPaneClick={handlePaneClick}
        onConnect={handleConnect}
        onEdgeClick={handleEdgeClick}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        minZoom={0.15}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(136, 153, 170, 0.08)" />
        <Controls
          showInteractive={false}
          style={{ bottom: hasBreadcrumbs ? 56 : 16, left: 16 }}
        />
        <MiniMap
          nodeColor={miniMapNodeColor}
          maskColor="rgba(10, 14, 20, 0.85)"
          style={{ bottom: 16, right: 16 }}
          pannable
          zoomable
        />
      </ReactFlow>

      {/* Breadcrumb navigation */}
      {hasBreadcrumbs && (
        <div
          style={{
            position: 'absolute',
            bottom: 16,
            left: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 0,
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: 999,
            padding: '5px 14px',
            zIndex: 20,
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
          }}
        >
          {/* Overview (root) */}
          <span
            onClick={onDrillReset}
            style={{
              color: 'var(--text-secondary)',
              cursor: 'pointer',
              transition: 'color 0.15s ease',
              userSelect: 'none',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLSpanElement).style.color = 'var(--accent-cyan)';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLSpanElement).style.color = 'var(--text-secondary)';
            }}
          >
            Overview
          </span>

          {drillDown.path.map((crumb, index) => {
            const isLast = index === drillDown.path.length - 1;
            return (
              <span key={crumb.id} style={{ display: 'flex', alignItems: 'center' }}>
                <span
                  style={{
                    color: 'var(--text-muted)',
                    margin: '0 6px',
                    fontSize: 10,
                    userSelect: 'none',
                  }}
                >
                  &gt;
                </span>
                <span
                  onClick={() => {
                    if (!isLast) onDrillBack(index);
                  }}
                  style={{
                    color: isLast ? 'var(--text-primary)' : 'var(--text-secondary)',
                    cursor: isLast ? 'default' : 'pointer',
                    fontWeight: isLast ? 600 : 400,
                    transition: 'color 0.15s ease',
                    userSelect: 'none',
                  }}
                  onMouseEnter={(e) => {
                    if (!isLast) {
                      (e.currentTarget as HTMLSpanElement).style.color = 'var(--accent-cyan)';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isLast) {
                      (e.currentTarget as HTMLSpanElement).style.color = 'var(--text-secondary)';
                    }
                  }}
                >
                  {crumb.label}
                </span>
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
