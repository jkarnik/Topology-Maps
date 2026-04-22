# Plan 1.19 — UI Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Establish the UI plumbing: TypeScript types matching the REST responses, a small API client wrapping `fetch()`, React hooks for each endpoint, WebSocket hook for live events, and extending `SourceSelector` to include a "Configs" workspace.

**Depends on:** Plans 1.17, 1.18.
**Unblocks:** Plans 1.20, 1.21.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `ui/src/types/config.ts` | Create | TypeScript interfaces matching API responses |
| `ui/src/api/config.ts` | Create | Thin fetch wrapper per endpoint |
| `ui/src/hooks/useConfigOrgs.ts` | Create | Hook: list orgs + status |
| `ui/src/hooks/useConfigTree.ts` | Create | Hook: fetch tree for an org |
| `ui/src/hooks/useConfigEntity.ts` | Create | Hook: fetch entity detail |
| `ui/src/hooks/useConfigCollection.ts` | Create | Hook: subscribe to `/ws/config` |
| `ui/src/components/SourceSelector.tsx` | Modify | Add "Configs" option |

---

## Task 1: TypeScript types

- [ ] **Step 1.1: Create types file**

Create `ui/src/types/config.ts`:

```typescript
// Types matching /api/config/* responses (Plan 1.19)

export type BaselineState = 'none' | 'in_progress' | 'complete' | 'failed';
export type EntityType = 'org' | 'network' | 'device' | 'ssid';
export type SourceEvent =
  | 'baseline'
  | 'change_log'
  | 'anti_drift_confirm'
  | 'anti_drift_discrepancy'
  | 'manual_refresh';

export interface ConfigOrg {
  org_id: string;
  observation_count: number;
  baseline_state: BaselineState;
  last_baseline_at: string | null;
  active_sweep_run_id: number | null;
}

export interface ConfigStatus {
  baseline_state: BaselineState;
  last_sync: string | null;
  active_sweep: { id: number; kind: string; status: string } | null;
}

export interface ConfigObservation {
  id: number;
  org_id: string;
  entity_type: EntityType;
  entity_id: string;
  config_area: string;
  sub_key: string | null;
  hash: string;
  observed_at: string;
  source_event: SourceEvent;
  change_event_id: number | null;
  sweep_run_id: number | null;
  name_hint: string | null;
  enabled_hint: 0 | 1 | null;
}

export interface ConfigArea extends ConfigObservation {
  payload: unknown;
}

export interface ConfigEntity {
  entity_type: EntityType;
  entity_id: string;
  org_id: string;
  areas: ConfigArea[];
}

export interface ConfigTreeNetwork {
  id: string;
  name: string | null;
  config_areas: string[];
  devices: { serial: string; name: string | null }[];
}

export interface ConfigTree {
  org: { id: string; config_areas: string[] };
  networks: ConfigTreeNetwork[];
}

export interface ConfigChangeEvent {
  id: number;
  org_id: string;
  ts: string;
  admin_id: string | null;
  admin_name: string | null;
  admin_email: string | null;
  network_id: string | null;
  network_name: string | null;
  ssid_number: number | null;
  ssid_name: string | null;
  page: string | null;
  label: string | null;
  old_value: string | null;
  new_value: string | null;
}

export type ConfigWsEvent =
  | { type: 'sweep.started'; sweep_run_id: number; org_id: string; kind: string; total_calls: number }
  | { type: 'sweep.progress'; sweep_run_id: number; completed_calls: number; total_calls: number }
  | { type: 'sweep.completed'; sweep_run_id: number; org_id: string }
  | { type: 'sweep.failed'; sweep_run_id: number; org_id: string; error_summary: string }
  | { type: 'observation.updated'; org_id: string; entity_type: string; entity_id: string; config_area: string }
  | { type: 'change_event.new'; org_id: string; event_id: number; network_id: string | null; label: string | null; ts: string };
```

- [ ] **Step 1.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/types/config.ts
git commit -m "feat(ui): TypeScript types for config API (Plan 1.19)"
```

---

## Task 2: API client module

- [ ] **Step 2.1: Create API client**

Create `ui/src/api/config.ts`:

```typescript
// Thin fetch wrappers for /api/config/* (Plan 1.19)
import type {
  ConfigOrg, ConfigStatus, ConfigEntity, ConfigTree, ConfigChangeEvent,
  ConfigObservation, EntityType,
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
```

- [ ] **Step 2.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/api/config.ts
git commit -m "feat(ui): config API fetch client (Plan 1.19)"
```

---

## Task 3: React hooks

- [ ] **Step 3.1: Create `useConfigOrgs`**

Create `ui/src/hooks/useConfigOrgs.ts`:

```typescript
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
```

- [ ] **Step 3.2: Create `useConfigTree`**

Create `ui/src/hooks/useConfigTree.ts`:

```typescript
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
```

- [ ] **Step 3.3: Create `useConfigEntity`**

Create `ui/src/hooks/useConfigEntity.ts`:

```typescript
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
```

- [ ] **Step 3.4: Create `useConfigCollection` (WebSocket)**

Create `ui/src/hooks/useConfigCollection.ts`:

```typescript
import { useEffect, useState } from 'react';
import type { ConfigWsEvent } from '../types/config';

export function useConfigCollection(orgId: string | null) {
  const [lastEvent, setLastEvent] = useState<ConfigWsEvent | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!orgId) { setConnected(false); return; }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/ws/config?org_id=${orgId}`;
    const ws = new WebSocket(url);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (evt) => {
      try {
        const data: ConfigWsEvent = JSON.parse(evt.data);
        setLastEvent(data);
      } catch { /* ignore */ }
    };
    return () => ws.close();
  }, [orgId]);

  return { connected, lastEvent };
}
```

- [ ] **Step 3.5: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/hooks/useConfigOrgs.ts ui/src/hooks/useConfigTree.ts ui/src/hooks/useConfigEntity.ts ui/src/hooks/useConfigCollection.ts
git commit -m "feat(ui): React hooks for config data + WebSocket events (Plan 1.19)"
```

---

## Task 4: Extend SourceSelector with "Configs" option

- [ ] **Step 4.1: Read the existing SourceSelector to find the right spot**

Read: `ui/src/components/SourceSelector.tsx`.

- [ ] **Step 4.2: Add the "Configs" option**

Exact edit depends on the existing component shape. The addition should follow the existing pattern — add a new option value `'configs'` with display label `'Configs'` to the dropdown's option list, and ensure the parent component handles a `configs` selection by rendering the new `ConfigBrowser` (built in Plan 1.20).

For the change to be minimally invasive: widen the SourceSelector's `value` union type to include `'configs'`, add one `<option value="configs">Configs</option>` element (or its equivalent in whatever pattern the component uses), and propagate via the existing `onChange`.

- [ ] **Step 4.3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/SourceSelector.tsx
git commit -m "feat(ui): add Configs option to SourceSelector (Plan 1.19)"
```

---

## Completion Checklist

- [ ] `config.ts` types defined
- [ ] `api/config.ts` client functions exist
- [ ] 4 React hooks created
- [ ] `SourceSelector` extended
- [ ] 4 commits

## What This Unblocks

- Plans 1.20, 1.21 can now build components against these hooks.

