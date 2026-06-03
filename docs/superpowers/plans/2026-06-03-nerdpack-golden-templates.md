# Nerdpack Multiple Golden Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the nerdpack's single in-session network template with a persistent multi-template system supporting site, gateway, switch, and access-point templates — matching the feature already live on the website.

**Architecture:** All changes go into `CompareView.js`. Templates are persisted via NR1 NerdStorage (`AccountStorageMutation`/`AccountStorageQuery`) so they survive page reloads. Scoring stays fully client-side via NRQL — network templates compare `config_hash` per `config_area` across all network snapshots; device templates compare per-device snapshots and group results by `network_id`. No FastAPI backend calls; no TypeScript.

**Tech Stack:** NR1 React SDK (`NrqlQuery`, `AccountStorageMutation`, `AccountStorageQuery`, `Spinner`, `Select`, `SelectItem`), React 16 hooks (`useState`, `useEffect`)

**No test infrastructure exists in the nerdpack** — tasks skip the TDD loop. Manual smoke test via `nr1 nerdpack:serve` is the verification step.

---

## File Map

| File | Change |
|---|---|
| `nerdpack/nerdlets/config-app/components/CompareView.js` | Replace entire `TemplatesTab`; add NerdStorage CRUD hook, `TemplateList`, `PromoteModal`, `DevicePicker`, `ScoreBar`, `NetworkScoreRow`, `NetworkTemplateScoring`, `DeviceScoreRow`, `NetworkDeviceGroup`, `DeviceTemplateScoring` |

---

### Task 1: Imports, constants, and NerdStorage hook

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

- [ ] **Step 1: Update the import line at line 1–2**

Replace:
```js
import React, { useState } from 'react';
import { NrqlQuery, Spinner, Select, SelectItem } from 'nr1';
```
With:
```js
import React, { useState, useEffect } from 'react';
import { NrqlQuery, Spinner, Select, SelectItem, AccountStorageMutation, AccountStorageQuery } from 'nr1';
```

- [ ] **Step 2: Add KIND constants and STORAGE keys after the `nrqlEsc` function (around line 12)**

```js
const KIND_ORDER = ['site', 'gateway', 'switch', 'access_point'];
const KIND_META = {
  site:         { label: 'Site (Network)',  prefix: null },
  gateway:      { label: 'Gateway',         prefix: 'appliance_device_' },
  switch:       { label: 'Switch',          prefix: 'switch_device_' },
  access_point: { label: 'Access Point',    prefix: 'wireless_device_' },
};
const STORAGE_COLLECTION = 'golden-templates';
```

- [ ] **Step 3: Add `useTemplates` hook after the KIND constants**

```js
function useTemplates(accountId, orgId) {
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading]     = useState(true);

  useEffect(() => {
    if (!accountId || !orgId) { setLoading(false); return; }
    setLoading(true);
    AccountStorageQuery.query({
      accountId,
      collection: STORAGE_COLLECTION,
      documentId: orgId,
    }).then(({ data }) => {
      setTemplates((data && data.templates) || []);
      setLoading(false);
    }).catch(() => { setTemplates([]); setLoading(false); });
  }, [accountId, orgId]);

  function save(next) {
    setTemplates(next);
    AccountStorageMutation.mutate({
      accountId,
      actionType: AccountStorageMutation.ACTION_TYPE.WRITE_DOCUMENT,
      collection: STORAGE_COLLECTION,
      documentId: orgId,
      document: { templates: next },
    });
  }

  function addTemplate(tmpl)    { save([...templates, tmpl]); }
  function deleteTemplate(id)   { save(templates.filter(t => t.id !== id)); }

  return { templates, loading, addTemplate, deleteTemplate };
}
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "feat(nerdpack): add NerdStorage hook and KIND constants for golden templates"
```

---

### Task 2: TemplateList component

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

Add the left-panel component that lists saved templates with a "+ Promote" button. Insert before the `CoverageTab` function.

- [ ] **Step 1: Add `TemplateList` component**

