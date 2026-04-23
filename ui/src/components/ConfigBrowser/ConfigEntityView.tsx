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

export const ConfigEntityView: React.FC<Props> = ({ orgId, entityType, entityId }) => {
  const { entity, loading, reload } = useConfigEntity(orgId, entityType, entityId);
  const [refreshingArea, setRefreshingArea] = useState<string | null>(null);

  if (loading && !entity) return <div className="text-sm text-gray-500">Loading…</div>;
  if (!entity) return <div className="text-sm text-gray-500">No data for this entity yet.</div>;

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
    <div>
      <div className="mb-4">
        <div className="text-xs uppercase tracking-wide text-gray-500">{entityType}</div>
        <div className="text-xl font-semibold">{entityId}</div>
      </div>
      {entity.areas.length === 0
        ? <div className="text-sm text-gray-500">No observations yet. Try running a baseline.</div>
        : entity.areas.map((area) => (
            <ConfigAreaViewer
              key={`${area.config_area}:${area.sub_key ?? ''}`}
              area={area}
              onRefresh={() => handleRefresh(area.config_area)}
              refreshing={refreshingArea === area.config_area}
            />
          ))
      }
    </div>
  );
};
