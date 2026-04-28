import React, { useState } from 'react';
import { NrqlQuery, Spinner } from 'nr1';

function TreeNode({ label, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div>
      <div
        onClick={() => setOpen(o => !o)}
        style={{ cursor: 'pointer', padding: '4px 0', fontWeight: 'bold', color: '#8e9aad', userSelect: 'none', fontSize: '13px' }}
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
        color: selected ? '#0095f7' : '#e0e0e0',
        background: selected ? 'rgba(0,149,247,0.1)' : undefined,
        borderRadius: '3px',
      }}
    >
      {entity.name || entity.id}
    </div>
  );
}

export default function ConfigTree({ accountId, orgId, selectedEntityId, onEntitySelect }) {
  if (!accountId || !orgId) {
    return <p style={{ color: '#8e9aad' }}>Select an org to browse config.</p>;
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
        if (error) return <p style={{ color: 'red' }}>Failed to load: {error.message}</p>;

        // Build: networks{id: {name, devices:[], ssids:[]}}
        const networks = {};
        const orgs = [];

        (data || []).forEach((series) => {
          const facets = (series.metadata.groups || []).filter(g => g.type === 'facet');
          const entityType = facets[0]?.value;
          const entityId   = facets[1]?.value;
          const networkId  = series.data?.[0]?.['latest.network_id'] || '';
          if (!entityType || !entityId) return;
          const name = series.data?.[0]?.['latest.entity_name'] || series.data?.[0]?.name || entityId;

          if (entityType === 'network') {
            if (!networks[entityId]) networks[entityId] = { id: entityId, name, devices: [], ssids: [] };
            else { networks[entityId].name = name; networks[entityId].id = entityId; }
          } else if (entityType === 'device') {
            if (networkId && !networks[networkId]) networks[networkId] = { id: networkId, name: networkId, devices: [], ssids: [] };
            const bucket = networkId ? networks[networkId] : (networks['__unknown'] = networks['__unknown'] || { id: '', name: 'Unknown Network', devices: [], ssids: [] });
            bucket.devices.push({ id: entityId, name });
          } else if (entityType === 'ssid') {
            const netId = entityId.split(':')[0];
            if (!networks[netId]) networks[netId] = { id: netId, name: netId, devices: [], ssids: [] };
            networks[netId].ssids.push({ id: entityId, name });
          } else if (entityType === 'org') {
            orgs.push({ id: entityId, name });
          }
        });

        return (
          <div style={{ fontFamily: 'monospace' }}>
            {Object.values(networks).map(net => (
              <TreeNode key={net.id} label={`${net.name || net.id}`} defaultOpen={Object.keys(networks).length === 1}>
                {net.devices.length > 0 && (
                  <TreeNode label={`Devices (${net.devices.length})`} defaultOpen>
                    {net.devices.map(e => (
                      <EntityItem key={e.id} entity={e} entityType="device" selectedEntityId={selectedEntityId} onEntitySelect={onEntitySelect} />
                    ))}
                  </TreeNode>
                )}
                {net.ssids.length > 0 && (
                  <TreeNode label={`SSIDs (${net.ssids.length})`} defaultOpen>
                    {net.ssids.map(e => (
                      <EntityItem key={e.id} entity={e} entityType="ssid" selectedEntityId={selectedEntityId} onEntitySelect={onEntitySelect} />
                    ))}
                  </TreeNode>
                )}
              </TreeNode>
            ))}
          </div>
        );
      }}
    </NrqlQuery>
  );
}