```js
function TemplateList({ templates, loading, onSelect, selectedId, onDelete, onPromote }) {
  if (loading) return <Spinner />;
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <span style={{ fontSize: '12px', opacity: 0.6 }}>
          {templates.length} template{templates.length !== 1 ? 's' : ''}
        </span>
        <button
          onClick={onPromote}
          style={{ padding: '5px 12px', background: 'rgba(0,120,191,0.15)', border: '1px solid #0078bf', borderRadius: '4px', color: '#0078bf', fontSize: '12px', cursor: 'pointer' }}>
          + Promote
        </button>
      </div>

      {templates.length === 0 && (
        <p style={{ opacity: 0.5, fontSize: '12px' }}>No templates yet. Click "+ Promote" to create one.</p>
      )}

      {templates.map(t => {
        const meta       = KIND_META[t.kind] || KIND_META.site;
        const isSelected = t.id === selectedId;
        return (
          <div
            key={t.id}
            onClick={() => onSelect(t)}
            style={{
              display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px',
              border: `1px solid ${isSelected ? '#0078bf' : 'rgba(128,128,128,0.2)'}`,
              background: isSelected ? 'rgba(0,120,191,0.08)' : 'transparent',
              borderRadius: '5px', marginBottom: '6px', cursor: 'pointer',
            }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: '13px', fontWeight: isSelected ? 600 : 400, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.name}</div>
              <div style={{ fontSize: '11px', opacity: 0.5, marginTop: '2px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {meta.label} · {t.source_entity_name || t.source_entity_id}
              </div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(t.id); }}
              style={{ background: 'transparent', border: 'none', color: '#e74c3c', cursor: 'pointer', fontSize: '14px', opacity: 0.6, padding: '2px 4px', flexShrink: 0 }}>
              ✕
            </button>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "feat(nerdpack): add TemplateList component"
```

---

### Task 3: PromoteModal with kind + network + device selection

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

The modal collects kind → network → (for non-site kinds) a device → template name. Insert before `CoverageTab`.

- [ ] **Step 1: Add `DevicePicker` component**

```js
function DevicePicker({ accountId, orgId, networkId, kind, selectedSerial, onSelect }) {
  const prefix = KIND_META[kind] && KIND_META[kind].prefix;
  const query = prefix
    ? `SELECT latest(entity_name) FROM MerakiConfigSnapshot
       WHERE org_id = '${nrqlEsc(orgId)}'
         AND entity_type = 'device'
         AND network_id = '${nrqlEsc(networkId)}'
         AND config_area LIKE '${prefix}%'
       FACET entity_id SINCE 30 days ago LIMIT 100`
    : null;

  if (!query) return null;

  return (
    <NrqlQuery accountIds={[accountId]} query={query}>
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const devices = (data || []).map(s => {
          const serial = s.metadata && s.metadata.groups && s.metadata.groups.find(g => g.type === 'facet') && s.metadata.groups.find(g => g.type === 'facet').value;
          const name   = (s.data && s.data[0] && (s.data[0]['latest.entity_name'] || s.data[0]['entity_name'])) || serial;
          return serial ? { serial, name: name || serial } : null;
        }).filter(Boolean);

        if (!devices.length) {
          return <p style={{ fontSize: '11px', color: '#e67e22', margin: '4px 0' }}>No {KIND_META[kind].label.toLowerCase()} devices found in this network.</p>;
        }

        return (
          <div style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '4px', maxHeight: '140px', overflowY: 'auto', marginTop: '4px' }}>
            {devices.map(d => (
              <div
                key={d.serial}
                onClick={() => onSelect(d)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '8px',
                  padding: '7px 10px', cursor: 'pointer',
                  background: selectedSerial === d.serial ? 'rgba(0,120,191,0.12)' : 'transparent',
                  borderLeft: `2px solid ${selectedSerial === d.serial ? '#0078bf' : 'transparent'}`,
                }}>
                <span style={{ fontSize: '12px', flex: 1 }}>{d.name}</span>
                <span style={{ fontSize: '10px', opacity: 0.4, fontFamily: 'monospace' }}>{d.serial}</span>
              </div>
            ))}
          </div>
        );
      }}
    </NrqlQuery>
  );
}
```

