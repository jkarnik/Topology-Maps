# Plan 1.20 — UI: Browser Shell + Status Bar + Tree

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Build the main Configs workspace: top-level `ConfigBrowser` with split layout, `CollectionStatusBar` showing org dropdown + sync state + action buttons, and `ConfigTree` for hierarchical navigation with lazy expansion.

**Depends on:** Plan 1.19.
**Unblocks:** Plan 1.21.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `ui/src/components/ConfigBrowser/ConfigBrowser.tsx` | Create | Top-level layout |
| `ui/src/components/ConfigBrowser/CollectionStatusBar.tsx` | Create | Org selector + status + trigger buttons |
| `ui/src/components/ConfigBrowser/ConfigTree.tsx` | Create | Left-pane hierarchical tree |
| `ui/src/components/ConfigBrowser/index.ts` | Create | Barrel export |

---

## Task 1: `CollectionStatusBar`

- [ ] **Step 1.1: Create the component**

Create `ui/src/components/ConfigBrowser/CollectionStatusBar.tsx`:

```typescript
import React from 'react';
import type { ConfigOrg, ConfigStatus } from '../../types/config';

interface Props {
  orgs: ConfigOrg[];
  selectedOrgId: string | null;
  status: ConfigStatus | null;
  onOrgChange: (orgId: string) => void;
  onStartBaseline: () => void;
  onStartSweep: () => void;
}

function statusChip(state: string): { bg: string; label: string } {
  switch (state) {
    case 'complete':     return { bg: 'bg-green-500',  label: 'Synced' };
    case 'in_progress':  return { bg: 'bg-yellow-500', label: 'Syncing' };
    case 'running':      return { bg: 'bg-yellow-500', label: 'Running' };
    case 'failed':       return { bg: 'bg-red-500',    label: 'Failed' };
    default:             return { bg: 'bg-gray-400',   label: 'Never baselined' };
  }
}

export const CollectionStatusBar: React.FC<Props> = ({
  orgs, selectedOrgId, status, onOrgChange, onStartBaseline, onStartSweep,
}) => {
  const state = status?.active_sweep?.status ?? status?.baseline_state ?? 'none';
  const chip = statusChip(state);
  const baselineStarted = status?.baseline_state !== 'none';

  return (
    <div className="flex items-center gap-4 p-3 border-b bg-white">
      <label className="text-sm text-gray-700">Org:</label>
      <select
        value={selectedOrgId ?? ''}
        onChange={(e) => onOrgChange(e.target.value)}
        className="border rounded px-2 py-1 text-sm"
      >
        <option value="">Select an org…</option>
        {orgs.map((o) => (
          <option key={o.org_id} value={o.org_id}>
            {o.org_id} ({o.observation_count} observations)
          </option>
        ))}
      </select>

      <span className={`inline-flex items-center gap-2 px-2 py-1 rounded text-xs text-white ${chip.bg}`}>
        <span className="w-2 h-2 rounded-full bg-white/80" />
        {chip.label}
        {status?.last_sync && (
          <span className="ml-1 text-white/80">{new Date(status.last_sync).toLocaleString()}</span>
        )}
      </span>

      <div className="ml-auto flex gap-2">
        {!baselineStarted ? (
          <button
            className="px-3 py-1 text-sm rounded bg-blue-600 text-white hover:bg-blue-700"
            disabled={!selectedOrgId}
            onClick={onStartBaseline}
          >Start baseline</button>
        ) : (
          <button
            className="px-3 py-1 text-sm rounded bg-gray-700 text-white hover:bg-gray-800"
            disabled={!selectedOrgId || state === 'running'}
            onClick={onStartSweep}
          >Run full sweep</button>
        )}
      </div>
    </div>
  );
};
```

- [ ] **Step 1.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/CollectionStatusBar.tsx
git commit -m "feat(ui): CollectionStatusBar with org dropdown + status chip (Plan 1.20)"
```

---

## Task 2: `ConfigTree`

- [ ] **Step 2.1: Create the component**

Create `ui/src/components/ConfigBrowser/ConfigTree.tsx`:

```typescript
import React, { useState } from 'react';
import type { ConfigTree as ConfigTreeData, EntityType } from '../../types/config';

interface Props {
  tree: ConfigTreeData | null;
  loading: boolean;
  onSelect: (entityType: EntityType, entityId: string) => void;
  selected: { entityType: EntityType; entityId: string } | null;
}

const caret = (open: boolean) => (open ? '▾' : '▸');

