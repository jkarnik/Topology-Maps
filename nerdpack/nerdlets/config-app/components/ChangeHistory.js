import React, { useState } from 'react';
import { NrqlQuery, Spinner, Table, TableHeader, TableHeaderCell, TableRow, TableRowCell } from 'nr1';
import DiffViewer from './DiffViewer';

export default function ChangeHistory({ accountId, orgId, entityId }) {
  const [expandedDiff, setExpandedDiff] = useState(null);
  if (!accountId || !orgId) return <p style={{ opacity: 0.6 }}>Select an org to view change history.</p>;

  const entityFilter = entityId ? `AND entity_id = '${entityId}'` : '';
  const query = `SELECT entity_name, entity_id, config_area, change_summary, detected_at, diff_json
                 FROM MerakiConfigChange WHERE org_id = '${orgId}' ${entityFilter}
                 SINCE 30 days ago ORDER BY detected_at DESC LIMIT 100`;

  return (
    <>
      <NrqlQuery accountIds={[accountId]} query={query}>
        {({ data, loading, error }) => {
          if (loading) return <Spinner />;
          if (error) return <span style={{ color: '#c0392b' }}>Failed to load change history.</span>;
          const rows = data?.[0]?.data || [];
          if (!rows.length) return <p style={{ opacity: 0.6 }}>No config changes found.</p>;
          return (
            <Table items={rows}>
              <TableHeader>
                <TableHeaderCell>Entity</TableHeaderCell>
                <TableHeaderCell>Config Area</TableHeaderCell>
                <TableHeaderCell>Summary</TableHeaderCell>
                <TableHeaderCell>Detected At</TableHeaderCell>
                <TableHeaderCell>Diff</TableHeaderCell>
              </TableHeader>
              {({ item }) => (
                <TableRow>
                  <TableRowCell>{item.entity_name || item.entity_id}</TableRowCell>
                  <TableRowCell>{item.config_area}</TableRowCell>
                  <TableRowCell>{item.change_summary}</TableRowCell>
                  <TableRowCell>{item.detected_at}</TableRowCell>
                  <TableRowCell>
                    <span style={{ color: '#0078bf', cursor: 'pointer', textDecoration: 'underline' }}
                          onClick={() => setExpandedDiff(item.diff_json)}>
                      View diff
                    </span>
                  </TableRowCell>
                </TableRow>
              )}
            </Table>
          );
        }}
      </NrqlQuery>
      {expandedDiff && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.7)',
                      zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
             onClick={() => setExpandedDiff(null)}>
          <div style={{ background: 'var(--color-background, #1e2132)', padding: '24px', borderRadius: '8px',
                        minWidth: '500px', maxWidth: '80vw', maxHeight: '80vh', overflow: 'auto',
                        border: '1px solid rgba(128,128,128,0.2)' }}
               onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
              <strong>Config Diff</strong>
              <span style={{ cursor: 'pointer', opacity: 0.6 }} onClick={() => setExpandedDiff(null)}>✕</span>
            </div>
            <DiffViewer diffJson={expandedDiff} />
          </div>
        </div>
      )}
    </>
  );
}