- [ ] **Step 2: Add `PromoteModal` component**

```js
function PromoteModal({ accountId, orgId, onConfirm, onCancel }) {
  const [kind, setKind]               = useState('');
  const [networkId, setNetworkId]     = useState(null);
  const [networkName, setNetworkName] = useState(null);
  const [device, setDevice]           = useState(null); // { serial, name }
  const [name, setName]               = useState('');

  const needsDevice = kind && kind !== 'site';
  const canSave     = name.trim() && networkId && kind && (kind === 'site' || device);

  function handleConfirm() {
    onConfirm({
      id:                  String(Date.now()),
      name:                name.trim(),
      kind,
      org_id:              orgId,
      source_entity_id:    needsDevice ? device.serial    : networkId,
      source_entity_name:  needsDevice ? device.name      : networkName,
      source_entity_type:  needsDevice ? 'device'         : 'network',
      source_network_id:   networkId,
      created_at:          new Date().toISOString(),
    });
  }

  const inputStyle = {
    width: '100%', background: 'rgba(255,255,255,0.05)',
    border: '1px solid rgba(255,255,255,0.12)', borderRadius: '4px',
    padding: '7px 10px', fontSize: '12px', color: 'inherit', boxSizing: 'border-box',
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
      <div style={{ background: '#1a1a2e', border: '1px solid rgba(255,255,255,0.12)', borderRadius: '8px', padding: '20px', width: '340px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, marginBottom: '16px' }}>Promote as Golden Template</div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ fontSize: '11px', opacity: 0.5, display: 'block', marginBottom: '4px' }}>Template type</label>
          <select value={kind} onChange={e => { setKind(e.target.value); setDevice(null); }} style={inputStyle}>
            <option value="">Select a type…</option>
            {KIND_ORDER.map(k => <option key={k} value={k}>{KIND_META[k].label}</option>)}
          </select>
        </div>

        <div style={{ marginBottom: '14px' }}>
          <label style={{ fontSize: '11px', opacity: 0.5, display: 'block', marginBottom: '4px' }}>
            {needsDevice ? 'Step 1 — Pick a network' : 'Network'}
          </label>
          <NetworkSelector
            accountId={accountId} orgId={orgId} label="" value={networkId}
            onChange={(id, nm) => { setNetworkId(id); setNetworkName(nm); setDevice(null); }}
          />
        </div>

        {needsDevice && networkId && (
          <div style={{ marginBottom: '14px' }}>
            <label style={{ fontSize: '11px', opacity: 0.5, display: 'block', marginBottom: '4px' }}>
              Step 2 — Pick a {KIND_META[kind].label.toLowerCase()}
            </label>
            <DevicePicker
              accountId={accountId} orgId={orgId}
              networkId={networkId} kind={kind}
              selectedSerial={device && device.serial}
              onSelect={d => setDevice(d)}
            />
          </div>
        )}

        <div style={{ marginBottom: '14px' }}>
          <label style={{ fontSize: '11px', opacity: 0.5, display: 'block', marginBottom: '4px' }}>Template name</label>
          <input
            type="text" value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Standard Core Switch"
            style={inputStyle}
          />
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button onClick={onCancel} style={{ padding: '6px 14px', background: 'transparent', border: '1px solid rgba(128,128,128,0.3)', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
          <button
            onClick={handleConfirm}
            disabled={!canSave}
            style={{ padding: '6px 14px', background: canSave ? 'rgba(0,120,191,0.8)' : 'rgba(128,128,128,0.2)', border: 'none', borderRadius: '4px', cursor: canSave ? 'pointer' : 'not-allowed', color: canSave ? '#fff' : 'inherit', fontSize: '12px' }}>
            Save Template
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "feat(nerdpack): add PromoteModal with kind/network/device picker"
```

---

### Task 4: Network template scoring panel

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

