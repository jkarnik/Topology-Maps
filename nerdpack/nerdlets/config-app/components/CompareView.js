import React, { useState } from 'react';
import { NrqlQuery, Spinner, Select, SelectItem } from 'nr1';

function cellColor(ts, now, STALE_MS) {
  if (ts == null) return 'rgba(128,128,128,0.12)';
  return (now - ts) > STALE_MS ? '#e67e22' : '#27ae60';
}

function pctColor(pct) {
  if (pct >= 80) return '#27ae60';
  if (pct >= 50) return '#e67e22';
  return '#e74c3c';
}

function scoreColor(pct) {
  if (pct >= 80) return { bg: 'rgba(39,174,96,0.06)', border: 'rgba(39,174,96,0.2)', text: '#27ae60' };
  if (pct >= 50) return { bg: 'rgba(230,126,34,0.06)', border: 'rgba(230,126,34,0.2)', text: '#e67e22' };
  return { bg: 'rgba(231,76,60,0.06)', border: 'rgba(231,76,60,0.2)', text: '#e74c3c' };
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

function CoverageTab({ accountId, orgId }) {
  const query = `SELECT latest(timestamp) FROM MerakiConfigSnapshot
                 WHERE org_id = '${orgId}'
                 FACET entity_id, config_area
                 SINCE 30 days ago LIMIT MAX`;
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
          if (!entityId || !area) return;
          const ts = s.data?.[0]?.['latest.timestamp'] ?? s.data?.[0]?.['timestamp'] ?? null;
          if (!matrix[entityId]) matrix[entityId] = {};
          matrix[entityId][area] = ts ? Number(ts) : null;
          allAreas.add(area);
        });

        const areas = [...allAreas].sort();
        const rows = Object.entries(matrix).map(([entityId, areaMap]) => {
          const observed = areas.filter(a => areaMap[a] != null).length;
          const pct = areas.length ? Math.round((observed / areas.length) * 100) : 0;
          return { entityId, areaMap, pct };
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
                {rows.map(({ entityId, areaMap, pct }) => (
                  <tr key={entityId}>
                    <td style={{ padding: '4px 8px 4px 0', whiteSpace: 'nowrap' }}>{entityId}</td>
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
}

function TemplatesTab({ accountId, orgId }) {
  const [selectedNet, setSelectedNet] = useState(null);
  const [templateNet, setTemplateNet] = useState(null);

  const query = templateNet
    ? `SELECT latest(config_json) FROM MerakiConfigSnapshot
       WHERE org_id = '${orgId}'
       FACET entity_id, config_area
       SINCE 30 days ago LIMIT MAX`
    : null;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px', padding: '12px', background: 'rgba(0,120,191,0.07)', border: '1px solid rgba(0,120,191,0.2)', borderRadius: '6px' }}>
        <span style={{ fontSize: '12px', opacity: 0.6, whiteSpace: 'nowrap' }}>Golden template:</span>
        <div style={{ flex: 1 }}>
          <NetworkSelector accountId={accountId} orgId={orgId} label="" value={selectedNet} onChange={setSelectedNet} />
        </div>
        <button
          onClick={() => setTemplateNet(selectedNet)}
          disabled={!selectedNet}
          style={{ padding: '6px 14px', background: selectedNet ? 'rgba(0,120,191,0.2)' : 'rgba(128,128,128,0.1)', border: `1px solid ${selectedNet ? '#0078bf' : 'rgba(128,128,128,0.3)'}`, borderRadius: '4px', color: selectedNet ? '#0078bf' : 'inherit', fontSize: '12px', cursor: selectedNet ? 'pointer' : 'not-allowed', whiteSpace: 'nowrap' }}>
          Set as Template
        </button>
      </div>

      {!templateNet && (
        <p style={{ opacity: 0.6 }}>Select a network above and click "Set as Template" to score all other networks against it.</p>
      )}

      {templateNet && (
        <NrqlQuery accountIds={[accountId]} query={query}>
          {({ data, loading, error }) => {
            if (loading) return <Spinner />;
            if (error) return <p style={{ color: '#c0392b' }}>Failed to load snapshot data.</p>;

            // Build map: { entityId -> { configArea -> config_json } }
            const snapshots = {};
            (data || []).forEach(s => {
              const fg = (s.metadata?.groups || []).filter(g => g.type === 'facet');
              const entityId = fg[0]?.value;
              const area = fg[1]?.value;
              if (!entityId || !area) return;
              const json = s.data?.[0]?.['latest.config_json'] ?? s.data?.[0]?.['config_json'] ?? s.data?.[0]?.json ?? null;
              if (!snapshots[entityId]) snapshots[entityId] = {};
              snapshots[entityId][area] = json;
            });

            const templateAreas = snapshots[templateNet] || {};
            const templateAreaKeys = Object.keys(templateAreas);

            if (!templateAreaKeys.length) return <p style={{ opacity: 0.6 }}>No snapshot data found for the selected template network.</p>;

            const scored = Object.entries(snapshots)
              .filter(([id]) => id !== templateNet)
              .map(([entityId, areaMap]) => {
                const matched = templateAreaKeys.filter(a => areaMap[a] != null && areaMap[a] === templateAreas[a]);
                const pct = Math.round((matched.length / templateAreaKeys.length) * 100);
                return { entityId, areaMap, matched: new Set(matched), pct };
              })
              .sort((a, b) => b.pct - a.pct);

            if (!scored.length) return <p style={{ opacity: 0.6 }}>No other networks to score against this template.</p>;

            return (
              <div>
                <div style={{ marginBottom: '14px', fontSize: '12px' }}>
                  <span style={{ opacity: 0.5 }}>Scoring against: </span>
                  <span style={{ color: '#0078bf', fontWeight: 'bold' }}>{templateNet}</span>
                  <span style={{ opacity: 0.5 }}> · {templateAreaKeys.length} config areas</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {scored.map(({ entityId, matched, pct }) => {
                    const c = scoreColor(pct);
                    return (
                      <div key={entityId} style={{ background: c.bg, border: `1px solid ${c.border}`, borderRadius: '6px', padding: '10px 14px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
                          <div style={{ flex: 1, fontSize: '13px' }}>{entityId}</div>
                          <div style={{ fontSize: '20px', fontWeight: 'bold', color: c.text }}>{pct}%</div>
                          <div style={{ fontSize: '11px', opacity: 0.5 }}>{matched.size} / {templateAreaKeys.length} areas</div>
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                          {templateAreaKeys.map(a => (
                            <span key={a} style={{
                              fontSize: '10px', padding: '2px 7px', borderRadius: '10px',
                              background: matched.has(a) ? 'rgba(39,174,96,0.15)' : 'rgba(231,76,60,0.15)',
                              color: matched.has(a) ? '#27ae60' : '#e74c3c',
                            }}>
                              {a} {matched.has(a) ? '✓' : '✗'}
                            </span>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          }}
        </NrqlQuery>
      )}
    </div>
  );
}

export default function CompareView({ accountId, orgId }) {
  const [netA, setNetA] = useState(null);
  const [netAName, setNetAName] = useState(null);
  const [netB, setNetB] = useState(null);
  const [netBName, setNetBName] = useState(null);
  const [subTab, setSubTab] = useState('networks');

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
        <button style={pillStyle('networks')} onClick={() => setSubTab('networks')}>Networks</button>
        <button style={pillStyle('coverage')} onClick={() => setSubTab('coverage')}>Coverage</button>
        <button style={pillStyle('templates')} onClick={() => setSubTab('templates')}>Templates</button>
      </div>

      {subTab === 'networks' && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px', marginBottom: '16px' }}>
            <NetworkSelector accountId={accountId} orgId={orgId} label="Network A" value={netA} onChange={(id, name) => { setNetA(id); setNetAName(name); }} />
            <NetworkSelector accountId={accountId} orgId={orgId} label="Network B" value={netB} onChange={(id, name) => { setNetB(id); setNetBName(name); }} />
          </div>
          {netA && netB && netA !== netB
            ? <CompareDiffView accountId={accountId} netA={netA} netB={netB} nameA={netAName} nameB={netBName} />
            : <p style={{ opacity: 0.6 }}>Select two different networks to compare.</p>
          }
        </div>
      )}

      {subTab === 'coverage' && (
        <CoverageTab accountId={accountId} orgId={orgId} />
      )}

      {subTab === 'templates' && (
        <TemplatesTab accountId={accountId} orgId={orgId} />
      )}
    </div>
  );
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
