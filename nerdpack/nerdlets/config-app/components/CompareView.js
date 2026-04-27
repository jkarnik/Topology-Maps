import React, { useState } from 'react';
import { NrqlQuery, Spinner, Select, SelectItem } from 'nr1';

function NetworkSelector({ accountId, orgId, label, value, onChange }) {
  return (
    <NrqlQuery accountIds={[accountId]}
      query={`SELECT uniques(entity_id, 100) FROM MerakiConfigSnapshot
              WHERE org_id = '${orgId}' AND entity_type = 'network' SINCE 30 days ago`}>
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const ids = data?.[0]?.data?.[0]?.['uniques.entity_id'] || [];
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
  if (!orgId) return <p style={{ color: '#8e9aad' }}>Select an org to compare networks.</p>;
  return (
    <div>
      <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end', marginBottom: '16px' }}>
        <NetworkSelector accountId={accountId} orgId={orgId} label="Network A" value={netA} onChange={setNetA} />
        <NetworkSelector accountId={accountId} orgId={orgId} label="Network B" value={netB} onChange={setNetB} />
      </div>
      {netA && netB && netA !== netB ? (
        <SideBySideDiff accountId={accountId} netA={netA} netB={netB} />
      ) : (
        <p style={{ color: '#8e9aad' }}>Select two different networks to compare.</p>
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
            (dA || []).forEach((s) => { mapA[s.metadata.groups[0].value] = s.data?.[0]?.json; });
            (dB || []).forEach((s) => { mapB[s.metadata.groups[0].value] = s.data?.[0]?.json; });
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
                            <p style={{ color: '#8e9aad', fontSize: '12px' }}>{id}</p>
                            <pre style={{ background: '#0d1117', color: '#e0e0e0', padding: '8px', fontSize: '11px',
                                          borderRadius: '4px', overflow: 'auto', maxHeight: '200px' }}>
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