export const ConfigTree: React.FC<Props> = ({ tree, loading, onSelect, selected }) => {
  const [openNetworks, setOpenNetworks] = useState<Set<string>>(new Set());

  if (loading) return <div className="p-3 text-sm text-gray-500">Loading…</div>;
  if (!tree) return <div className="p-3 text-sm text-gray-500">No data yet.</div>;

  const isSelected = (t: EntityType, id: string) =>
    selected?.entityType === t && selected.entityId === id;

  const rowClass = (t: EntityType, id: string) =>
    `cursor-pointer px-2 py-1 rounded text-sm ${isSelected(t, id) ? 'bg-blue-100 font-semibold' : 'hover:bg-gray-100'}`;

  const toggleNetwork = (id: string) => {
    setOpenNetworks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div className="p-2 text-sm overflow-y-auto h-full">
      <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Org configs</div>
      <div
        className={rowClass('org', tree.org.id)}
        onClick={() => onSelect('org', tree.org.id)}
      >
        {tree.org.id}
        <span className="ml-2 text-gray-400">({tree.org.config_areas.length} areas)</span>
      </div>

      <div className="mt-3 mb-2 text-xs uppercase tracking-wide text-gray-500">Networks</div>
      {tree.networks.map((net) => {
        const open = openNetworks.has(net.id);
        return (
          <div key={net.id}>
            <div
              className="flex items-center gap-1 cursor-pointer hover:bg-gray-50 px-1"
              onClick={() => toggleNetwork(net.id)}
            >
              <span className="w-4">{caret(open)}</span>
              <span
                onClick={(e) => { e.stopPropagation(); onSelect('network', net.id); }}
                className={`flex-1 ${rowClass('network', net.id)}`}
              >
                {net.name ?? net.id}
                <span className="ml-2 text-gray-400">({net.config_areas.length})</span>
              </span>
            </div>
            {open && net.devices.map((d) => (
              <div
                key={d.serial}
                className={`ml-6 ${rowClass('device', d.serial)}`}
                onClick={() => onSelect('device', d.serial)}
              >
                {d.name ?? d.serial}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};
```

- [ ] **Step 2.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/ConfigTree.tsx
git commit -m "feat(ui): ConfigTree with lazy network expansion (Plan 1.20)"
```

---

## Task 3: `ConfigBrowser` top-level shell

- [ ] **Step 3.1: Create the component**

Create `ui/src/components/ConfigBrowser/ConfigBrowser.tsx`:

```typescript
import React, { useState, useEffect } from 'react';
import { CollectionStatusBar } from './CollectionStatusBar';
import { ConfigTree } from './ConfigTree';
import { useConfigOrgs } from '../../hooks/useConfigOrgs';
import { useConfigTree } from '../../hooks/useConfigTree';
import { useConfigCollection } from '../../hooks/useConfigCollection';
import { getStatus, startBaseline, startSweep } from '../../api/config';
import type { ConfigStatus, EntityType } from '../../types/config';

export const ConfigBrowser: React.FC = () => {
  const { orgs } = useConfigOrgs();
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ entityType: EntityType; entityId: string } | null>(null);
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const { tree, loading: treeLoading, reload: reloadTree } = useConfigTree(selectedOrgId);
  const { lastEvent } = useConfigCollection(selectedOrgId);

  // Auto-pick first org
  useEffect(() => {
    if (!selectedOrgId && orgs.length > 0) setSelectedOrgId(orgs[0].org_id);
  }, [orgs, selectedOrgId]);

  // Reload status on WS events
  useEffect(() => {
    if (!selectedOrgId) return;
    getStatus(selectedOrgId).then(setStatus);
  }, [selectedOrgId, lastEvent]);

  // Reload tree on observation updates
  useEffect(() => {
    if (lastEvent?.type === 'observation.updated') reloadTree();
    if (lastEvent?.type === 'sweep.completed') reloadTree();
  }, [lastEvent, reloadTree]);

  const handleBaseline = async () => {
    if (!selectedOrgId) return;
    await startBaseline(selectedOrgId);
    getStatus(selectedOrgId).then(setStatus);
  };

  const handleSweep = async () => {
    if (!selectedOrgId) return;
    await startSweep(selectedOrgId);
    getStatus(selectedOrgId).then(setStatus);
  };

  return (
    <div className="flex flex-col h-full">
      <CollectionStatusBar
        orgs={orgs}
        selectedOrgId={selectedOrgId}
        status={status}
        onOrgChange={setSelectedOrgId}
        onStartBaseline={handleBaseline}
        onStartSweep={handleSweep}
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="w-80 border-r overflow-y-auto">
          <ConfigTree
            tree={tree}
            loading={treeLoading}
            onSelect={(t, id) => setSelected({ entityType: t, entityId: id })}
            selected={selected}
          />
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          {/* Plan 1.21 will replace this placeholder with ConfigEntityView */}
          <div className="text-sm text-gray-500">
            {selected ? `Selected: ${selected.entityType} / ${selected.entityId}` : 'Select an entity from the tree.'}
          </div>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 3.2: Create barrel export**

Create `ui/src/components/ConfigBrowser/index.ts`:

```typescript
export { ConfigBrowser } from './ConfigBrowser';
```

- [ ] **Step 3.3: Wire into `App.tsx` or parent router**

Identify the parent that renders based on `SourceSelector`'s value, and add a branch that renders `<ConfigBrowser />` when `value === 'configs'`.

- [ ] **Step 3.4: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/ConfigBrowser.tsx ui/src/components/ConfigBrowser/index.ts ui/src/App.tsx
git commit -m "feat(ui): ConfigBrowser top-level shell wired into app (Plan 1.20)"
```

---

## Completion Checklist

- [ ] `ConfigBrowser`, `CollectionStatusBar`, `ConfigTree` exist and compile
- [ ] App renders ConfigBrowser when Configs is selected in SourceSelector
- [ ] 3 commits

## What This Unblocks

- Plan 1.21: the right-pane placeholder is replaced by `ConfigEntityView` + `ConfigAreaViewer` + `BaselineProgressOverlay`.
