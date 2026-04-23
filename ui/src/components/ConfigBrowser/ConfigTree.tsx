import React, { useState } from 'react';
import type { ConfigTree as ConfigTreeData, EntityType } from '../../types/config';

interface Props {
  tree: ConfigTreeData | null;
  loading: boolean;
  onSelect: (entityType: EntityType, entityId: string) => void;
  selected: { entityType: EntityType; entityId: string } | null;
}

const MONO: React.CSSProperties = { fontFamily: "'JetBrains Mono', monospace" };

const caret = (open: boolean) => (open ? '▾' : '▸');

export const ConfigTree: React.FC<Props> = ({ tree, loading, onSelect, selected }) => {
  const [openNetworks, setOpenNetworks] = useState<Set<string>>(new Set());

  if (loading) {
    return (
      <div style={{ padding: '14px', fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>
        Loading…
      </div>
    );
  }
  if (!tree) {
    return (
      <div style={{ padding: '14px', fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>
        No data yet.
      </div>
    );
  }

  const isSelected = (t: EntityType, id: string) =>
    selected?.entityType === t && selected.entityId === id;

  const rowStyle = (t: EntityType, id: string): React.CSSProperties => ({
    cursor: 'pointer',
    padding: '5px 10px',
    borderRadius: '4px',
    fontSize: '12px',
    color: isSelected(t, id) ? 'var(--accent-amber)' : 'var(--text-primary)',
    background: isSelected(t, id) ? 'var(--accent-amber-glow)' : 'transparent',
    fontWeight: isSelected(t, id) ? 600 : 400,
    transition: 'background 0.1s ease',
  });

  const sectionLabelStyle: React.CSSProperties = {
    marginTop: '12px',
    marginBottom: '6px',
    fontSize: '10px',
    letterSpacing: '0.1em',
    textTransform: 'uppercase',
    color: 'var(--text-muted)',
    fontWeight: 600,
  };

  const toggleNetwork = (id: string) => {
    setOpenNetworks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div style={{ padding: '10px 8px', overflowY: 'auto', height: '100%', ...MONO }}>
      <div style={sectionLabelStyle}>Org configs</div>
      <div
        style={rowStyle('org', tree.org.id)}
        onClick={() => onSelect('org', tree.org.id)}
        onMouseEnter={(e) => {
          if (!isSelected('org', tree.org.id)) {
            (e.currentTarget as HTMLElement).style.background = 'var(--bg-tertiary)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isSelected('org', tree.org.id)) {
            (e.currentTarget as HTMLElement).style.background = 'transparent';
          }
        }}
      >
        {tree.org.id}
        <span style={{ marginLeft: '8px', color: 'var(--text-muted)' }}>
          ({tree.org.config_areas.length} areas)
        </span>
      </div>

      <div style={sectionLabelStyle}>Networks</div>
      {tree.networks.length === 0 && (
        <div style={{ padding: '5px 10px', fontSize: '11px', color: 'var(--text-muted)' }}>
          No networks yet.
        </div>
      )}
      {tree.networks.map((net) => {
        const open = openNetworks.has(net.id);
        return (
          <div key={net.id}>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                cursor: 'pointer',
                padding: '3px 4px',
              }}
              onClick={() => toggleNetwork(net.id)}
            >
              <span style={{ width: '14px', color: 'var(--text-muted)', fontSize: '11px' }}>
                {caret(open)}
              </span>
              <span
                style={{ flex: 1, ...rowStyle('network', net.id) }}
                onClick={(e) => { e.stopPropagation(); onSelect('network', net.id); }}
                onMouseEnter={(e) => {
                  if (!isSelected('network', net.id)) {
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-tertiary)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected('network', net.id)) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {net.name ?? net.id}
                <span style={{ marginLeft: '8px', color: 'var(--text-muted)' }}>
                  ({net.config_areas.length})
                </span>
              </span>
            </div>
            {open && net.devices.map((d) => (
              <div
                key={d.serial}
                style={{ ...rowStyle('device', d.serial), marginLeft: '24px' }}
                onClick={() => onSelect('device', d.serial)}
                onMouseEnter={(e) => {
                  if (!isSelected('device', d.serial)) {
                    (e.currentTarget as HTMLElement).style.background = 'var(--bg-tertiary)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isSelected('device', d.serial)) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {d.name ?? d.serial}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};
