import React, { useState } from 'react';
import { NrqlQuery, Spinner } from 'nr1';

function TreeNode({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ cursor: 'pointer', padding: '4px 0', fontWeight: 'bold', opacity: 0.7, userSelect: 'none', fontSize: '13px' }}
      >
        {open ? '▾' : '▸'} {label}
      </div>
      {open && <div style={{ paddingLeft: '14px' }}>{children}</div>}
    </div>
  );
}

function EntityItem({ entity, selectedEntityId, onEntitySelect, entityType }) {
  const selected = entity.id === selectedEntityId;
  return (
    <div
      onClick={() => onEntitySelect(entity.id, entityType)}
      style={{
        padding: '3px 0 3px 2px', cursor: 'pointer', fontSize: '13px',
        color: selected ? '#0078bf' : 'inherit',
        background: selected ? 'rgba(0,120,191,0.12)' : undefined,
        borderRadius: '3px',
      }}
    >
      {entity.name || entity.id}
    </div>
  );
}

export default function ConfigTree({ accountId, orgId, selectedEntityId, onEntitySelect }) {
  if (!accountId || !orgId) {
    return <p style={{ opacity: 0.6 }}>Select an org to browse config.</p>;
  }
  return (
    <NrqlQuery
      accountIds={[accountId]}
      query={`SELECT latest(entity_name), latest(network_id) FROM MerakiConfigSnapshot
              WHERE org_id = '${orgId}'
              FACET entity_type, entity_id
              SINCE 30 days ago LIMIT MAX`}
    >
      {({ data, loading, error }) => {
        if (loading) return <Spinner />;
        if (error) return <p style={{ color: '#c0392b' }}>Failed to load: {error.message}</p>;

        // CHART format with 2 SELECT items produces 2 series per facet combination.
        // Merge by entity_type:entity_id so each entity ends up with one record.
        const entityMap = {};
        (data || []).forEach(s => {
          const facetGroups = (s.metadata?.groups || []).filter(g => g.type === 'facet');
          const entityType = facetGroups[0]?.value;
          const entityId = facetGroups[1]?.value;
          if (!entityType || !entityId) return;
          const key = `${entityType}:${entityId}`;
          if (!entityMap[key]) entityMap[key] = { entityType, entityId };
          Object.assign(entityMap[key], s.data?.[0] || {});
        });

        const networks = {};
        let orgEntity = null;

        Object.values(entityMap).forEach(entry => {
          const { entityType, entityId } = entry;
          const name = entry['entity_name'] || '';
          const networkId = entry['network_id'] || '';

          if (entityType === 'org') {
            orgEntity = { id: entityId, name: name || entityId };
          } else if (entityType === 'network') {
            if (!networks[entityId]) networks[entityId] = { id: entityId, name: name || entityId, devices: [], ssids: [] };
            else { networks[entityId].name = name || networks[entityId].name; }
          } else if (entityType === 'device') {
            const netId = networkId || '__unknown';
            if (!networks[netId]) networks[netId] = { id: netId, name: netId === '__unknown' ? 'Unknown Network' : netId, devices: [], ssids: [] };
            networks[netId].devices.push({ id: entityId, name: name || entityId });
          } else if (entityType === 'ssid') {
            const netId = entityId.split(':')[0];
            const ssidNum = entityId.split(':')[1];
            if (!networks[netId]) networks[netId] = { id: netId, name: netId, devices: [], ssids: [] };
            networks[netId].ssids.push({ id: entityId, name: name || `SSID ${ssidNum}` });
          }
        });

        const networkList = Object.values(networks).filter(n => n.id !== '__unknown');
        const unknown = networks['__unknown'];

        return (
          <div style={{ fontFamily: 'monospace' }}>
            {orgEntity && (
              <EntityItem
                entity={{ id: orgEntity.id, name: `Org: ${orgEntity.name}` }}
                entityType="org"
                selectedEntityId={selectedEntityId}
                onEntitySelect={onEntitySelect}
              />
            )}
            {networkList.map(net => (
              <TreeNode key={net.id} label={net.name || net.id} defaultOpen={networkList.length === 1}>
                {net.devices.length > 0 && (
                  <TreeNode label={`Devices (${net.devices.length})`} defaultOpen={net.devices.length <= 10}>
                    {net.devices.map(e => (
                      <EntityItem key={e.id} entity={e} entityType="device" selectedEntityId={selectedEntityId} onEntitySelect={onEntitySelect} />
                    ))}
                  </TreeNode>
                )}
                {net.ssids.length > 0 && (
                  <TreeNode label={`SSIDs (${net.ssids.length})`}>
                    {net.ssids.map(e => (
                      <EntityItem key={e.id} entity={e} entityType="ssid" selectedEntityId={selectedEntityId} onEntitySelect={onEntitySelect} />
                    ))}
                  </TreeNode>
                )}
              </TreeNode>
            ))}
            {unknown && (
              <TreeNode label={`Unknown Network (${unknown.devices.length})`}>
                {unknown.devices.map(e => (
                  <EntityItem key={e.id} entity={e} entityType="device" selectedEntityId={selectedEntityId} onEntitySelect={onEntitySelect} />
                ))}
              </TreeNode>
            )}
          </div>
        );
      }}
    </NrqlQuery>
  );
}
