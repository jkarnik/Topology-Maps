import React, { useState } from 'react';
import { NrqlQuery, Spinner, Table, TableHeader, TableHeaderCell, TableRow, TableRowCell, Modal, ModalHeader, ModalBody } from 'nr1';
import DiffViewer from './DiffViewer';

export default function ChangeHistory({ accountId, orgId, entityId }) {
  const [expandedDiff, setExpandedDiff] = useState(null);
  if (!accountId || !orgId) return <p style={{ color: '#8e9aad' }}>Select an org to view change history.</p>;

  const entityFilter = entityId ? `AND entity_id = '${entityId}'` : '';
  const query = `SELECT entity_name, entity_id, config_area, change_summary, detected_at, diff_json
                 FROM MerakiConfigChange WHERE org_id = '${orgId}' ${entityFilter}
                 SINCE 30 days ago ORDER BY detected_at DESC LIMIT 100`;

  return (
    <>
      <NrqlQuery accountIds={[accountId]} query={query}>
        {({ data, loading, error }) => {
          if (loading) return <Spinner />;
          if (error) return <span style={{ color: '#e74c3c' }}>Failed to load change history.</span>;
          const rows = data?.[0]?.data || [];
          if (!rows.length) return <p style={{ color: '#8e9aad' }}>No config changes found.</p>;
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
        <Modal onClose={() => setExpandedDiff(null)}>
          <ModalHeader title="Config Diff" />
          <ModalBody><DiffViewer diffJson={expandedDiff} /></ModalBody>
        </Modal>
      )}
    </>
  );
}
