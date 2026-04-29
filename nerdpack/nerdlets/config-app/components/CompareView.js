import React, { useState } from 'react';
import { NrqlQuery, Spinner, Select, SelectItem } from 'nr1';

function NetworkSelector({ accountId, orgId, label, value, onChange }) {
  return (
    <NrqlQuery accountIds={[accountId]}
      query={`SELECT count(*) FROM MerakiConfigSnapshot
              WHERE org_id = '${orgId}' AND entity_type = 'network'
              FACET entity_id SINCE 30 days ago LIMIT 100`}>
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const ids = (data || []).map(s => s.metadata?.groups?.find(g => g.type === 'facet')?.value).filter(Boolean);
        return (
          <Select label={label} value={value} onChange={(_, v) => onChange(v)}>
            <SelectItem value={null}>— Select network —</SelectItem>
            {ids.map((id) => <SelectItem key={id} value={id}>{id}</SelectItem>)}
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
          return { entityId, areaMap, observed, pct };
        }).sort((a, b) => b.pct - a.pct);

        if (!rows.length) return <p style={{ opacity: 0.6 }}>No snapshot data found for this org.</p>;

        function cellColor(ts) {
          if (ts == null) return 'rgba(128,128,128,0.12)';
          return (now - ts) > STALE_MS ? '#e67e22' : '#27ae60';
        }
        function pctColor(pct) {
          if (pct >= 80) return '#27ae60';
          if (pct >= 50) return '#e67e22';
          return '#e74c3c';
        }

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
                {rows.map(({ entityId, areaMap, observed, pct }) => (
                  <tr key={entityId}>
                    <td style={{ padding: '4px 8px 4px 0', whiteSpace: 'nowrap' }}>{entityId}</td>
                    <td style={{ padding: '4px 12px 4px 4px', textAlign: 'right', fontWeight: 'bold', color: pctColor(pct) }}>{pct}%</td>
                    {areas.map(a => (
                      <td key={a} style={{ padding: '3px' }}>
                        <div style={{ background: cellColor(areaMap[a]), borderRadius: '3px', width: '20px', height: '14px', margin: '0 auto' }} />
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

export default function CompareView({ accountId, orgId }) {
  const [netA, setNetA] = useState(null);
  const [netB, setNetB] = useState(null);
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
          <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', marginBottom: '16px' }}>
            <NetworkSelector accountId={accountId} orgId={orgId} label="Network A" value={netA} onChange={setNetA} />
            <NetworkSelector accountId={accountId} orgId={orgId} label="Network B" value={netB} onChange={setNetB} />
          </div>
          {netA && netB && netA !== netB
            ? <SideBySideDiff accountId={accountId} netA={netA} netB={netB} />
            : <p style={{ opacity: 0.6 }}>Select two different networks to compare.</p>
          }
        </div>
      )}

      {subTab === 'coverage' && (
        <CoverageTab accountId={accountId} orgId={orgId} />
      )}

      {subTab === 'templates' && (
        <p style={{ opacity: 0.6 }}>Templates coming soon…</p>
      )}
    </div>
  );
}

function SideBySideDiff({ accountId, netA, netB }) {
  const q = (id) => `SELECT latest(config_json) AS json FROM MerakiConfigSnapshot
                     WHERE entity_id = '${id}' FACET config_area SINCE 30 days ago LIMIT MAX`;
  return (
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
            return (
              <div>
                {diffAreas.map((area) => {
                  const fmt = (raw) => { try { return JSON.stringify(JSON.parse(raw), null, 2); } catch(_) { return raw || '(not observed)'; }};
                  return (
                    <div key={area} style={{ marginBottom: '16px' }}>
                      <h4 style={{ marginBottom: '4px' }}>{area}</h4>
                      <div style={{ display: 'flex', gap: '16px' }}>
                        {[{id: netA, json: mapA[area]}, {id: netB, json: mapB[area]}].map(({id, json}) => (
                          <div key={id} style={{ flex: 1 }}>
                            <p style={{ opacity: 0.6, fontSize: '12px' }}>{id}</p>
                            <pre style={{ background: 'rgba(128,128,128,0.08)', border: '1px solid rgba(128,128,128,0.15)',
                                          padding: '8px', fontSize: '11px', borderRadius: '4px', overflow: 'auto', maxHeight: '200px' }}>
                              {fmt(json)}
                            </pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          }}
        </NrqlQuery>
      )}
    </NrqlQuery>
  );
}
