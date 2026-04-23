import React, { useState, useEffect } from 'react';
import { CollectionStatusBar } from './CollectionStatusBar';
import { ConfigTree } from './ConfigTree';
import { ConfigEntityView } from './ConfigEntityView';
import { BaselineProgressOverlay } from './BaselineProgressOverlay';
import { useConfigOrgs } from '../../hooks/useConfigOrgs';
import { useConfigTree } from '../../hooks/useConfigTree';
import { useConfigCollection } from '../../hooks/useConfigCollection';
import { getStatus, startBaseline, startSweep } from '../../api/config';
import type { ConfigStatus, EntityType } from '../../types/config';

export const ConfigBrowser: React.FC = () => {
  const { orgs } = useConfigOrgs();
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [selected, setSelected] = useState<{ entityType: EntityType; entityId: string } | null>(null);
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const { tree, loading: treeLoading, reload: reloadTree } = useConfigTree(selectedOrgId);
  const { lastEvent } = useConfigCollection(selectedOrgId);

  useEffect(() => {
    if (!selectedOrgId && orgs.length > 0) setSelectedOrgId(orgs[0].org_id);
  }, [orgs, selectedOrgId]);

  useEffect(() => {
    if (!selectedOrgId) return;
    getStatus(selectedOrgId).then(setStatus);
  }, [selectedOrgId, lastEvent]);

  useEffect(() => {
    if (lastEvent?.type === 'observation.updated') reloadTree();
    if (lastEvent?.type === 'sweep.completed') reloadTree();
  }, [lastEvent, reloadTree]);

  const handleBaseline = async () => {
    if (!selectedOrgId) return;
    await startBaseline(selectedOrgId);
    getStatus(selectedOrgId).then(setStatus);
  };

  const handleSweep = async () => {
    if (!selectedOrgId) return;
    await startSweep(selectedOrgId);
    getStatus(selectedOrgId).then(setStatus);
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--bg-primary)',
        color: 'var(--text-primary)',
      }}
    >
      <CollectionStatusBar
        orgs={orgs}
        selectedOrgId={selectedOrgId}
        status={status}
        onOrgChange={setSelectedOrgId}
        onStartBaseline={handleBaseline}
        onStartSweep={handleSweep}
      />
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div
          style={{
            width: '320px',
            borderRight: '1px solid var(--border-subtle)',
            overflowY: 'auto',
            background: 'var(--bg-primary)',
          }}
        >
          <ConfigTree
            tree={tree}
            loading={treeLoading}
            onSelect={(t, id) => setSelected({ entityType: t, entityId: id })}
            selected={selected}
          />
        </div>
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '18px 22px',
            background: 'var(--bg-primary)',
          }}
        >
          {selected && selectedOrgId ? (
            <ConfigEntityView
              orgId={selectedOrgId}
              entityType={selected.entityType}
              entityId={selected.entityId}
            />
          ) : (
            <div
              style={{
                fontSize: '12px',
                color: 'var(--text-muted)',
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              Select an entity from the tree.
            </div>
          )}
        </div>
      </div>
      {lastEvent?.type === 'sweep.progress' && (
        <BaselineProgressOverlay
          progress={lastEvent}
          kind={status?.active_sweep?.kind ?? null}
          onClose={() => { /* dismiss handled by parent if needed */ }}
        />
      )}
    </div>
  );
};
