import React, { useState } from 'react';
import { NrqlQuery, Spinner, Table, TableHeader, TableHeaderCell, TableRow, TableRowCell } from 'nr1';

export default function ConfigAreaViewer({ accountId, entityId, entityType }) {
  const [selectedArea, setSelectedArea] = useState(null);
  if (!entityId) return <p style={{ color: '#8e9aad' }}>Select an entity to view its config.</p>;

  return (
    <div>
      <h3 style={{ marginBottom: '8px' }}>{entityType}: {entityId}</h3>
      <NrqlQuery
        accountIds={[accountId]}
        query={`SELECT latest(config_hash) AS hash, latest(observed_at) AS ts
                FROM MerakiConfigSnapshot WHERE entity_id = '${entityId}'
                FACET config_area SINCE 30 days ago LIMIT MAX`}
      >
        {({ data, loading, error }) => {
          if (loading) return <Spinner />;
          if (error || !data?.length) return <span>No config data found.</span>;
          const areas = (data || []).map((s) => ({
            area: s.metadata.groups[0].value,
            hash: s.data?.[0]?.hash || '',
            ts: s.data?.[0]?.ts || '',
          }));
          return (
            <>
              <Table items={areas}>
                <TableHeader>
                  <TableHeaderCell value={({ item }) => item.area}>Config Area</TableHeaderCell>
                  <TableHeaderCell value={({ item }) => item.hash.slice(0, 12)}>Hash</TableHeaderCell>
                  <TableHeaderCell value={({ item }) => item.ts}>Last Observed</TableHeaderCell>
                </TableHeader>
                {({ item }) => (
                  <TableRow
                    onClick={() => setSelectedArea(item.area)}
                    style={{ cursor: 'pointer', background: item.area === selectedArea ? '#e8f4fd' : undefined }}
                  >
                    <TableRowCell>{item.area}</TableRowCell>
                    <TableRowCell><code>{item.hash.slice(0, 12)}</code></TableRowCell>
                    <TableRowCell>{item.ts}</TableRowCell>
                  </TableRow>
                )}
              </Table>
              {selectedArea && (
                <NrqlQuery
                  accountIds={[accountId]}
                  query={`SELECT latest(config_json) FROM MerakiConfigSnapshot
                          WHERE entity_id = '${entityId}' AND config_area = '${selectedArea}'
                          SINCE 30 days ago`}
                >
                  {({ data: jData, loading: jl }) => {
                    if (jl) return <Spinner />;
                    const raw = jData?.[0]?.data?.[0]?.['latest.config_json'];
                    let pretty = raw || '{}';
                    try { pretty = JSON.stringify(JSON.parse(raw), null, 2); } catch (_) {}
                    return (
                      <pre style={{ background: '#0d1117', color: '#e0e0e0', padding: '12px',
                                    borderRadius: '4px', overflow: 'auto', maxHeight: '400px',
                                    marginTop: '12px', fontSize: '12px' }}>
                        {pretty}
                      </pre>
                    );
                  }}
                </NrqlQuery>
              )}
            </>
          );
        }}
      </NrqlQuery>
    </div>
  );
}
