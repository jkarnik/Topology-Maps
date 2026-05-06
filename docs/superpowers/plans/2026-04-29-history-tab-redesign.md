# History Tab Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the History tab with a two-panel layout — date-range picker + entity tree on the left, expandable before/after diff tiles on the right — and add `from_payload` / `to_payload` fields to `MerakiConfigChange` events pushed to New Relic.

**Architecture:** The backend change is one event-dict addition in `build_change_events()`; both payload fields are already fetched in the SQL. The frontend replaces the flat table+modal with a stateful component: date-range state drives two NRQL queries (entity tree + diff tiles), and each tile expands inline to show side-by-side pretty-printed JSON with line-level tinting.

**Tech Stack:** Python 3, pytest, React (NR1 `NrqlQuery`, `Spinner`), CSS-in-JS (no new npm packages)

---

### Task 1: Add `from_payload` and `to_payload` to MerakiConfigChange events

**Files:**
- Modify: `nr_ingest/config_ingest.py:265-280`
- Modify: `nr_ingest/tests/test_config_ingest.py:97-118`

The SQL in `build_change_events()` already selects both columns (`b_new.payload AS to_payload`, `b_old.payload AS from_payload`, lines 232-233). They just aren't added to the event dict.

- [ ] **Step 1: Write the failing test**

  In `nr_ingest/tests/test_config_ingest.py`, add assertions to the existing `test_build_change_events_detects_hash_diff` test immediately after the `assert ev["change_summary"] != ""` line:

  ```python
  assert ev["from_payload"] == '[{"portId":"1","enabled":true}]'
  assert ev["to_payload"] == '[{"portId":"1","enabled":false}]'
  ```

- [ ] **Step 2: Run the test to confirm it fails**

  ```bash
  python3 -m pytest nr_ingest/tests/test_config_ingest.py::test_build_change_events_detects_hash_diff -v
  ```
  Expected: `FAILED` — `KeyError: 'from_payload'`

- [ ] **Step 3: Add the two fields to the event dict**

  In `nr_ingest/config_ingest.py`, inside `build_change_events()`, in the `events.append({...})` block after the `"network_id"` line (around line 278), add:

  ```python
  "from_payload": (row["from_payload"] or "")[:4000],
  "to_payload": row["to_payload"][:4000],
  ```

- [ ] **Step 4: Run all ingest tests**

  ```bash
  python3 -m pytest nr_ingest/tests/test_config_ingest.py -v
  ```
  Expected: all tests PASS (no regressions)

- [ ] **Step 5: Commit**

  ```bash
  git add nr_ingest/config_ingest.py nr_ingest/tests/test_config_ingest.py
  git commit -m "feat(ingest): add from_payload and to_payload to MerakiConfigChange events"
  ```

---