For site/network templates: query all network `config_hash` values via NRQL, compare each network's hashes against the golden network, show a collapsible scored list. Scoring uses hash comparison (exact match) per config area. Insert before `CoverageTab`.

- [ ] **Step 1: Add `ScoreBar`, `NetworkScoreRow`, and `NetworkTemplateScoring` components**

```js
function ScoreBar({ pct }) {
  const color = pct >= 90 ? '#27ae60' : pct >= 60 ? '#e67e22' : '#e74c3c';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, height: '5px', background: 'rgba(128,128,128,0.15)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: '3px' }} />
      </div>
      <span style={{ fontSize: '12px', fontWeight: 600, color, minWidth: '34px', textAlign: 'right' }}>{pct}%</span>
    </div>
  );
}

function NetworkScoreRow({ score, nameMap }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '4px', marginBottom: '8px', overflow: 'hidden' }}>
      <div onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '9px 12px', cursor: 'pointer', background: 'rgba(128,128,128,0.03)' }}>
        <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{open ? '▼' : '▶'}</span>
        <span style={{ flex: 1, fontSize: '13px' }}>{nameMap[score.network_id] || score.network_id}</span>
        <span style={{ fontSize: '11px', opacity: 0.4 }}>{score.matched}/{score.total} areas</span>
        <div style={{ width: '140px' }}><ScoreBar pct={score.pct} /></div>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid rgba(128,128,128,0.1)', padding: '8px 12px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {score.area_scores.map(a => (
              <span key={a.area} style={{
                fontSize: '10px', padding: '2px 7px', borderRadius: '10px',
                background: a.match ? 'rgba(39,174,96,0.15)' : a.missing ? 'rgba(128,128,128,0.1)' : 'rgba(231,76,60,0.15)',
                color: a.match ? '#27ae60' : a.missing ? '#999' : '#e74c3c',
              }}>
                {a.area} {a.match ? '✓' : a.missing ? '⊘' : '✗'}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function NetworkTemplateScoring({ accountId, orgId, template }) {
  const query = `SELECT latest(config_hash) FROM MerakiConfigSnapshot
                 WHERE org_id = '${nrqlEsc(orgId)}' AND entity_type = 'network'
                 FACET entity_id, config_area
                 SINCE 30 days ago LIMIT MAX`;
  return (
    <WithNetworkNames accountId={accountId} orgId={orgId}>
      {(nameMap) => (
        <NrqlQuery accountIds={[accountId]} query={query}>
          {({ data, loading, error }) => {
            if (loading) return <Spinner />;
            if (error) return <p style={{ color: '#c0392b', fontSize: '12px' }}>Failed to load snapshot data.</p>;

            // Build: { networkId -> { configArea -> hash } }
            const snapshots = {};
            (data || []).forEach(s => {
              const fg       = (s.metadata && s.metadata.groups || []).filter(g => g.type === 'facet');
              const entityId = fg[0] && fg[0].value;
              const area     = fg[1] && fg[1].value;
              if (!entityId || !area) return;
              const hash = s.data && s.data[0] && (s.data[0]['latest.config_hash'] || s.data[0]['config_hash']) || null;
              if (!snapshots[entityId]) snapshots[entityId] = {};
              snapshots[entityId][area] = hash;
            });

            const templateAreas    = snapshots[template.source_entity_id] || {};
            const templateAreaKeys = Object.keys(templateAreas);

            if (!templateAreaKeys.length) {
              return <p style={{ opacity: 0.6, fontSize: '12px' }}>No snapshot data found for the golden network.</p>;
            }

            const scores = Object.entries(snapshots)
              .filter(([id]) => id !== template.source_entity_id)
              .map(([networkId, areaMap]) => {
                let matched = 0;
                const area_scores = templateAreaKeys.map(a => {
                  if (!areaMap[a]) return { area: a, match: false, missing: true };
                  const match = areaMap[a] === templateAreas[a];
                  if (match) matched++;
                  return { area: a, match, missing: false };
                });
                const pct = Math.round((matched / templateAreaKeys.length) * 100);
                return { network_id: networkId, matched, total: templateAreaKeys.length, pct, area_scores };
              })
              .sort((a, b) => a.pct - b.pct);

            if (!scores.length) {
              return <p style={{ opacity: 0.6, fontSize: '12px' }}>No other networks to score.</p>;
            }

            return (
              <div>
                <div style={{ marginBottom: '14px', fontSize: '12px', opacity: 0.6 }}>
                  Template: <strong>{template.source_entity_name || template.source_entity_id}</strong> · {templateAreaKeys.length} config areas
                </div>
                {scores.map(score => <NetworkScoreRow key={score.network_id} score={score} nameMap={nameMap} />)}
              </div>
            );
          }}
        </NrqlQuery>
      )}
    </WithNetworkNames>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "feat(nerdpack): add network template scoring panel"
```

