/**
 * Persist the Meraki topology cache to localStorage so that a full page
 * reload does not trigger any Meraki API calls.  Only the Refresh button
 * should produce network traffic.
 *
 * The payload is version-tagged so future schema changes can be rejected
 * cleanly without crashing the UI.
 */

import type { L2Topology, L3Topology } from '../types/topology';
import type { MerakiNetwork, MerakiDeviceDetail } from '../types/meraki';

const STORAGE_KEY = 'meraki-topology-cache';
/**
 * Cache schema version.  Bumped to 2 when per-device detail (clients +
 * switch ports) was added to the per-network payload.  Mismatched
 * versions are discarded on load so stale payloads can't crash the UI.
 */
export const SCHEMA_VERSION = 2;

export interface CachedNetwork {
  l2: L2Topology;
  l3: L3Topology;
  /** Serial-keyed map of per-device detail shown in the right-hand panel. */
  deviceDetails: Record<string, MerakiDeviceDetail>;
}

export interface MerakiCacheSnapshot {
  version: number;
  orgName: string | null;
  networks: MerakiNetwork[];
  selectedNetwork: string | null;
  topology: Record<string, CachedNetwork>;
  lastUpdated: string | null; // ISO 8601
}

export function loadCache(): MerakiCacheSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as MerakiCacheSnapshot;
    if (parsed.version !== SCHEMA_VERSION) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveCache(snapshot: Omit<MerakiCacheSnapshot, 'version'>): void {
  try {
    const payload: MerakiCacheSnapshot = { version: SCHEMA_VERSION, ...snapshot };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
  } catch (err) {
    // Quota exceeded, private mode, or other storage failures — skip silently.
    console.warn('Failed to persist Meraki cache:', err);
  }
}

export function clearCache(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // No-op.
  }
}
