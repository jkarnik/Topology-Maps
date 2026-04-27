import React from 'react';
import { NrqlQuery, Spinner, TreeView, TreeViewItem } from 'nr1';

export default function ConfigTree({ accountId, orgId, selectedEntityId, onEntitySelect }) {
  if (!accountId || !orgId) {
    return <p style={{ color: '#8e9aad' }}>Select an org to browse config.</p>;
  }
  return (
    <NrqlQuery
      accountIds={[accountId]}
      query={`SELECT latest(entity_name) AS name FROM MerakiConfigSnapshot
              WHERE org_id = '${orgId}'
              FACET entity_type, entity_id
              SINCE 30 days ago LIMIT MAX`}
    >
      {({ data, loading }) => {
        if (loading) return <Spinner />;
        const byType = {};
        (data || []).forEach((series) => {
          const [entityType, entityId] = series.metadata.groups.map((g) => g.value);
          const name = series.data?.[0]?.name || entityId;
          if (!byType[entityType]) byType[entityType] = [];
          byType[entityType].push({ id: entityId, name });
        });
        return (
          <TreeView>
            {Object.entries(byType).map(([type, entities]) => (
              <TreeViewItem key={type} label={type} value={type}>
                {entities.map((e) => (
                  <TreeViewItem
                    key={e.id} label={e.name || e.id} value={e.id}
                    selected={e.id === selectedEntityId}
                    onClick={() => onEntitySelect(e.id, type)}
                  />
                ))}
              </TreeViewItem>
            ))}
          </TreeView>
        );
      }}
    </NrqlQuery>
  );
}
