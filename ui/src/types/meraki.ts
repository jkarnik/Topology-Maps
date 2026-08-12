export interface MerakiNetwork {
  id: string;
  name: string;
  productTypes: string[];
}

export interface MerakiStatus {
  configured: boolean;
  org_id?: string;
  org_name?: string;
  error?: string;
}

export type RefreshPhase = 'discovery' | 'devices' | 'topology' | 'clients' | 'complete';

export interface RefreshProgress {
  phase: RefreshPhase;
  device_count?: number;
  network_count?: number;
  estimated_seconds?: number;
  nodes?: Record<string, unknown>[];
  edges?: Record<string, unknown>[];
  network?: string;
  progress?: number;
  total?: number;
  remaining_seconds?: number;
  client_counts?: Record<string, number>;
  l2?: Record<string, unknown>;
  l3?: Record<string, unknown>;
}

/**
 * Per-device detail pre-fetched during refresh and shown in the right-hand
 * MerakiDetailPanel.  Mirrors the response shape of
 * `GET /api/meraki/devices/{serial}`.
 */
export interface MerakiDeviceDetail {
  serial: string;
  clients: Record<string, unknown>[];
  switch_ports: Record<string, unknown>[];
}

export type HealthBucket = 'green' | 'yellow' | 'orange' | 'red' | 'unknown';

/**
 * One aggregated entry per Meraki network for the world map landing view.
 * Mirrors the backend `Site` model (server/models.py).
 */
export interface MerakiSite {
  network_id: string;
  name: string;
  lat: number | null;
  lng: number | null;
  device_count: number;
  health_bucket: HealthBucket;
  unhealthy_pct: number | null;
  mapped: boolean;
}