### Task 2: ChangeHistory — two-panel skeleton and date range controls

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ChangeHistory.js`

Replace the entire file. This task produces a working component with date-range state and the two-panel layout. Right panel shows a placeholder; entity tree section is a placeholder. No NRQL queries yet.

- [ ] **Step 1: Replace ChangeHistory.js with the skeleton**

  Replace the full file contents with:

  ```jsx
  import React, { useState } from 'react';
  import { NrqlQuery, Spinner } from 'nr1';

  function daysAgo(n) {
    const d = new Date();
    d.setDate(d.getDate() - n);
    d.setHours(0, 0, 0, 0);
    return d;
  }

  function DateRangePanel({ fromDate, toDate, onRangeChange }) {
    function setShortcut(days) {
      const to = new Date();
      to.setHours(23, 59, 59, 999);
      const from = daysAgo(days);
      onRangeChange(from, to);
    }
    function toInputVal(d) { return d.toISOString().slice(0, 10); }
    const activeDays = Math.round((toDate - fromDate) / 86400000);
    return (
      <div style={{ marginBottom: '16px' }}>
        <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Date Range</div>
        <div style={{ marginBottom: '6px', fontSize: '12px' }}>
          <label style={{ display: 'block', opacity: 0.6, marginBottom: '2px' }}>From</label>
          <input type="date" value={toInputVal(fromDate)} max={toInputVal(toDate)}
            onChange={e => onRangeChange(new Date(e.target.value + 'T00:00:00'), toDate)}
            style={{ width: '100%', fontSize: '12px', padding: '2px 4px', background: 'transparent', border: '1px solid rgba(128,128,128,0.3)', borderRadius: '3px', color: 'inherit' }} />
        </div>
        <div style={{ marginBottom: '8px', fontSize: '12px' }}>
          <label style={{ display: 'block', opacity: 0.6, marginBottom: '2px' }}>To</label>
          <input type="date" value={toInputVal(toDate)} min={toInputVal(fromDate)}
            onChange={e => onRangeChange(fromDate, new Date(e.target.value + 'T23:59:59'))}
            style={{ width: '100%', fontSize: '12px', padding: '2px 4px', background: 'transparent', border: '1px solid rgba(128,128,128,0.3)', borderRadius: '3px', color: 'inherit' }} />
        </div>
        <div style={{ display: 'flex', gap: '4px' }}>
          {[7, 30, 90].map(d => (
            <button key={d} onClick={() => setShortcut(d)} style={{
              flex: 1, fontSize: '11px', padding: '3px 0', cursor: 'pointer',
              background: activeDays === d ? 'rgba(0,120,191,0.15)' : 'transparent',
              border: `1px solid ${activeDays === d ? '#0078bf' : 'rgba(128,128,128,0.3)'}`,
              borderRadius: '3px', color: activeDays === d ? '#0078bf' : 'inherit',
            }}>{d}d</button>
          ))}
        </div>
      </div>
    );
  }

  export default function ChangeHistory({ accountId, orgId }) {
    const [fromDate, setFromDate] = useState(daysAgo(30));
    const [toDate, setToDate] = useState(() => { const d = new Date(); d.setHours(23,59,59,999); return d; });
    const [selectedEntityId, setSelectedEntityId] = useState(null);
    const [selectedEntityName, setSelectedEntityName] = useState(null);

    if (!accountId || !orgId) return <p style={{ opacity: 0.6 }}>Select an org to view change history.</p>;

    function handleSelect(entityId, entityName) {
      if (selectedEntityId === entityId) { setSelectedEntityId(null); setSelectedEntityName(null); }
      else { setSelectedEntityId(entityId); setSelectedEntityName(entityName); }
    }

    return (
      <div style={{ display: 'flex', height: '100%', gap: 0 }}>
        <div style={{ width: '220px', minWidth: '220px', borderRight: '1px solid rgba(128,128,128,0.2)', paddingRight: '12px', overflowY: 'auto' }}>
          <DateRangePanel fromDate={fromDate} toDate={toDate}
            onRangeChange={(f, t) => { setFromDate(f); setToDate(t); }} />
          <div style={{ fontSize: '11px', opacity: 0.4 }}>Entity tree coming soon…</div>
        </div>
        <div style={{ flex: 1, paddingLeft: '16px', overflowY: 'auto' }}>
          <div style={{ opacity: 0.4, fontSize: '13px' }}>Diff tiles coming soon…</div>
        </div>
      </div>
    );
  }
  ```

- [ ] **Step 2: Verify in browser**

  The History tab should show a left panel with From/To date inputs and 7d/30d/90d shortcut buttons; clicking 7d highlights the 7d button. Right panel is a placeholder.

- [ ] **Step 3: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/ChangeHistory.js
  git commit -m "feat(nerdpack): replace ChangeHistory with two-panel skeleton and date range controls"
  ```

---