---

### Task 5: Device template scoring panel

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

For device templates (gateway/switch/access_point): query all device snapshots matching the kind's `config_area` prefix, score each device's hashes against the golden device, group results by `network_id`. Insert before `CoverageTab`.

- [ ] **Step 1: Add `DeviceScoreRow`, `NetworkDeviceGroup`, and `DeviceTemplateScoring` components**

```js
function DeviceScoreRow({ device }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: '1px solid rgba(128,128,128,0.15)', borderRadius: '4px', marginBottom: '6px', overflow: 'hidden' }}>
      <div onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', cursor: 'pointer' }}>
        <span style={{ flex: 1, fontSize: '12px' }}>{device.name}</span>
        <span style={{ fontSize: '10px', opacity: 0.4, fontFamily: 'monospace' }}>{device.serial}</span>
        <div style={{ width: '130px' }}><ScoreBar pct={device.pct} /></div>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid rgba(128,128,128,0.1)', padding: '8px 12px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
            {device.area_scores.map(a => (
              <span key={a.area} style={{
                fontSize: '10px', padding: '2px 7px', borderRadius: '10px',
                background: a.match ? 'rgba(39,174,96,0.15)' : a.missing ? 'rgba(128,128,128,0.1)' : 'rgba(231,76,60,0.15)',
                color: a.match ? '#27ae60' : a.missing ? '#999' : '#e74c3c',
              }}>
                {a.area} {a.match ? '✓' : a.missing ? '⊘' : '✗'}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function NetworkDeviceGroup({ networkId, networkName, devices }) {
  const [open, setOpen] = useState(false);
  const avg   = devices.length ? Math.round(devices.reduce((s, d) => s + d.pct, 0) / devices.length) : 0;
  const color = avg >= 90 ? '#27ae60' : avg >= 60 ? '#e67e22' : '#e74c3c';
  return (
    <div style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '4px', marginBottom: '10px', overflow: 'hidden' }}>
      <div onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 14px', cursor: 'pointer', background: 'rgba(128,128,128,0.04)' }}>
        <span style={{ fontFamily: 'monospace', fontSize: '12px' }}>{open ? '▼' : '▶'}</span>
        <span style={{ flex: 1, fontSize: '13px', fontWeight: 500 }}>{networkName || networkId}</span>
        <span style={{ fontSize: '11px', opacity: 0.4 }}>{devices.length} device{devices.length !== 1 ? 's' : ''}</span>
        <span style={{ fontSize: '14px', fontWeight: 700, color }}>{avg}%</span>
      </div>
      {open && (
        <div style={{ borderTop: '1px solid rgba(128,128,128,0.1)', padding: '8px 12px' }}>
          {devices.map(d => <DeviceScoreRow key={d.serial} device={d} />)}
        </div>
      )}
    </div>
  );
}

function DeviceTemplateScoring({ accountId, orgId, template }) {
  const prefix = KIND_META[template.kind] && KIND_META[template.kind].prefix;
  const query = prefix
    ? `SELECT latest(config_hash), latest(entity_name), latest(network_id) FROM MerakiConfigSnapshot
       WHERE org_id = '${nrqlEsc(orgId)}'
         AND entity_type = 'device'
         AND config_area LIKE '${prefix}%'
       FACET entity_id, config_area
       SINCE 30 days ago LIMIT MAX`
    : null;

  if (!query) return <p style={{ opacity: 0.6, fontSize: '12px' }}>Unsupported template kind.</p>;

  return (
    <WithNetworkNames accountId={accountId} orgId={orgId}>
      {(nameMap) => (
        <NrqlQuery accountIds={[accountId]} query={query}>
          {({ data, loading, error }) => {
            if (loading) return <Spinner />;
            if (error) return <p style={{ color: '#c0392b', fontSize: '12px' }}>Failed to load device snapshot data.</p>;

            // Build: { serial -> { name, network_id, areas: { config_area -> hash } } }
            const deviceSnaps = {};
            (data || []).forEach(s => {
              const fg     = (s.metadata && s.metadata.groups || []).filter(g => g.type === 'facet');
              const serial = fg[0] && fg[0].value;
              const area   = fg[1] && fg[1].value;
              if (!serial || !area) return;
              const hash      = s.data && s.data[0] && (s.data[0]['latest.config_hash'] || s.data[0]['config_hash']) || null;
              const devName   = s.data && s.data[0] && (s.data[0]['latest.entity_name'] || s.data[0]['entity_name']) || serial;
              const networkId = s.data && s.data[0] && (s.data[0]['latest.network_id'] || s.data[0]['network_id']) || '__unknown__';
              if (!deviceSnaps[serial]) deviceSnaps[serial] = { name: devName, network_id: networkId, areas: {} };
              deviceSnaps[serial].areas[area] = hash;
            });

            const golden         = deviceSnaps[template.source_entity_id];
            const goldenAreaKeys = golden ? Object.keys(golden.areas) : [];

            if (!golden || !goldenAreaKeys.length) {
              return <p style={{ opacity: 0.6, fontSize: '12px' }}>No snapshot data found for golden device ({template.source_entity_name || template.source_entity_id}).</p>;
            }

            // Score each device against the golden
            const deviceScores = Object.entries(deviceSnaps)
              .filter(([serial]) => serial !== template.source_entity_id)
              .map(([serial, snap]) => {
                let matched = 0;
                const area_scores = goldenAreaKeys.map(a => {
                  if (!snap.areas[a]) return { area: a, match: false, missing: true };
                  const match = snap.areas[a] === golden.areas[a];
                  if (match) matched++;
                  return { area: a, match, missing: false };
                });
                const pct = Math.round((matched / goldenAreaKeys.length) * 100);
                return { serial, name: snap.name, network_id: snap.network_id, pct, area_scores };
              });

            // Group by network_id
            const netGroups = {};
            deviceScores.forEach(d => {
              if (!netGroups[d.network_id]) netGroups[d.network_id] = [];
              netGroups[d.network_id].push(d);
            });
            const sortedNets = Object.entries(netGroups)
              .map(([nid, devices]) => ({
                networkId: nid,
                devices:   devices.sort((a, b) => a.pct - b.pct),
                avg:       Math.round(devices.reduce((s, d) => s + d.pct, 0) / devices.length),
              }))
              .sort((a, b) => a.avg - b.avg);

            if (!sortedNets.length) {
              return <p style={{ opacity: 0.6, fontSize: '12px' }}>No other {KIND_META[template.kind].label} devices found.</p>;
            }

            return (
              <div>
                <div style={{ marginBottom: '14px', fontSize: '12px', opacity: 0.6 }}>
                  Golden device: <strong>{template.source_entity_name || template.source_entity_id}</strong> · {goldenAreaKeys.length} config areas
                </div>
                {sortedNets.map(({ networkId, devices }) => (
                  <NetworkDeviceGroup
                    key={networkId}
                    networkId={networkId}
                    networkName={networkId === '__unknown__' ? 'Unknown network' : (nameMap[networkId] || networkId)}
                    devices={devices}
                  />
                ))}
              </div>
            );
          }}
        </NrqlQuery>
      )}
    </WithNetworkNames>
  );
}
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "feat(nerdpack): add device template scoring panel grouped by network"
```

