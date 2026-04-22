# Plan 1.21 — UI: Entity Views + Progress Overlay

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans.
>
> **Execution guideline (user directive):** Before executing ANY task, evaluate whether it can be split further. Commit frequently.

**Goal:** Fill in the right pane of `ConfigBrowser`: `ConfigEntityView` renders a selected entity's areas; `ConfigAreaViewer` displays redacted JSON per area with a refresh button; `BaselineProgressOverlay` shows live progress during baseline runs.

**Depends on:** Plans 1.19, 1.20.
**Unblocks:** End of Phase 1.

---

## File Structure

| Path | Status | Responsibility |
|---|---|---|
| `ui/src/components/ConfigBrowser/ConfigEntityView.tsx` | Create | Right-pane: render all areas for an entity |
| `ui/src/components/ConfigBrowser/ConfigAreaViewer.tsx` | Create | Collapsible JSON viewer for one area + refresh button |
| `ui/src/components/ConfigBrowser/BaselineProgressOverlay.tsx` | Create | Modal shown during sweep runs |
| `ui/src/components/ConfigBrowser/ConfigBrowser.tsx` | Modify | Replace right-pane placeholder with `ConfigEntityView`, add overlay |
| `ui/package.json` | Modify | Add `@uiw/react-json-view` or equivalent JSON viewer library |

---

## Task 1: Install JSON viewer dependency

- [ ] **Step 1.1: Add dependency**

```bash
cd "/Users/jkarnik/Code/Topology Maps/ui"
npm install @uiw/react-json-view
```

- [ ] **Step 1.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/package.json ui/package-lock.json
git commit -m "chore(ui): add @uiw/react-json-view for config viewer (Plan 1.21)"
```

---

## Task 2: `ConfigAreaViewer` component

- [ ] **Step 2.1: Create the component**

Create `ui/src/components/ConfigBrowser/ConfigAreaViewer.tsx`:

```typescript
import React, { useState } from 'react';
import JsonView from '@uiw/react-json-view';
import type { ConfigArea } from '../../types/config';

interface Props {
  area: ConfigArea;
  onRefresh: () => void;
  refreshing: boolean;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const d = Math.round(hr / 24);
  return `${d}d ago`;
}

export const ConfigAreaViewer: React.FC<Props> = ({ area, onRefresh, refreshing }) => {
  const [open, setOpen] = useState(false);
  const label = area.config_area.replace(/_/g, ' ');

  return (
    <div className="border rounded mb-2 bg-white">
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b">
        <button
          className="text-sm text-gray-700 hover:text-black"
          onClick={() => setOpen((o) => !o)}
        >{open ? '▾' : '▸'} {label}</button>
        <span className="text-xs text-gray-500 ml-auto">
          last: {relativeTime(area.observed_at)} ({area.source_event})
        </span>
        <button
          className="text-sm px-2 py-0.5 rounded hover:bg-gray-200"
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh this area"
        >{refreshing ? '⟳' : '↻'}</button>
      </div>
      {open && (
        <div className="p-3 text-sm overflow-auto max-h-96">
          <JsonView
            value={area.payload as object}
            displayDataTypes={false}
            collapsed={2}
          />
        </div>
      )}
    </div>
  );
};
```

- [ ] **Step 2.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/ConfigAreaViewer.tsx
git commit -m "feat(ui): ConfigAreaViewer with collapsible JSON + refresh (Plan 1.21)"
```

---

## Task 3: `ConfigEntityView` component

- [ ] **Step 3.1: Create the component**

Create `ui/src/components/ConfigBrowser/ConfigEntityView.tsx`:

```typescript
import React, { useState } from 'react';
import { ConfigAreaViewer } from './ConfigAreaViewer';
import { useConfigEntity } from '../../hooks/useConfigEntity';
import { refresh } from '../../api/config';
import type { EntityType } from '../../types/config';

interface Props {
  orgId: string;
  entityType: EntityType;
  entityId: string;
}

export const ConfigEntityView: React.FC<Props> = ({ orgId, entityType, entityId }) => {
  const { entity, loading, reload } = useConfigEntity(orgId, entityType, entityId);
  const [refreshingArea, setRefreshingArea] = useState<string | null>(null);

  if (loading && !entity) return <div className="text-sm text-gray-500">Loading…</div>;
  if (!entity) return <div className="text-sm text-gray-500">No data for this entity yet.</div>;

  const handleRefresh = async (configArea: string) => {
    setRefreshingArea(configArea);
    try {
      await refresh(orgId, { entity_type: entityType, entity_id: entityId, config_area: configArea });
      reload();
    } finally {
      setRefreshingArea(null);
    }
  };

  return (
    <div>
      <div className="mb-4">
        <div className="text-xs uppercase tracking-wide text-gray-500">{entityType}</div>
        <div className="text-xl font-semibold">{entityId}</div>
      </div>
      {entity.areas.length === 0
        ? <div className="text-sm text-gray-500">No observations yet. Try running a baseline.</div>
        : entity.areas.map((area) => (
            <ConfigAreaViewer
              key={`${area.config_area}:${area.sub_key ?? ''}`}
              area={area}
              onRefresh={() => handleRefresh(area.config_area)}
              refreshing={refreshingArea === area.config_area}
            />
          ))
      }
    </div>
  );
};
```

