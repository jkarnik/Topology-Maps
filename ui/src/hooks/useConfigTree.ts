import { useCallback, useEffect, useState } from 'react';
import type { ConfigTree } from '../types/config';
import { getTree } from '../api/config';

export function useConfigTree(orgId: string | null) {
  const [tree, setTree] = useState<ConfigTree | null>(null);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(() => {
    if (!orgId) return;
    setLoading(true);
    getTree(orgId).then(setTree).finally(() => setLoading(false));
  }, [orgId]);

  useEffect(() => { reload(); }, [reload]);

  return { tree, loading, reload };
}