### Task 3: ChangeHistory — entity tree in left panel

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ChangeHistory.js`

Add `HistoryTreeNode`, `HistoryEntityItem`, and `EntityTree` components. Replace the placeholder in the left panel with `<EntityTree>`. The entity tree runs two NRQL queries: one for change counts by entity, one for network names from snapshots.

NrqlQuery FACET shape: `data` is an array of series. For each series, facet values live in `s.metadata?.groups` filtered to `g.type === 'facet'`; the metric is in `s.data?.[0]`.

- [ ] **Step 1: Add sub-components and EntityTree before the main export**

  Insert the following **after** the closing `}` of `DateRangePanel` and **before** `export default function ChangeHistory`:

  ```jsx
  function HistoryTreeNode({ label, children, defaultOpen = false }) {
    const [open, setOpen] = useState(defaultOpen);
    return (
      <div>
        <div onClick={() => setOpen(o => !o)} style={{ cursor: 'pointer', padding: '3px 0', fontWeight: 'bold', userSelect: 'none', fontSize: '12px', opacity: 0.7 }}>
          {open ? '▾' : '▸'} {label}
        </div>
        {open && <div style={{ paddingLeft: '12px' }}>{children}</div>}
      </div>
    );
  }

  function HistoryEntityItem({ entity, selected, onSelect }) {
    return (
      <div onClick={onSelect} style={{
        padding: '2px 4px', cursor: 'pointer', borderRadius: '3px', marginBottom: '1px', fontSize: '12px',
        color: selected ? '#0078bf' : 'inherit',
        background: selected ? 'rgba(0,120,191,0.12)' : 'transparent',
      }}>
        {selected ? '●' : '○'} {entity.entityName}
        <span style={{ opacity: 0.5, marginLeft: '4px' }}>({entity.count})</span>
      </div>
    );
  }

  function EntityTree({ accountId, orgId, fromDate, toDate, selectedId, onSelect }) {
    const fromISO = fromDate.toISOString().slice(0, 10);
    const toISO = toDate.toISOString().slice(0, 10);
    return (
      <div>
        <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Changed Entities</div>
        <NrqlQuery accountIds={[accountId]}
          query={`SELECT latest(entity_name) FROM MerakiConfigSnapshot WHERE entity_type = 'network' AND org_id = '${orgId}' FACET entity_id SINCE 30 days ago LIMIT MAX`}>
          {({ data: netData }) => {
            const netNames = {};
            (netData || []).forEach(s => {
              const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
              const id = fg[0]?.value;
              const name = s.data?.[0]?.['entity_name'];
              if (id && name) netNames[id] = name;
            });
            return (
              <NrqlQuery accountIds={[accountId]}
                query={`SELECT count(*) FROM MerakiConfigChange WHERE org_id = '${orgId}' FACET entity_type, entity_id, entity_name, network_id SINCE '${fromISO}' UNTIL '${toISO}' LIMIT MAX`}>
                {({ data, loading, error }) => {
                  if (loading) return <Spinner />;
                  if (error) return <p style={{ color: '#c0392b', fontSize: '12px' }}>Failed to load.</p>;
                  const entities = [];
                  (data || []).forEach(s => {
                    const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
                    const entityType = fg[0]?.value;
                    const entityId = fg[1]?.value;
                    const entityName = fg[2]?.value;
                    const networkId = fg[3]?.value;
                    const count = s.data?.[0]?.count || 0;
                    if (!entityId || !count) return;
                    entities.push({ entityType, entityId, entityName: entityName || entityId, networkId, count });
                  });
                  if (!entities.length) return <p style={{ opacity: 0.5, fontSize: '12px' }}>No changes in range.</p>;
                  const networks = {};
                  entities.forEach(e => {
                    const netId = e.entityType === 'network' ? e.entityId
                      : e.entityType === 'ssid' ? e.entityId.split(':')[0]
                      : e.networkId || '__unknown';
                    if (!networks[netId]) networks[netId] = { id: netId, name: netNames[netId] || netId, items: [] };
                    networks[netId].items.push(e);
                  });
                  return (
                    <div style={{ fontFamily: 'monospace' }}>
                      {Object.values(networks).map(net => (
                        <HistoryTreeNode key={net.id} label={net.name} defaultOpen>
                          {net.items.map(e => (
                            <HistoryEntityItem key={e.entityId} entity={e}
                              selected={selectedId === e.entityId}
                              onSelect={() => onSelect(e.entityId, e.entityName)} />
                          ))}
                        </HistoryTreeNode>
                      ))}
                    </div>
                  );
                }}
              </NrqlQuery>
            );
          }}
        </NrqlQuery>
      </div>
    );
  }
  ```

- [ ] **Step 2: Replace the left-panel placeholder with `<EntityTree>`**

  In the main `ChangeHistory` return, replace:
  ```jsx
  <div style={{ fontSize: '11px', opacity: 0.4 }}>Entity tree coming soon…</div>
  ```
  with:
  ```jsx
  <EntityTree accountId={accountId} orgId={orgId} fromDate={fromDate} toDate={toDate}
    selectedId={selectedEntityId} onSelect={handleSelect} />
  ```

- [ ] **Step 3: Verify in browser**

  Left panel should show a tree of networks, each with entities and `(N)` change count badges. Clicking 7d/30d/90d updates the tree. Clicking an entity highlights it.

- [ ] **Step 4: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/ChangeHistory.js
  git commit -m "feat(nerdpack): add entity tree with change counts to History tab left panel"
  ```

