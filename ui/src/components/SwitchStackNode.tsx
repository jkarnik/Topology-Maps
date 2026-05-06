import React, { useState, useCallback } from 'react';
import { Handle, Position, useUpdateNodeInternals, type NodeProps } from '@xyflow/react';
import type { Device, DeviceStatus } from '../types/topology';

export const stackStatusColor: Record<DeviceStatus, string> = {
  up: 'var(--accent-green)',
  down: 'var(--accent-red)',
  degraded: 'var(--accent-amber)',
  alerting: 'var(--accent-amber)',
};

export const StackIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--device-floor-switch)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="5" rx="1.5" />
    <rect x="2" y="9.5" width="20" height="5" rx="1.5" />
    <rect x="2" y="16" width="20" height="5" rx="1.5" />
    <circle cx="6" cy="5.5" r="0.6" fill="var(--device-floor-switch)" />
    <circle cx="6" cy="12" r="0.6" fill="var(--device-floor-switch)" />
    <circle cx="6" cy="18.5" r="0.6" fill="var(--device-floor-switch)" />
  </svg>
);

export const StackMemberIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--device-floor-switch)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="6" width="20" height="5" rx="1.5" />
    <rect x="2" y="13" width="20" height="5" rx="1.5" />
    <circle cx="6" cy="8.5" r="0.5" fill="var(--device-floor-switch)" />
    <circle cx="6" cy="15.5" r="0.5" fill="var(--device-floor-switch)" />
  </svg>
);

export type SwitchStackNodeData = {
  stackName: string;
  members: Device[];
  onSelectMember?: (device: Device | null) => void;
};

const SwitchStackNode: React.FC<NodeProps> = ({ id, data }) => {
  const { stackName, members, onSelectMember } = data as SwitchStackNodeData;
  const [expanded, setExpanded] = useState(false);
  const updateNodeInternals = useUpdateNodeInternals();

  const color = 'var(--device-floor-switch)';
  const glow = 'rgba(245, 166, 35, 0.15)';
  const hoverGlow = 'rgba(245, 166, 35, 0.35)';

  const toggleExpand = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setExpanded((prev) => !prev);
      setTimeout(() => updateNodeInternals(id), 0);
    },
    [id, updateNodeInternals],
  );

  return (
    <div
      style={{
        position: 'relative',
        width: 220,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      <Handle
        type="target"
        position={Position.Top}
        style={{ width: 6, height: 6, background: color, border: 'none', opacity: 0 }}
      />
      <div
        style={{
          background: 'var(--bg-elevated)',
          border: `2px solid ${color}`,
          borderRadius: 5,
          boxShadow: `0 2px 14px ${glow}, 0 1px 3px rgba(0,0,0,0.4)`,
          overflow: 'hidden',
          transition: 'box-shadow 0.2s ease',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.boxShadow = `0 4px 24px ${hoverGlow}, 0 1px 4px rgba(0,0,0,0.5)`;
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLDivElement).style.boxShadow = `0 2px 14px ${glow}, 0 1px 3px rgba(0,0,0,0.4)`;
        }}
      >
        {/* Header — click to expand/collapse */}
        <div
          onClick={toggleExpand}
          style={{
            padding: '12px 16px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 10,
          }}
        >
          <div style={{ flexShrink: 0, marginTop: 2 }}>
            <StackIcon />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                fontSize: 12,
                fontWeight: 700,
                color: 'var(--text-primary)',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                paddingRight: 8,
                lineHeight: 1.3,
              }}
            >
              {stackName}
            </div>
            <div
              style={{
                fontSize: 10,
                color: 'var(--text-secondary)',
                marginTop: 2,
                lineHeight: 1.4,
              }}
            >
              {members.length} switch{members.length !== 1 ? 'es' : ''} · stacked
            </div>
            <div style={{ display: 'flex', gap: 4, marginTop: 6 }}>
              {members.map((m) => (
                <div
                  key={m.id}
                  title={`${m.name || m.id}: ${m.status}`}
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: stackStatusColor[m.status],
                    boxShadow: `0 0 4px ${stackStatusColor[m.status]}`,
                  }}
                />
              ))}
            </div>
          </div>
          <div
            style={{
              flexShrink: 0,
              color: 'var(--text-muted)',
              fontSize: 10,
              marginTop: 2,
              transition: 'transform 0.2s',
              transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)',
            }}
          >
            ▾
          </div>
        </div>

        {/* Expanded member list */}
        {expanded && (
          <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
            {members.map((m, i) => (
              <div
                key={m.id}
                onClick={(e) => {
                  e.stopPropagation();
                  onSelectMember?.(m);
                }}
                style={{
                  padding: '8px 16px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: onSelectMember ? 'pointer' : 'default',
                  borderBottom: i < members.length - 1 ? '1px solid var(--border-subtle)' : 'none',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => {
                  if (onSelectMember)
                    (e.currentTarget as HTMLDivElement).style.background = 'rgba(245,166,35,0.06)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLDivElement).style.background = 'transparent';
                }}
              >
                <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center' }}>
                  <StackMemberIcon />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 11,
                      fontWeight: 600,
                      color: 'var(--text-primary)',
                      whiteSpace: 'nowrap',
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      lineHeight: 1.3,
                    }}
                  >
                    {m.name || m.id}
                  </div>
                  <div
                    style={{
                      fontSize: 9,
                      color: 'var(--text-muted)',
                      whiteSpace: 'nowrap',
                      lineHeight: 1.4,
                      marginTop: 1,
                    }}
                  >
                    {m.model}
                  </div>
                </div>
                {m.stack_role === 'active' && (
                  <span
                    style={{
                      fontSize: 8,
                      fontWeight: 700,
                      color: 'var(--accent-green)',
                      background: 'rgba(0,214,143,0.1)',
                      padding: '1px 5px',
                      borderRadius: 3,
                      border: '1px solid var(--accent-green)',
                      flexShrink: 0,
                      letterSpacing: '0.05em',
                    }}
                  >
                    ACTIVE
                  </span>
                )}
                <div
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: stackStatusColor[m.status],
                    boxShadow: `0 0 4px ${stackStatusColor[m.status]}`,
                    flexShrink: 0,
                  }}
                />
              </div>
            ))}
          </div>
        )}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        style={{ width: 6, height: 6, background: color, border: 'none', opacity: 0 }}
      />
    </div>
  );
};

SwitchStackNode.displayName = 'SwitchStackNode';
export default SwitchStackNode;
