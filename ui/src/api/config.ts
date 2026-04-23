// Thin fetch wrappers for /api/config/* (Plan 1.19)
import type {
  ConfigOrg, ConfigStatus, ConfigEntity, ConfigTree, ConfigChangeEvent,
  ConfigObservation, EntityType, OrgDiffResponse, EntityTimelineResponse,
} from '../types/config';

const BASE = '/api/config';

async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${path}`);
  return res.json();
}

export function listOrgs(): Promise<ConfigOrg[]> {
  return _fetch('/orgs');
}

export function getStatus(orgId: string): Promise<ConfigStatus> {
  return _fetch(`/orgs/${orgId}/status`);
}

export function startBaseline(orgId: string): Promise<{ sweep_run_id: number }> {
  return _fetch(`/orgs/${orgId}/baseline`, { method: 'POST' });
}

export function startSweep(orgId: string): Promise<{ sweep_run_id: number }> {
  return _fetch(`/orgs/${orgId}/sweep`, { method: 'POST' });
}

export function refresh(orgId: string, body: {
  entity_type: EntityType; entity_id: string; config_area?: string;
}): Promise<{ task_id: number; expected_calls: number }> {
  return _fetch(`/orgs/${orgId}/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function getTree(orgId: string): Promise<ConfigTree> {
  return _fetch(`/orgs/${orgId}/tree`);
}

export function getEntity(orgId: string, entityType: EntityType, entityId: string): Promise<ConfigEntity> {
  return _fetch(`/entities/${entityType}/${entityId}?org_id=${orgId}`);
}

export function getHistory(orgId: string, entityType: EntityType, entityId: string, opts?: {
  config_area?: string; limit?: number; before?: string;
}): Promise<{ observations: ConfigObservation[]; has_more: boolean; next_cursor: string | null }> {
  const qs = new URLSearchParams({ org_id: orgId });
  if (opts?.config_area) qs.set('config_area', opts.config_area);
  if (opts?.limit) qs.set('limit', String(opts.limit));
  if (opts?.before) qs.set('before', opts.before);
  return _fetch(`/entities/${entityType}/${entityId}/history?${qs}`);
}

export function listChangeEvents(orgId: string, opts?: { network_id?: string; limit?: number; before?: string })
: Promise<{ events: ConfigChangeEvent[]; has_more: boolean; next_cursor: string | null }> {
  const qs = new URLSearchParams({ org_id: orgId });
  if (opts?.network_id) qs.set('network_id', opts.network_id);
  if (opts?.limit) qs.set('limit', String(opts.limit));
  if (opts?.before) qs.set('before', opts.before);
  return _fetch(`/change-events?${qs}`);
}

export async function fetchOrgDiff(
  orgId: string,
  fromTs: string,
  toTs?: string,
): Promise<OrgDiffResponse> {
  const params = new URLSearchParams({ org_id: orgId, from_ts: fromTs })
  if (toTs) params.set('to_ts', toTs)
  return _fetch<OrgDiffResponse>(`/diff/org?${params}`)
}

export async function fetchEntityTimeline(
  orgId: string,
  entityType: EntityType,
  entityId: string,
): Promise<EntityTimelineResponse> {
  const params = new URLSearchParams({ org_id: orgId })
  return _fetch<EntityTimelineResponse>(
    `/entities/${entityType}/${entityId}/timeline?${params}`,
  )
}
