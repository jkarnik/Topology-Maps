import React, { useState } from 'react';
import { NrqlQuery, Spinner } from 'nr1';

export default function ConfigAreaViewer({ accountId, entityId, entityType }) {
  const [selectedArea, setSelectedArea] = useState(null);

  if (!entityId) return <p style={{ opacity: 0.6 }}>Select an entity to view its config.</p>;
  if (!accountId) return <p style={{ opacity: 0.6 }}>No account.</p>;

  return (
    <div>
      <h3 style={{ marginBottom: '12px', fontSize: '14px' }}>
        {entityType}: {entityId}
      </h3>
      <NrqlQuery
        accountIds={[accountId]}
        query={`SELECT latest(config_hash), latest(observed_at) FROM MerakiConfigSnapshot
                WHERE entity_id = '${entityId}'
                FACET config_area SINCE 30 days ago LIMIT MAX`}
      >
        {({ data, loading, error }) => {
          if (loading) return <Spinner />;
          if (error) return <p style={{ color: '#c0392b' }}>Query failed: {String(error.message || error)}</p>;
          if (!data || !data.length) return <p style={{ opacity: 0.6 }}>No config data found.</p>;

          const seen = new Set();
          const areas = (data || []).reduce((acc, s) => {
            const area = (s.metadata?.groups || []).find(g => g.type === 'facet')?.value;
            if (!area || seen.has(area)) return acc;
            seen.add(area);
            const hash = s.data?.[0]?.['config_hash'] || s.data?.[0]?.['latest.config_hash'] || '';
            const ts   = s.data?.[0]?.['observed_at'] || s.data?.[0]?.['latest.observed_at'] || '';
            acc.push({ area, hash, ts });
            return acc;
          }, []);

          if (!areas.length) return <p style={{ opacity: 0.6 }}>No config areas found.</p>;

          return (
            <>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(128,128,128,0.2)', textAlign: 'left', opacity: 0.6 }}>
                    <th style={{ padding: '6px 8px', fontWeight: 'normal' }}>Config Area</th>
                    <th style={{ padding: '6px 8px', fontWeight: 'normal' }}>Hash</th>
                    <th style={{ padding: '6px 8px', fontWeight: 'normal' }}>Last Observed</th>
                  </tr>
                </thead>
                <tbody>
                  {areas.map(({ area, hash, ts }) => (
                    <tr
                      key={area}
                      onClick={() => setSelectedArea(selectedArea === area ? null : area)}
                      style={{
                        borderBottom: '1px solid rgba(128,128,128,0.1)', cursor: 'pointer',
                        background: area === selectedArea ? 'rgba(0,120,191,0.12)' : undefined,
                      }}
                    >
                      <td style={{ padding: '6px 8px', color: area === selectedArea ? '#0078bf' : 'inherit' }}>{area}</td>
                      <td style={{ padding: '6px 8px', fontFamily: 'monospace', opacity: 0.6 }}>{hash.slice(0, 12)}</td>
                      <td style={{ padding: '6px 8px', opacity: 0.6 }}>{ts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {selectedArea && (
                <ConfigJson accountId={accountId} entityId={entityId} configArea={selectedArea} />
              )}
            </>
          );
        }}
      </NrqlQuery>
    </div>
  );
}

function ConfigJson({ accountId, entityId, configArea }) {
  return (
    <NrqlQuery
      accountIds={[accountId]}
      query={`SELECT latest(config_json) FROM MerakiConfigSnapshot
              WHERE entity_id = '${entityId}' AND config_area = '${configArea}'
              SINCE 30 days ago`}
    >
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const raw = data?.[0]?.data?.[0]?.['config_json'] || data?.[0]?.data?.[0]?.['latest.config_json'] || '{}';
        let pretty = raw;
        try { pretty = JSON.stringify(JSON.parse(raw), null, 2); } catch (_) {}
        return (
          <pre style={{
            background: 'rgba(128,128,128,0.08)', padding: '12px',
            borderRadius: '4px', overflow: 'auto', maxHeight: '400px',
            marginTop: '12px', fontSize: '12px', border: '1px solid rgba(128,128,128,0.15)',
          }}>
            {pretty}
          </pre>
        );
      }}
    </NrqlQuery>
  );
}
