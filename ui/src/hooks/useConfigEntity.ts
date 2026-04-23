import { useCallback, useEffect, useState } from 'react';
import type { ConfigEntity, EntityType } from '../types/config';
import { getEntity } from '../api/config';

export function useConfigEntity(
  orgId: string | null,
  entityType: EntityType | null,
  entityId: string | null,
) {
  const [entity, setEntity] = useState<ConfigEntity | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(() => {
    if (!orgId || !entityType || !entityId) { setEntity(null); return; }
    setLoading(true);
    getEntity(orgId, entityType, entityId).then(setEntity).finally(() => setLoading(false));
  }, [orgId, entityType, entityId]);

  useEffect(() => { reload(); }, [reload]);

  return { entity, loading, reload };
}
