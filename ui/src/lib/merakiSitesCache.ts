/**
 * Persist the Meraki sites list (world map landing view) to localStorage,
 * independent of the per-network topology cache in merakiCache.ts — sites
 * have a different lifecycle (fetched once on landing) and a much lighter
 * payload, so keeping the cache separate avoids the two caches racing to
 * overwrite the same localStorage entry.
 */

import type { MerakiSite } from '../types/meraki';

const STORAGE_KEY = 'meraki-sites-cache';
export const SITES_SCHEMA_VERSION = 1;

export interface MerakiSitesCacheSnapshot {
  version: number;
  sites: MerakiSite[];
  lastUpdated: string | null;
}

export function loadSitesCache(): MerakiSitesCacheSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MerakiSitesCacheSnapshot;
    if (parsed.version !== SITES_SCHEMA_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveSitesCache(snapshot: Omit<MerakiSitesCacheSnapshot, 'version'>): void {
  try {
    const payload: MerakiSitesCacheSnapshot = { version: SITES_SCHEMA_VERSION, ...snapshot };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch (err) {
    console.warn('Failed to persist Meraki sites cache:', err);
  }
}
