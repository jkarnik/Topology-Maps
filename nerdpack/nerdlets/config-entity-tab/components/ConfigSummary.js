import React from 'react';
import { NrqlQuery, Spinner } from 'nr1';

const STATUS = {
  changed: { color: '#e67e22', dot: '🟠' },
  stable:  { color: '#27ae60', dot: '🟢' },
};

export default function ConfigSummary({ accountId, entityId, orgId }) {
  if (!entityId) return null;

  return (
    <div>
      <h3>Config Status</h3>
      <NrqlQuery accountIds={[accountId]}
        query={`SELECT uniques(config_area, 100) FROM MerakiConfigChange
                WHERE entity_id = '${entityId}' SINCE 24 hours ago`}>
        {({ data: cd }) => {
          const changedAreas = new Set(cd?.[0]?.data?.[0]?.['uniques.config_area'] || []);
          return (
            <NrqlQuery accountIds={[accountId]}
              query={`SELECT latest(observed_at) AS ts FROM MerakiConfigSnapshot
                      WHERE entity_id = '${entityId}'
                      FACET config_area SINCE 30 days ago LIMIT MAX`}>
              {({ data, loading }) => {
                if (loading) return <Spinner />;
                if (!data?.length) return <p style={{ color: '#8e9aad' }}>No config data found for this entity.</p>;
                const lastTs = data.reduce((max, s) => {
                  const ts = s.data?.[0]?.ts || '';
                  return ts > max ? ts : max;
                }, '');
                return (
                  <div>
                    <p style={{ color: '#8e9aad', fontSize: '12px', marginBottom: '8px' }}>Last ingest: {lastTs || 'unknown'}</p>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '8px' }}>
                      {data.map((series) => {
                        const area = series.metadata.groups[0].value;
                        const s = changedAreas.has(area) ? STATUS.changed : STATUS.stable;
                        return (
                          <div key={area} style={{ padding: '8px 12px', borderRadius: '4px',
                                                   border: `1px solid ${s.color}`, background: '#1a1a2e' }}>
                            <span style={{ marginRight: '6px' }}>{s.dot}</span>
                            <span style={{ color: '#e0e0e0', fontSize: '13px' }}>{area}</span>
                          </div>
                        );
                      })}
                    </div>
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