---

### Task 6: Replace TemplatesTab and wire everything together

**Files:**
- Modify: `nerdpack/nerdlets/config-app/components/CompareView.js`

Delete the entire existing `TemplatesTab` function (lines ~309–420) and replace with the wired-up version.

- [ ] **Step 1: Replace `TemplatesTab` with the wired-up version**

```js
function TemplatesTab({ accountId, orgId }) {
  const { templates, loading, addTemplate, deleteTemplate } = useTemplates(accountId, orgId);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [showPromote, setShowPromote]            = useState(false);

  function handlePromote(tmpl) {
    addTemplate(tmpl);
    setShowPromote(false);
    setSelectedTemplate(tmpl);
  }

  function handleDelete(id) {
    deleteTemplate(id);
    if (selectedTemplate && selectedTemplate.id === id) setSelectedTemplate(null);
  }

  const isDevice = selectedTemplate && selectedTemplate.source_entity_type === 'device';

  return (
    <div style={{ display: 'flex', gap: '20px' }}>
      <div style={{ width: '260px', flexShrink: 0 }}>
        <TemplateList
          templates={templates}
          loading={loading}
          selectedId={selectedTemplate && selectedTemplate.id}
          onSelect={setSelectedTemplate}
          onDelete={handleDelete}
          onPromote={() => setShowPromote(true)}
        />
      </div>

      <div style={{ flex: 1, minWidth: 0 }}>
        {!selectedTemplate && !loading && (
          <p style={{ opacity: 0.5, fontSize: '12px' }}>
            {templates.length === 0
              ? 'Create a golden template to start scoring your networks and devices.'
              : 'Select a template on the left to see compliance scores.'}
          </p>
        )}

        {selectedTemplate && (
          isDevice
            ? <DeviceTemplateScoring accountId={accountId} orgId={orgId} template={selectedTemplate} />
            : <NetworkTemplateScoring accountId={accountId} orgId={orgId} template={selectedTemplate} />
        )}
      </div>

      {showPromote && (
        <PromoteModal
          accountId={accountId}
          orgId={orgId}
          onConfirm={handlePromote}
          onCancel={() => setShowPromote(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify the build compiles**

```bash
cd "/Users/jkarnik/Code/Topology Maps/nerdpack"
nr1 nerdpack:build 2>&1 | tail -20
```

Expected: build succeeds with no errors. If there are syntax errors, fix them and re-run.

- [ ] **Step 3: Commit**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "feat(nerdpack): wire TemplatesTab with multi-template list and scoring"
```

