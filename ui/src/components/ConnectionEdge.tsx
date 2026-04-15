import { EdgeProps, Edge, getBezierPath, EdgeLabelRenderer } from '@xyflow/react';
import { Edge as TopologyEdge } from '../types/topology';

export type ConnectionEdgeData = {
  edge: TopologyEdge;
};

const PROTOCOL_COLOR: Record<TopologyEdge['protocol'], string> = {
  LLDP: 'var(--accent-cyan)',
  ARP: 'var(--text-muted)',
  wireless: 'var(--accent-purple)',
  stack: 'var(--accent-green)',
};

const WIRELESS_ANIMATION_ID = 'connection-edge-wireless-dash';
const STACK_ANIMATION_ID = 'connection-edge-stack-dash';

function ensureWirelessAnimation() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(WIRELESS_ANIMATION_ID)) return;
  const style = document.createElement('style');
  style.id = WIRELESS_ANIMATION_ID;
  style.textContent = `
    @keyframes wireless-dash {
      from { stroke-dashoffset: 20; }
      to   { stroke-dashoffset: 0; }
    }
    .connection-edge-wireless {
      animation: wireless-dash 0.6s linear infinite;
    }
  `;
  document.head.appendChild(style);
}

function ensureStackAnimation() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STACK_ANIMATION_ID)) return;
  const style = document.createElement('style');
  style.id = STACK_ANIMATION_ID;
  style.textContent = `
    @keyframes stack-dash {
      from { stroke-dashoffset: 24; }
      to   { stroke-dashoffset: 0; }
    }
    .connection-edge-stack {
      animation: stack-dash 1.2s linear infinite;
    }
  `;
  document.head.appendChild(style);
}

export function ConnectionEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
}: EdgeProps<Edge<Record<string, unknown>>>) {
  const edge = (data as ConnectionEdgeData | undefined)?.edge;
  if (!edge) return null;

  const { protocol, source_port, target_port, speed } = edge;

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const color = PROTOCOL_COLOR[protocol as TopologyEdge['protocol']];
  const isWireless = protocol === 'wireless';
  const isLLDP = protocol === 'LLDP';
  const isStack = protocol === 'stack';

  if (isWireless) ensureWirelessAnimation();
  if (isStack) ensureStackAnimation();

  // Port label positions: ~18% and ~82% along the bezier
  // Approximate by lerping between source/target with a small offset
  const srcLabelX = sourceX + (targetX - sourceX) * 0.12;
  const srcLabelY = sourceY + (targetY - sourceY) * 0.12;
  const tgtLabelX = sourceX + (targetX - sourceX) * 0.88;
  const tgtLabelY = sourceY + (targetY - sourceY) * 0.88;

  return (
    <>
      <path
        id={id}
        className={isWireless ? 'connection-edge-wireless' : isStack ? 'connection-edge-stack' : undefined}
        d={edgePath}
        fill="none"
        stroke={color}
        strokeWidth={isLLDP ? 2 : 1.5}
        strokeOpacity={isLLDP ? 0.9 : 0.65}
        strokeDasharray={isWireless ? '6 4' : isStack ? '8 4' : undefined}
        style={{ pointerEvents: 'visibleStroke' }}
      />

      <EdgeLabelRenderer>
        {/* STACK badge — midpoint */}
        {isStack && (
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'none',
              zIndex: 10,
            }}
            className="nodrag nopan"
          >
            <span
              style={{
                display: 'inline-block',
                background: 'var(--bg-tertiary)',
                color: 'var(--accent-green)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '8px',
                fontWeight: 600,
                lineHeight: 1,
                padding: '2px 5px',
                borderRadius: '999px',
                border: '1px solid rgba(0, 214, 143, 0.2)',
                letterSpacing: '0.03em',
                whiteSpace: 'nowrap',
              }}
            >
              STACK
            </span>
          </div>
        )}

        {/* Speed badge — LLDP only, midpoint */}
        {isLLDP && speed && (
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'none',
              zIndex: 10,
            }}
            className="nodrag nopan"
          >
            <span
              style={{
                display: 'inline-block',
                background: 'var(--bg-tertiary)',
                color: 'var(--accent-cyan)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '8px',
                fontWeight: 600,
                lineHeight: 1,
                padding: '2px 5px',
                borderRadius: '999px',
                border: '1px solid rgba(0, 229, 200, 0.2)',
                letterSpacing: '0.03em',
                whiteSpace: 'nowrap',
              }}
            >
              {speed}
            </span>
          </div>
        )}

        {/* Source port label — LLDP only */}
        {isLLDP && source_port && (
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${srcLabelX}px, ${srcLabelY}px)`,
              pointerEvents: 'none',
              zIndex: 10,
            }}
            className="nodrag nopan"
          >
            <span
              style={{
                display: 'inline-block',
                background: 'var(--bg-elevated)',
                color: 'var(--text-muted)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '9px',
                fontWeight: 400,
                lineHeight: 1,
                padding: '2px 4px',
                borderRadius: '3px',
                whiteSpace: 'nowrap',
              }}
            >
              {source_port}
            </span>
          </div>
        )}

        {/* Target port label — LLDP only */}
        {isLLDP && target_port && (
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${tgtLabelX}px, ${tgtLabelY}px)`,
              pointerEvents: 'none',
              zIndex: 10,
            }}
            className="nodrag nopan"
          >
            <span
              style={{
                display: 'inline-block',
                background: 'var(--bg-elevated)',
                color: 'var(--text-muted)',
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '9px',
                fontWeight: 400,
                lineHeight: 1,
                padding: '2px 4px',
                borderRadius: '3px',
                whiteSpace: 'nowrap',
              }}
            >
              {target_port}
            </span>
          </div>
        )}
      </EdgeLabelRenderer>
    </>
  );
}
