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

export default function CompareView({ accountId, orgId }) {
  const [netA, setNetA] = useState(null);
  const [netB, setNetB] = useState(null);
  if (!orgId) return <p style={{ opacity: 0.6 }}>Select an org to compare networks.</p>;
  return (
    <div>
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', marginBottom: '16px' }}>
        <NetworkSelector accountId={accountId} orgId={orgId} label="Network A" value={netA} onChange={setNetA} />
        <NetworkSelector accountId={accountId} orgId={orgId} label="Network B" value={netB} onChange={setNetB} />
      </div>
      {netA && netB && netA !== netB ? (
        <SideBySideDiff accountId={accountId} netA={netA} netB={netB} />
      ) : (
        <p style={{ opacity: 0.6 }}>Select two different networks to compare.</p>
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