---

### Task 7: Smoke test

- [ ] **Step 1: Serve the nerdpack locally**

```bash
cd "/Users/jkarnik/Code/Topology Maps/nerdpack"
nr1 nerdpack:serve
```

Open the NR1 app (follow terminal URL). Navigate: Config App → Compare tab → Golden Template Comparator sub-tab.

Verify:
1. Left panel shows "0 templates" with a "+ Promote" button
2. Clicking "+ Promote" opens the modal with a "Template type" dropdown
3. Selecting "Site (Network)" shows only the network selector — no device picker
4. Selecting "Switch" shows "Step 1 — Pick a network", then after picking a network shows "Step 2 — Pick a switch" with device list from NRQL
5. Filling in a name and clicking "Save Template" adds the template to the list and auto-selects it
6. Reloading the page shows the template persists (loaded from NerdStorage)
7. A Site template shows the network scoring panel with collapsible rows
8. A device template shows devices grouped by network
9. Clicking ✕ on a template removes it and clears NerdStorage

- [ ] **Step 2: Final commit if any fixes needed**

```bash
cd "/Users/jkarnik/Code/Topology Maps"
git add nerdpack/nerdlets/config-app/components/CompareView.js
git commit -m "fix(nerdpack): smoke test fixes for golden templates"
```