---

### Task 4: ChangeHistory — right panel with collapsed diff tiles

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ChangeHistory.js`

Add `parseSummaryBadges`, `DiffTile` (collapsed header only), and `RightPanel`. Replace the right-panel placeholder with `<RightPanel>`.

- [ ] **Step 1: Add helpers and components before the main export**

  Insert the following after the `EntityTree` closing `}` and before `export default function ChangeHistory`:

  ```jsx
  function parseSummaryBadges(summary) {
    if (!summary) return [];
    const patterns = [
      [/(\d+) added/, n => `+ ${n} added`, '#27ae60'],
      [/(\d+) removed/, n => `− ${n} removed`, '#e74c3c'],
      [/(\d+) changed/, n => `~ ${n} changed`, '#e67e22'],
      [/(\d+) secret rotated/, n => `🔒 ${n} secret rotated`, '#8e44ad'],
    ];
    return patterns.flatMap(([re, label, color]) => {
      const m = summary.match(re);
      return m ? [{ text: label(m[1]), color }] : [];
    });
  }

  function DiffTile({ row }) {
    const [expanded, setExpanded] = useState(false);
    const badges = parseSummaryBadges(row.change_summary);
    const dt = row.detected_at ? String(row.detected_at).slice(0, 10) : '';
    return (
      <div style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '4px', marginBottom: '8px', overflow: 'hidden' }}>
        <div onClick={() => setExpanded(e => !e)} style={{
          display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px',
          cursor: 'pointer', background: 'rgba(128,128,128,0.05)',
        }}>
          <span style={{ fontFamily: 'monospace', fontSize: '13px' }}>{expanded ? '▼' : '▶'}</span>
          <span style={{ fontFamily: 'monospace', fontSize: '13px', flex: 1 }}>{row.config_area}</span>
          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
            {badges.map((b, i) => (
              <span key={i} style={{
                fontSize: '11px', padding: '2px 6px', borderRadius: '10px',
                background: `${b.color}22`, color: b.color, fontWeight: 500,
              }}>{b.text}</span>
            ))}
          </div>
          <span style={{ fontSize: '11px', opacity: 0.5, marginLeft: '8px', whiteSpace: 'nowrap' }}>{dt}</span>
        </div>
        {expanded && (
          <div style={{ padding: '12px', borderTop: '1px solid rgba(128,128,128,0.15)', opacity: 0.5, fontSize: '12px' }}>
            Diff view coming in next task…
          </div>
        )}
      </div>
    );
  }

  function RightPanel({ accountId, orgId, selectedEntityId, selectedEntityName, fromDate, toDate }) {
    const fromISO = fromDate.toISOString().slice(0, 10);
    const toISO = toDate.toISOString().slice(0, 10);
    const entityFilter = selectedEntityId ? `AND entity_id = '${selectedEntityId}'` : '';
    const query = `SELECT config_area, change_summary, detected_at, diff_json, from_payload, to_payload
                   FROM MerakiConfigChange
                   WHERE org_id = '${orgId}' ${entityFilter}
                   SINCE '${fromISO}' UNTIL '${toISO}'
                   ORDER BY detected_at DESC LIMIT 100`;
    const headerLabel = selectedEntityName || 'All entities';
    return (
      <div>
        <NrqlQuery accountIds={[accountId]} query={query}>
          {({ data, loading, error }) => {
            if (loading) return <Spinner />;
            if (error) return <span style={{ color: '#c0392b' }}>Failed to load changes.</span>;
            const rows = data?.[0]?.data || [];
            return (
              <>
                <div style={{ marginBottom: '12px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <strong style={{ fontFamily: 'monospace' }}>{headerLabel}</strong>
                  <span style={{ opacity: 0.4 }}>·</span>
                  <span style={{ opacity: 0.6 }}>{rows.length} changes</span>
                  <span style={{ opacity: 0.4 }}>·</span>
                  <span style={{ opacity: 0.5, fontSize: '11px' }}>{fromISO} – {toISO}</span>
                </div>
                {!rows.length
                  ? <p style={{ opacity: 0.6 }}>No changes found for this selection.</p>
                  : <div>{rows.map((row, i) => <DiffTile key={i} row={row} />)}</div>
                }
              </>
            );
          }}
        </NrqlQuery>
      </div>
    );
  }
  ```

- [ ] **Step 2: Replace the right-panel placeholder with `<RightPanel>`**

  In the main `ChangeHistory` return, replace:
  ```jsx
  <div style={{ opacity: 0.4, fontSize: '13px' }}>Diff tiles coming soon…</div>
  ```
  with:
  ```jsx
  <RightPanel accountId={accountId} orgId={orgId}
    selectedEntityId={selectedEntityId} selectedEntityName={selectedEntityName}
    fromDate={fromDate} toDate={toDate} />
  ```

- [ ] **Step 3: Verify in browser**

  Right panel shows change tiles with header row: config_area in monospace, colored badges summarising the change, and date right-aligned. Clicking a tile expands to a placeholder. Clicking an entity in the left tree filters the right panel.

- [ ] **Step 4: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/ChangeHistory.js
  git commit -m "feat(nerdpack): add right panel with collapsible diff tile headers and change badges"
  ```

---

### Task 5: ChangeHistory — before/after JSON diff expansion

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/ChangeHistory.js`

Add `syntaxHighlight` (token colorizer) and `JsonPane` (side-by-side JSON column with line tinting). Replace the placeholder in `DiffTile`'s expanded state with the two-column diff view.

- [ ] **Step 1: Add `syntaxHighlight` and `JsonPane` before `DiffTile`**

  Insert the following between the `parseSummaryBadges` function and the `DiffTile` function:

  ```jsx
  function syntaxHighlight(line) {
    const tokenRegex = /("(?:[^"\\]|\\.)*":?|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}[\],:])/g;
    const result = [];
    let last = 0, m;
    while ((m = tokenRegex.exec(line)) !== null) {
      if (m.index > last) result.push(<span key={`p${last}`}>{line.slice(last, m.index)}</span>);
      const t = m[0];
      let color;
      if (t.endsWith(':') && t.startsWith('"')) color = '#7fb3d3';
      else if (t.startsWith('"')) color = '#a8c97e';
      else if (/^-?\d/.test(t)) color = '#f7ca88';
      else if (t === 'true' || t === 'false' || t === 'null') color = '#c8a2c8';
      else color = 'rgba(200,200,200,0.6)';
      result.push(<span key={m.index} style={{ color }}>{t}</span>);
      last = m.index + t.length;
    }
    if (last < line.length) result.push(<span key={`e${last}`}>{line.slice(last)}</span>);
    return result;
  }

  function JsonPane({ label, jsonStr, otherJsonStr, side }) {
    let lines = [], otherLines = [];
    try {
      lines = JSON.stringify(JSON.parse(jsonStr || '{}'), null, 2).split('\n');
      otherLines = JSON.stringify(JSON.parse(otherJsonStr || '{}'), null, 2).split('\n');
    } catch (_) {
      lines = (jsonStr || '').split('\n');
      otherLines = (otherJsonStr || '').split('\n');
    }
    const otherSet = new Set(otherLines.map(l => l.trim()).filter(Boolean));
    return (
      <div style={{
        flex: 1, overflow: 'auto', maxHeight: '300px',
        borderRight: side === 'from' ? '1px solid rgba(128,128,128,0.15)' : 'none',
      }}>
        <div style={{ fontSize: '11px', opacity: 0.5, padding: '4px 8px', borderBottom: '1px solid rgba(128,128,128,0.1)', fontFamily: 'monospace', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {label}
        </div>
        <pre style={{ margin: 0, padding: '8px', fontSize: '11px', fontFamily: 'monospace', lineHeight: '1.6' }}>
          {lines.map((line, i) => {
            const trimmed = line.trim();
            const changed = trimmed && !otherSet.has(trimmed);
            const bg = changed
              ? (side === 'from' ? 'rgba(231,76,60,0.15)' : 'rgba(39,174,96,0.15)')
              : 'transparent';
            return (
              <div key={i} style={{ background: bg, paddingLeft: '2px' }}>
                {syntaxHighlight(line)}
              </div>
            );
          })}
        </pre>
      </div>
    );
  }
  ```

- [ ] **Step 2: Replace the expanded placeholder in `DiffTile` with the two-column view**

  In `DiffTile`, replace:
  ```jsx
  {expanded && (
    <div style={{ padding: '12px', borderTop: '1px solid rgba(128,128,128,0.15)', opacity: 0.5, fontSize: '12px' }}>
      Diff view coming in next task…
    </div>
  )}
  ```
  with:
  ```jsx
  {expanded && (
    <div style={{ display: 'flex', borderTop: '1px solid rgba(128,128,128,0.15)' }}>
      <JsonPane label="Before" jsonStr={row.from_payload} otherJsonStr={row.to_payload} side="from" />
      <JsonPane label="After" jsonStr={row.to_payload} otherJsonStr={row.from_payload} side="to" />
    </div>
  )}
  ```

- [ ] **Step 3: Verify in browser**

  Expand a diff tile. Two columns appear side by side labeled "Before" and "After". JSON is pretty-printed with syntax colors. Lines that differ from the other side have a red tint (Before) or green tint (After). Each column scrolls independently up to 300px. If a change event predates the Task 1 backend push, `from_payload` and `to_payload` will be empty strings — the panes should render an empty `{}` gracefully.

- [ ] **Step 4: Commit**

  ```bash
  git add nerdpack/nerdlets/config-app/components/ChangeHistory.js
  git commit -m "feat(nerdpack): add before/after JSON diff view with syntax highlight and line tinting"
  ```

---

## Spec Coverage Checklist

- [x] Date range filter with From/To inputs → Task 2
- [x] 7d/30d/90d shortcut buttons (30d default) → Task 2
- [x] Entity tree showing only entities with changes in the range → Task 3
- [x] Network parent nodes from snapshot name lookup → Task 3
- [x] Entity name fallback to entity_id → Task 3
- [x] `(N)` change count badge on leaf items → Task 3
- [x] Clicking entity filters right panel; clicking again deselects → Task 3 + Task 4
- [x] Right panel header: entity name · N changes · date range → Task 4
- [x] Collapsed tile: chevron, config_area, change badges, date → Task 4
- [x] Badge format: `+ N added`, `− N removed`, `~ N changed`, `🔒 N secret rotated` → Task 4
- [x] Expanded tile: Before / After columns → Task 5
- [x] JSON syntax highlighting → Task 5
- [x] Line tinting (orange/red = removed/changed, green = added) → Task 5
- [x] `max-height: 300px` with independent scroll per column → Task 5
- [x] `from_payload` and `to_payload` in change events → Task 1
- [x] Both fields truncated to 4000 chars → Task 1
- [x] Test assertions for new fields → Task 1




