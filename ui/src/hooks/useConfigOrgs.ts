import { useEffect, useState } from 'react';
import type { ConfigOrg } from '../types/config';
import { listOrgs } from '../api/config';

export function useConfigOrgs(pollMs: number = 30000) {
  const [orgs, setOrgs] = useState<ConfigOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let alive = true;
    const tick = () => {
      listOrgs()
        .then((o) => { if (alive) { setOrgs(o); setLoading(false); } })
        .catch((e) => { if (alive) { setError(e); setLoading(false); } });
    };
    tick();
    const id = setInterval(tick, pollMs);
    return () => { alive = false; clearInterval(id); };
  }, [pollMs]);

  return { orgs, loading, error };
}
