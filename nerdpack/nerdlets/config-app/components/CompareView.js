import React, { useState, useEffect } from 'react';
import { NrqlQuery, Spinner, Select, SelectItem, AccountStorageMutation, AccountStorageQuery } from 'nr1';

// ── Module-level helpers ────────────────────────────────────────────────────

function cellColor(ts, now, STALE_MS) {
  if (ts == null) return 'rgba(128,128,128,0.12)';
  return (now - ts) > STALE_MS ? '#e67e22' : '#27ae60';
}

function pctColor(pct) {
  if (pct >= 80) return '#27ae60';
  if (pct >= 50) return '#e67e22';
  return '#e74c3c';
}


function safeParse(str) {
  if (!str) return null;
  try { return JSON.stringify(JSON.parse(str), null, 2).split('\n'); }
  catch (_) { return str.split('\n'); }
}

function syntaxHighlight(line) {
  const tokenRegex = /("(?:[^"\\]|\\.)*":?|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null|[{}[\],:])/g;
  const result = [];
  let last = 0, m;
  while ((m = tokenRegex.exec(line)) !== null) {
    if (m.index > last) result.push(<span key={`p${last}`}>{line.slice(last, m.index)}</span>);
    const t = m[0];
    let cls;
    if (t.endsWith(':') && t.startsWith('"')) cls = 'json-key';
    else if (t.startsWith('"')) cls = 'json-str';
    else if (/^-?\d/.test(t)) cls = 'json-num';
    else if (t === 'true' || t === 'false') cls = 'json-bool';
    else if (t === 'null') cls = 'json-null';
    result.push(<span key={m.index} className={cls}>{t}</span>);
    last = m.index + t.length;
  }
  if (last < line.length) result.push(<span key={`e${last}`}>{line.slice(last)}</span>);
  return result;
}

function computeCompareBadges(jsonA, jsonB) {
  const linesA = new Set((safeParse(jsonA) || []).map(l => l.trim()).filter(Boolean));
  const linesB = new Set((safeParse(jsonB) || []).map(l => l.trim()).filter(Boolean));
  const added = [...linesB].filter(l => !linesA.has(l)).length;
  const removed = [...linesA].filter(l => !linesB.has(l)).length;
  const badges = [];
  if (added) badges.push({ text: `+ ${added} added`, color: '#27ae60' });
  if (removed) badges.push({ text: `− ${removed} removed`, color: '#e74c3c' });
  return badges;
}

const KIND_ORDER = ['site', 'gateway', 'switch', 'access_point'];
const KIND_META = {
  site:         { label: 'Site (Network)',  prefix: null },
  gateway:      { label: 'Gateway',         prefix: 'appliance_device_' },
  switch:       { label: 'Switch',          prefix: 'switch_device_' },
  access_point: { label: 'Access Point',    prefix: 'wireless_device_' },
};
const STORAGE_COLLECTION = 'golden-templates';

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
    }).catch(() => {});
  }

  function addTemplate(tmpl)    { save([...templates, tmpl]); }
  function deleteTemplate(id)   { save(templates.filter(t => t.id !== id)); }

  return { templates, loading, addTemplate, deleteTemplate };
}

