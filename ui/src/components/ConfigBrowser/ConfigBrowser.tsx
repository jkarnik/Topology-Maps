import React, { useState, useEffect } from 'react';
import { CollectionStatusBar } from './CollectionStatusBar';
import { ConfigTree } from './ConfigTree';
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
    <div className="flex flex-col h-full">
      <CollectionStatusBar
        orgs={orgs}
        selectedOrgId={selectedOrgId}
        status={status}
        onOrgChange={setSelectedOrgId}
        onStartBaseline={handleBaseline}
        onStartSweep={handleSweep}
      />
      <div className="flex flex-1 overflow-hidden">
        <div className="w-80 border-r overflow-y-auto">
          <ConfigTree
            tree={tree}
            loading={treeLoading}
            onSelect={(t, id) => setSelected({ entityType: t, entityId: id })}
            selected={selected}
          />
        </div>
        <div className="flex-1 overflow-y-auto p-4">
          <div className="text-sm text-gray-500">
            {selected ? `Selected: ${selected.entityType} / ${selected.entityId}` : 'Select an entity from the tree.'}
          </div>
        </div>
      </div>
    </div>
  );
};
