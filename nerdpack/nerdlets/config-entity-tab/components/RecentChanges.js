import React from 'react';
import { NrqlQuery, Spinner, Collapsible, CollapsibleItem } from 'nr1';
import DiffViewer from '../../config-app/components/DiffViewer';

export default function RecentChanges({ accountId, entityId }) {
  if (!entityId) return null;
  return (
    <NrqlQuery accountIds={[accountId]}
      query={`SELECT config_area, change_summary, detected_at, diff_json
              FROM MerakiConfigChange WHERE entity_id = '${entityId}'
              SINCE 30 days ago ORDER BY detected_at DESC LIMIT 10`}>
      {({ data, loading, error }) => {
        if (loading) return <Spinner />;
        if (error) return <span style={{ color: '#e74c3c' }}>Failed to load changes.</span>;
        const rows = data?.[0]?.data || [];
        if (!rows.length) return <p style={{ color: '#8e9aad' }}>No recent config changes for this entity.</p>;
        return (
          <Collapsible>
            {rows.map((row, i) => (
              <CollapsibleItem key={i}
                title={`${row.config_area} — ${row.change_summary} (${row.detected_at})`}>
                <DiffViewer diffJson={row.diff_json} />
              </CollapsibleItem>
            ))}
          </Collapsible>
        );
      }}
    </NrqlQuery>
  );
}
