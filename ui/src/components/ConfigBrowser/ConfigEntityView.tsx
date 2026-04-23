import React, { useState } from 'react';
import { ConfigAreaViewer } from './ConfigAreaViewer';
import { useConfigEntity } from '../../hooks/useConfigEntity';
import { refresh } from '../../api/config';
import type { EntityType } from '../../types/config';

interface Props {
  orgId: string;
  entityType: EntityType;
  entityId: string;
}

const MONO: React.CSSProperties = { fontFamily: "'JetBrains Mono', monospace" };

/**
 * True when a payload has no meaningful configuration to display.
 *
 * Treated as empty:
 *   null / undefined
 *   []
 *   {}
 *   objects where EVERY value is recursively empty (e.g. {"rules": []})
 *
 * Treated as NOT empty:
 *   any primitive (string/number/boolean including "", 0, false)
 *   any array with at least one item
 *   objects containing a redaction sentinel ({_redacted: true, _hash: "..."})
 *   objects with at least one non-empty value
 */
function isEmptyPayload(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  if (typeof value === 'object') {
    const obj = value as Record<string, unknown>;
    if (obj._redacted === true) return false;
    const keys = Object.keys(obj);
    if (keys.length === 0) return true;
    return keys.every((k) => isEmptyPayload(obj[k]));
  }
  // Primitive (string, number, boolean)
  return false;
}

export const ConfigEntityView: React.FC<Props> = ({ orgId, entityType, entityId }) => {
  const { entity, loading, reload } = useConfigEntity(orgId, entityType, entityId);
  const [refreshingArea, setRefreshingArea] = useState<string | null>(null);

  if (loading && !entity) {
    return (
      <div style={{ fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>Loading…</div>
    );
  }
  if (!entity) {
    return (
      <div style={{ fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>
        No data for this entity yet.
      </div>
    );
  }

  const handleRefresh = async (configArea: string) => {
    setRefreshingArea(configArea);
    try {
      await refresh(orgId, { entity_type: entityType, entity_id: entityId, config_area: configArea });
      reload();
    } finally {
      setRefreshingArea(null);
    }
  };

  return (
    <div style={{ color: 'var(--text-primary)' }}>
      <div style={{ marginBottom: '18px' }}>
        <div
          style={{
            fontSize: '10px',
            letterSpacing: '0.12em',
            textTransform: 'uppercase',
            color: 'var(--text-muted)',
            marginBottom: '4px',
            ...MONO,
          }}
        >
          {entityType}
        </div>
        <div
          style={{
            fontSize: '18px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            ...MONO,
          }}
        >
          {entityId}
        </div>
      </div>
      {entity.areas.length === 0 ? (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', ...MONO }}>
          No observations yet. Try running a baseline.
        </div>
      ) : (() => {
        const visible = entity.areas.filter((a) => !isEmptyPayload(a.payload));
        const hiddenCount = entity.areas.length - visible.length;
        return (
          <>
            {visible.map((area) => (
              <ConfigAreaViewer
                key={`${area.config_area}:${area.sub_key ?? ''}`}
                area={area}
                onRefresh={() => handleRefresh(area.config_area)}
                refreshing={refreshingArea === area.config_area}
              />
            ))}
            {hiddenCount > 0 && (
              <div
                style={{
                  marginTop: '16px',
                  padding: '10px 12px',
                  fontSize: '10px',
                  letterSpacing: '0.08em',
                  color: 'var(--text-muted)',
                  textTransform: 'uppercase',
                  fontFamily: "'JetBrains Mono', monospace",
                  border: '1px dashed var(--border-subtle)',
                  borderRadius: '6px',
                }}
              >
                {hiddenCount} empty area{hiddenCount === 1 ? '' : 's'} hidden
              </div>
            )}
          </>
        );
      })()}
    </div>
  );
};
