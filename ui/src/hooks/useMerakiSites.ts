import { useState, useCallback, useRef } from 'react';
import { MerakiSite } from '../types/meraki';
import { loadSitesCache, saveSitesCache } from '../lib/merakiSitesCache';

export interface UseMerakiSitesReturn {
  sites: MerakiSite[];
  isLoading: boolean;
  error: string | null;
  hasFetched: boolean;
  lastUpdated: Date | null;
  /**
   * Try localStorage (synchronous, already applied by the time this hook
   * returns), then the server-side seed snapshot. Returns true if either
   * produced data — callers should skip `refresh()` in that case.
   */
  loadCached: () => Promise<boolean>;
  /** Hit the live Meraki API and persist the result to both caches. */
  refresh: () => Promise<void>;
}

export function useMerakiSites(): UseMerakiSitesReturn {
  const bootCacheRef = useRef<ReturnType<typeof loadSitesCache> | undefined>(undefined);
  if (bootCacheRef.current === undefined) bootCacheRef.current = loadSitesCache();
  const bootCache = bootCacheRef.current;

  const [sites, setSites] = useState<MerakiSite[]>(bootCache?.sites ?? []);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasFetched, setHasFetched] = useState(!!bootCache);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(
    bootCache?.lastUpdated ? new Date(bootCache.lastUpdated) : null,
  );

  const loadCached = useCallback(async (): Promise<boolean> => {
    // An empty snapshot is not a hit — reporting success on `{sites: []}` would
    // strand the caller on an empty cache instead of falling through to refresh().
    if (bootCache && bootCache.sites.length > 0) return true; // hydrated synchronously above
    try {
      const resp = await fetch('/api/meraki/sites/cache/load', { cache: 'no-store' });
      if (!resp.ok) return false;
      const data = (await resp.json()) as { sites: MerakiSite[] };
      const nextSites = data.sites ?? [];
      setSites(nextSites);
      setHasFetched(true);
      return nextSites.length > 0;
    } catch {
      return false;
    }
  }, [bootCache]);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await fetch('/api/meraki/sites');
      if (!resp.ok) throw new Error(`Failed to fetch sites: ${resp.status}`);
      const data = (await resp.json()) as { sites: MerakiSite[] };
      const nextSites = data.sites ?? [];
      const now = new Date();
      setSites(nextSites);
      setLastUpdated(now);
      saveSitesCache({ sites: nextSites, lastUpdated: now.toISOString() });
      fetch('/api/meraki/sites/cache/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sites: nextSites }),
      }).catch(() => {
        /* best-effort server snapshot — localStorage already has it */
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch sites');
    } finally {
      setIsLoading(false);
      setHasFetched(true);
    }
  }, []);

  return { sites, isLoading, error, hasFetched, lastUpdated, loadCached, refresh };
}