function CompareJsonPane({ label, jsonStr, otherJsonStr, side }) {
  const borderStyle = { flex: 1, overflow: 'auto', maxHeight: '400px', borderRight: side === 'left' ? '1px solid rgba(128,128,128,0.15)' : 'none' };
  const labelEl = <div style={{ fontSize: '11px', opacity: 0.5, padding: '4px 8px', borderBottom: '1px solid rgba(128,128,128,0.1)', fontFamily: 'monospace', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>;
  const lines = safeParse(jsonStr);
  if (!lines) {
    return (
      <div style={borderStyle}>
        {labelEl}
        <p style={{ opacity: 0.4, fontSize: '11px', padding: '8px', fontStyle: 'italic' }}>(not observed)</p>
      </div>
    );
  }
  const otherLines = safeParse(otherJsonStr) || [];
  const otherSet = new Set(otherLines.map(l => l.trim()).filter(Boolean));
  return (
    <div style={borderStyle}>
      {labelEl}
      <pre style={{ margin: 0, padding: '8px', fontSize: '11px', fontFamily: 'monospace', lineHeight: '1.6' }}>
        {lines.map((line, i) => {
          const trimmed = line.trim();
          const changed = trimmed && !otherSet.has(trimmed);
          const bg = changed
            ? (side === 'left' ? 'rgba(231,76,60,0.15)' : 'rgba(39,174,96,0.15)')
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

function CompareTile({ area, jsonA, jsonB, labelA, labelB }) {
  const [expanded, setExpanded] = useState(false);
  const badges = computeCompareBadges(jsonA, jsonB);
  return (
    <div style={{ border: '1px solid rgba(128,128,128,0.2)', borderRadius: '4px', marginBottom: '8px', overflow: 'hidden' }}>
      <div onClick={() => setExpanded(e => !e)} style={{
        display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 12px',
        cursor: 'pointer', background: 'rgba(128,128,128,0.05)',
      }}>
        <span style={{ fontFamily: 'monospace', fontSize: '13px' }}>{expanded ? '▼' : '▶'}</span>
        <span style={{ fontFamily: 'monospace', fontSize: '13px', flex: 1 }}>{area}</span>
        <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
          {badges.map((b, i) => (
            <span key={i} style={{
              fontSize: '11px', padding: '2px 6px', borderRadius: '10px',
              background: `${b.color}22`, color: b.color, fontWeight: 500,
            }}>{b.text}</span>
          ))}
        </div>
      </div>
      {expanded && (
        <div style={{ display: 'flex', borderTop: '1px solid rgba(128,128,128,0.15)' }}>
          <CompareJsonPane label={labelA} jsonStr={jsonA} otherJsonStr={jsonB} side="left" />
          <CompareJsonPane label={labelB} jsonStr={jsonB} otherJsonStr={jsonA} side="right" />
        </div>
      )}
    </div>
  );
}

function CompareDiffView({ accountId, netA, netB, nameA, nameB }) {
  const q = (id) => `SELECT latest(config_json) AS json FROM MerakiConfigSnapshot
                     WHERE entity_id = '${id}' FACET config_area SINCE 30 days ago LIMIT MAX`;
  return (
    <>
      <style>{`
        .json-key  { color: #0066cc; }
        .json-str  { color: #a31515; }
        .json-num  { color: #098658; }
        .json-bool { color: #0000ff; }
        .json-null { color: #dd0000; }
        @media (prefers-color-scheme: dark) {
          .json-key  { color: #9cdcfe; }
          .json-str  { color: #ce9178; }
          .json-num  { color: #b5cea8; }
          .json-bool { color: #569cd6; }
          .json-null { color: #f44747; }
        }
      `}</style>
      <NrqlQuery accountIds={[accountId]} query={q(netA)}>
        {({ data: dA, loading: lA }) => (
          <NrqlQuery accountIds={[accountId]} query={q(netB)}>
            {({ data: dB, loading: lB }) => {
              if (lA || lB) return <Spinner />;
              const mapA = {}, mapB = {};
              (dA || []).forEach((s) => { const k = (s.metadata.groups||[]).find(g=>g.type==='facet')?.value; if(k) mapA[k] = s.data?.[0]?.['config_json'] || s.data?.[0]?.['latest.config_json'] || s.data?.[0]?.json; });
              (dB || []).forEach((s) => { const k = (s.metadata.groups||[]).find(g=>g.type==='facet')?.value; if(k) mapB[k] = s.data?.[0]?.['config_json'] || s.data?.[0]?.['latest.config_json'] || s.data?.[0]?.json; });
              const allAreas = [...new Set([...Object.keys(mapA), ...Object.keys(mapB)])].sort();
              const diffAreas = allAreas.filter((a) => mapA[a] !== mapB[a]);
              if (!diffAreas.length) return <p style={{ color: '#27ae60' }}>Networks are identical across all observed config areas.</p>;
              const labelA = nameA || netA;
              const labelB = nameB || netB;
              return (
                <div>
                  <div style={{ marginBottom: '12px', fontSize: '12px', opacity: 0.6 }}>
                    {diffAreas.length} config area{diffAreas.length !== 1 ? 's' : ''} differ · click a tile to expand
                  </div>
                  {diffAreas.map(area => (
                    <CompareTile key={area} area={area}
                      jsonA={mapA[area]} jsonB={mapB[area]}
                      labelA={labelA} labelB={labelB} />
                  ))}
                </div>
              );
            }}
          </NrqlQuery>
        )}
      </NrqlQuery>
    </>
  );
}

// ── Sub-components ──────────────────────────────────────────────────────────

// Fetches { entityId -> name } for all networks in the org and passes it to children.
// Re-uses the same query that drives the dropdown selectors (which is known to work).
function WithNetworkNames({ accountId, orgId, children }) {
  const query = `SELECT latest(entity_name) FROM MerakiConfigSnapshot
                 WHERE org_id = '${orgId}' AND entity_type = 'network'
                 FACET entity_id SINCE 30 days ago LIMIT 100`;
  return (
    <NrqlQuery accountIds={[accountId]} query={query}>
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const nameMap = {};
        (data || []).forEach(s => {
          const id = s.metadata?.groups?.find(g => g.type === 'facet')?.value;
          const name = s.data?.[0]?.['entity_name'] ?? s.data?.[0]?.['latest.entity_name'] ?? null;
          if (id) nameMap[id] = name || id;
        });
        return children(nameMap);
      }}
    </NrqlQuery>
  );
}

function NetworkSelector({ accountId, orgId, label, value, onChange }) {
  return (
    <NrqlQuery accountIds={[accountId]}
      query={`SELECT latest(entity_name) FROM MerakiConfigSnapshot
              WHERE org_id = '${orgId}' AND entity_type = 'network'
              FACET entity_id SINCE 30 days ago LIMIT 100`}>
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const networks = (data || []).map(s => {
          const id = s.metadata?.groups?.find(g => g.type === 'facet')?.value;
          const name = s.data?.[0]?.['entity_name'] ?? s.data?.[0]?.['latest.entity_name'] ?? id;
          return id ? { id, name: name || id } : null;
        }).filter(Boolean);
        return (
          <Select label={label} value={value} onChange={(_, v) => {
            const net = networks.find(n => n.id === v);
            onChange(v, net?.name || v);
          }}>
            <SelectItem value={null}>— Select network —</SelectItem>
            {networks.map(({ id, name }) => <SelectItem key={id} value={id}>{name}</SelectItem>)}
          </Select>
        );
      }}
    </NrqlQuery>
  );
}

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

function DevicePicker({ accountId, orgId, networkId, kind, selectedSerial, onSelect }) {
  const prefix = KIND_META[kind] && KIND_META[kind].prefix;
  const query = prefix
    ? `SELECT latest(entity_name) FROM MerakiConfigSnapshot
       WHERE org_id = '${orgId}'
         AND entity_type = 'device'
         AND network_id = '${networkId}'
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
    width: '100%', background: 'rgba(0,0,0,0.04)',
    border: '1px solid rgba(0,0,0,0.15)', borderRadius: '4px',
    padding: '7px 10px', fontSize: '12px', color: 'inherit', boxSizing: 'border-box',
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 9999 }}>
      <div style={{ background: '#ffffff', border: '1px solid rgba(0,0,0,0.15)', borderRadius: '8px', padding: '20px', width: '340px' }}>
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
                 WHERE org_id = '${orgId}' AND entity_type = 'network'
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

function DeviceScoreRow({ device }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ border: '1px solid rgba(128,128,128,0.15)', borderRadius: '4px', marginBottom: '6px', overflow: 'hidden' }}>
      <div onClick={() => setOpen(o => !o)} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', cursor: 'pointer' }}>
        <span style={{ fontFamily: 'monospace', fontSize: '11px', opacity: 0.5 }}>{open ? '▼' : '▶'}</span>
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
       WHERE org_id = '${orgId}'
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

function CoverageTab({ accountId, orgId }) {
  const query = `SELECT latest(timestamp) FROM MerakiConfigSnapshot
                 WHERE org_id = '${orgId}'
                 FACET entity_id, config_area
                 SINCE 30 days ago LIMIT MAX`;
  return (
    <WithNetworkNames accountId={accountId} orgId={orgId}>
      {(nameMap) => {
        const networkIds = new Set(Object.keys(nameMap));
        return (
          <NrqlQuery accountIds={[accountId]} query={query}>
            {({ data, loading, error }) => {
              if (loading) return <Spinner />;
              if (error) return <p style={{ color: '#c0392b' }}>Failed to load coverage data.</p>;

              const now = Date.now();
              const STALE_MS = 7 * 24 * 60 * 60 * 1000;

              const matrix = {};
              const allAreas = new Set();
              (data || []).forEach(s => {
                const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
                const entityId = fg[0]?.value;
                const area = fg[1]?.value;
                if (!entityId || !area || !networkIds.has(entityId)) return;
                const ts = s.data?.[0]?.['latest.timestamp'] ?? s.data?.[0]?.['timestamp'] ?? null;
                if (!matrix[entityId]) matrix[entityId] = {};
                matrix[entityId][area] = ts ? Number(ts) : null;
                allAreas.add(area);
              });

              const areas = [...allAreas].sort();
              const rows = Object.entries(matrix).map(([entityId, areaMap]) => {
                const observed = areas.filter(a => areaMap[a] != null).length;
                const pct = areas.length ? Math.round((observed / areas.length) * 100) : 0;
                return { entityId, name: nameMap[entityId] || entityId, areaMap, pct };
              }).sort((a, b) => b.pct - a.pct);

              if (!rows.length) return <p style={{ opacity: 0.6 }}>No snapshot data found for this org.</p>;

              return (
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ borderCollapse: 'collapse', fontSize: '12px', width: '100%' }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: 'left', padding: '4px 8px 4px 0', color: 'rgba(128,128,128,0.6)', fontWeight: 'normal', whiteSpace: 'nowrap', minWidth: '140px' }}>Network</th>
                        <th style={{ textAlign: 'right', padding: '4px 12px 4px 4px', color: 'rgba(128,128,128,0.6)', fontWeight: 'normal', whiteSpace: 'nowrap' }}>Coverage</th>
                        {areas.map(a => (
                          <th key={a} style={{ padding: '4px 3px', color: 'rgba(128,128,128,0.6)', fontWeight: 'normal', textAlign: 'center', fontSize: '11px', whiteSpace: 'nowrap' }}>{a}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map(({ entityId, name, areaMap, pct }) => (
                        <tr key={entityId}>
                          <td style={{ padding: '4px 8px 4px 0', whiteSpace: 'nowrap' }}>{name}</td>
                          <td style={{ padding: '4px 12px 4px 4px', textAlign: 'right', fontWeight: 'bold', color: pctColor(pct) }}>{pct}%</td>
                          {areas.map(a => (
                            <td key={a} style={{ padding: '3px' }}>
                              <div style={{ background: cellColor(areaMap[a], now, STALE_MS), borderRadius: '3px', width: '20px', height: '14px', margin: '0 auto' }} />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ display: 'flex', gap: '14px', marginTop: '10px', fontSize: '11px', opacity: 0.5 }}>
                    <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#27ae60', borderRadius: '2px', verticalAlign: 'middle', marginRight: '4px' }} />observed</span>
                    <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: '#e67e22', borderRadius: '2px', verticalAlign: 'middle', marginRight: '4px' }} />stale (&gt;7d)</span>
                    <span><span style={{ display: 'inline-block', width: '10px', height: '10px', background: 'rgba(128,128,128,0.12)', borderRadius: '2px', verticalAlign: 'middle', marginRight: '4px' }} />never observed</span>
                  </div>
                </div>
              );
            }}
          </NrqlQuery>
        );
      }}
    </WithNetworkNames>
  );
}

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

// ── Main ────────────────────────────────────────────────────────────────────

export default function CompareView({ accountId, orgId }) {
  const [subTab, setSubTab] = useState('templates');

  const pillStyle = (key) => ({
    padding: '5px 14px',
    borderRadius: '20px',
    border: subTab === key ? '1px solid #0078bf' : '1px solid rgba(128,128,128,0.3)',
    background: subTab === key ? 'rgba(0,120,191,0.15)' : 'transparent',
    color: subTab === key ? '#0078bf' : 'inherit',
    cursor: 'pointer',
    fontSize: '12px',
  });

  if (!orgId) return <p style={{ opacity: 0.6 }}>Select an org to compare networks.</p>;

  return (
    <div>
      <div style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>
        <button style={pillStyle('templates')} onClick={() => setSubTab('templates')}>Golden Template Comparator</button>
        <button style={pillStyle('coverage')} onClick={() => setSubTab('coverage')}>Coverage</button>
      </div>

      {subTab === 'templates' && (
        <TemplatesTab accountId={accountId} orgId={orgId} />
      )}

      {subTab === 'coverage' && (
        <CoverageTab accountId={accountId} orgId={orgId} />
      )}
    </div>
  );
}
