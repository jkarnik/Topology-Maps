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
      ) : (
        entity.areas.map((area) => (
          <ConfigAreaViewer
            key={`${area.config_area}:${area.sub_key ?? ''}`}
            area={area}
            onRefresh={() => handleRefresh(area.config_area)}
            refreshing={refreshingArea === area.config_area}
          />
        ))
      )}
    </div>
  );
};
