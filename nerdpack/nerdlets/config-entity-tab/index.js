import React from 'react';
import { NerdletStateContext, EntityByGuidQuery, Spinner } from 'nr1';
import ConfigSummary from './components/ConfigSummary';
import RecentChanges from './components/RecentChanges';

function resolveEntityId(entity) {
  const tags = entity?.tags || [];
  const find = (key) => tags.find((t) => t.key === key)?.values?.[0];
  return find('tags.serial') || find('tags.network_id') || find('tags.org_id') || null;
}

function resolveOrgId(entity) {
  const tags = entity?.tags || [];
  return tags.find((t) => t.key === 'tags.org_id')?.values?.[0] || null;
}

export default function ConfigEntityTab() {
  return (
    <NerdletStateContext.Consumer>
      {(nerdletState) => {
        const entityGuid = nerdletState.entityGuid;
        if (!entityGuid) return <p>No entity GUID found.</p>;
        return (
          <EntityByGuidQuery entityGuid={entityGuid}>
            {({ data, loading, error }) => {
              if (loading) return <Spinner />;
              if (error || !data?.entities?.length) return <p>Entity not found.</p>;
              const entity = data.entities[0];
              const accountId = entity.accountId;
              const entityId = resolveEntityId(entity);
              const orgId = resolveOrgId(entity);
              if (!entityId) return <p style={{ color: '#e74c3c' }}>Could not determine entity ID from tags.</p>;
              return (
                <div style={{ padding: '16px' }}>
                  <ConfigSummary accountId={accountId} entityId={entityId} orgId={orgId} />
                  <div style={{ marginTop: '24px' }}>
                    <h3>Recent Changes</h3>
                    <RecentChanges accountId={accountId} entityId={entityId} orgId={orgId} />
                  </div>
                </div>
              );
            }}
          </EntityByGuidQuery>
        );
      }}
    </NerdletStateContext.Consumer>
  );
}