- [ ] **Step 3.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/ConfigEntityView.tsx
git commit -m "feat(ui): ConfigEntityView rendering all areas for an entity (Plan 1.21)"
```

---

## Task 4: `BaselineProgressOverlay` component

- [ ] **Step 4.1: Create the component**

Create `ui/src/components/ConfigBrowser/BaselineProgressOverlay.tsx`:

```typescript
import React from 'react';
import type { ConfigWsEvent } from '../../types/config';

interface Props {
  progress: Extract<ConfigWsEvent, { type: 'sweep.progress' }> | null;
  kind: string | null;
  onClose: () => void;
}

export const BaselineProgressOverlay: React.FC<Props> = ({ progress, kind, onClose }) => {
  if (!progress) return null;
  const pct = progress.total_calls > 0
    ? Math.round((progress.completed_calls / progress.total_calls) * 100)
    : 0;

  return (
    <div
      role="dialog"
      aria-live="polite"
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    >
      <div className="bg-white rounded shadow-lg p-6 w-[420px]">
        <h3 className="text-lg font-semibold mb-2">
          {kind === 'anti_drift' ? 'Anti-drift sweep running' : 'Baseline in progress'}
        </h3>
        <div className="text-sm text-gray-600 mb-4">
          {progress.completed_calls.toLocaleString()} of {progress.total_calls.toLocaleString()} calls
        </div>
        <div className="h-3 bg-gray-200 rounded overflow-hidden mb-4" aria-label="progress">
          <div className="h-full bg-blue-600" style={{ width: `${pct}%` }} />
        </div>
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>{pct}% complete</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">Dismiss</button>
        </div>
      </div>
    </div>
  );
};
```

- [ ] **Step 4.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/BaselineProgressOverlay.tsx
git commit -m "feat(ui): BaselineProgressOverlay modal with live progress bar (Plan 1.21)"
```

---

## Task 5: Wire everything into `ConfigBrowser.tsx`

- [ ] **Step 5.1: Replace placeholder and add overlay**

In `ui/src/components/ConfigBrowser/ConfigBrowser.tsx`:

1. Import the new components:

```typescript
import { ConfigEntityView } from './ConfigEntityView';
import { BaselineProgressOverlay } from './BaselineProgressOverlay';
```

2. Replace the right-pane placeholder div:

```typescript
        <div className="flex-1 overflow-y-auto p-4">
          {selected && selectedOrgId
            ? <ConfigEntityView orgId={selectedOrgId} entityType={selected.entityType} entityId={selected.entityId} />
            : <div className="text-sm text-gray-500">Select an entity from the tree.</div>
          }
        </div>
```

3. Add overlay logic before the closing root `</div>`:

```typescript
      {(() => {
        if (lastEvent?.type === 'sweep.progress') {
          return (
            <BaselineProgressOverlay
              progress={lastEvent}
              kind={status?.active_sweep?.kind ?? null}
              onClose={() => {/* local dismiss: simplest is to ignore further updates in local state */}}
            />
          );
        }
        return null;
      })()}
```

For dismiss behavior, add a `dismissedSweepId: number | null` state; set it on dismiss; suppress the overlay while `lastEvent.sweep_run_id === dismissedSweepId`.

- [ ] **Step 5.2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add ui/src/components/ConfigBrowser/ConfigBrowser.tsx
git commit -m "feat(ui): wire entity view + progress overlay into ConfigBrowser (Plan 1.21)"
```

---

## Task 6: End-of-Phase-1 smoke test

- [ ] **Step 6.1: Start the backend and UI**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
docker compose up --build
```

- [ ] **Step 6.2: Manual smoke in the browser**

Open `http://localhost:80`. Change the source selector to **Configs**. Confirm:

1. "Start baseline" button appears when there is no baseline for the org
2. Clicking it shows a progress overlay
3. The tree populates with networks once the baseline has written observations
4. Clicking a network displays its config areas in the right pane
5. Clicking the "↻" button on an area triggers a refresh and re-renders

If the baseline takes long (expected at scale), the overlay should continuously update and eventually close on sweep.completed.

- [ ] **Step 6.3: Note any UI polish issues**

Phase 1 does not require pixel-perfect polish. Note any issues in a `docs/superpowers/plans/2026-04-22-phase1-followups.md` for Phase 2 prep, but do not block completion.

---

## Completion Checklist

- [ ] `ConfigEntityView`, `ConfigAreaViewer`, `BaselineProgressOverlay` created
- [ ] `ConfigBrowser` replaces placeholder and wires overlay
- [ ] Manual smoke: baseline → tree populates → entity view works → refresh works
- [ ] 5 commits

## What This Unblocks

- **End of Phase 1.** At this point, the full pipeline described in the spec is implemented end-to-end. Phase 2 (diff + timeline) can begin.
