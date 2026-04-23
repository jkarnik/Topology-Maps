import { useState, useMemo, useEffect } from 'react'
import { CollectionStatusBar } from './CollectionStatusBar'
import { ConfigTree, type TreeSelection } from './ConfigTree'
import { ConfigEntityView } from './ConfigEntityView'
import { OrgDiffPanel } from './OrgDiffPanel'
import { useConfigOrgs } from '../../hooks/useConfigOrgs'
import { useConfigTree } from '../../hooks/useConfigTree'
import { useConfigCollection } from '../../hooks/useConfigCollection'
import { useOrgDiff } from '../../hooks/useOrgDiff'
import { startBaseline, startSweep } from '../../api/config'
import type { EntityType, ConfigStatus } from '../../types/config'

export function ConfigBrowser() {
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null)
  const [treeSelected, setTreeSelected] = useState<TreeSelection | null>(null)
  const [activeTab, setActiveTab] = useState<'overview' | 'history'>('overview')
  const [showAllTree, setShowAllTree] = useState(false)

  const { orgs } = useConfigOrgs()
  const { tree, loading: treeLoading, reload: reloadTree } = useConfigTree(selectedOrgId)
  const { lastEvent } = useConfigCollection(selectedOrgId)
  const orgDiff = useOrgDiff()

  // Auto-select first org
  useEffect(() => {
    if (!selectedOrgId && orgs.length > 0) setSelectedOrgId(orgs[0].org_id)
  }, [orgs, selectedOrgId])

  // Reset showAll when a new diff result loads
  useEffect(() => {
    if (orgDiff.result) setShowAllTree(false)
  }, [orgDiff.result])

  // Reload tree on new observations
  useEffect(() => {
    if (lastEvent?.type === 'sweep.completed' || lastEvent?.type === 'observation.updated') {
      reloadTree()
    }
  }, [lastEvent, reloadTree])

  // Build lookup maps for OrgDiffPanel
  const { networkNameMap, deviceNetworkMap } = useMemo(() => {
    const networkNameMap: Record<string, string> = {}
    const deviceNetworkMap: Record<string, string> = {}
    if (tree) {
      for (const net of tree.networks) {
        networkNameMap[net.id] = net.name ?? net.id
        for (const dev of net.devices) {
          deviceNetworkMap[dev.serial] = net.id
        }
      }
    }
    return { networkNameMap, deviceNetworkMap }
  }, [tree])

  // Baseline timestamps from org data
  const baselineTimestamps: string[] = useMemo(() => {
    const org = orgs.find(o => o.org_id === selectedOrgId)
    if (org?.last_baseline_at) return [org.last_baseline_at]
    return []
  }, [orgs, selectedOrgId])

  const selectedOrg = useMemo(
    () => orgs.find(o => o.org_id === selectedOrgId) ?? null,
    [orgs, selectedOrgId],
  )

  // Derive status from org data so CollectionStatusBar can show the sweep button
  const derivedStatus = useMemo((): ConfigStatus | null => {
    if (!selectedOrg) return null
    return {
      baseline_state: selectedOrg.baseline_state,
      last_sync: selectedOrg.last_baseline_at,
      active_sweep: selectedOrg.active_sweep_run_id
        ? { id: selectedOrg.active_sweep_run_id, kind: 'sweep', status: 'running' }
        : null,
    }
  }, [selectedOrg])

  // Determine entity to show in overview tab
  const entityViewProps = useMemo(() => {
    if (!treeSelected || treeSelected.level === 'org') return null
    if (treeSelected.level === 'network') {
      return { entityType: 'network' as EntityType, entityId: treeSelected.networkId }
    }
    return { entityType: treeSelected.entityType as EntityType, entityId: treeSelected.entityId }
  }, [treeSelected])

  return (
    <div className="flex flex-col h-full">
      <CollectionStatusBar
        orgs={orgs}
        selectedOrgId={selectedOrgId}
        status={derivedStatus}
        onOrgChange={setSelectedOrgId}
        onStartBaseline={async () => { if (selectedOrgId) await startBaseline(selectedOrgId) }}
        onStartSweep={async () => { if (selectedOrgId) await startSweep(selectedOrgId) }}
        baselineTimestamps={baselineTimestamps}
        comparing={orgDiff.loading}
        onCompare={(fromTs, toTs) => {
          if (selectedOrgId) orgDiff.compare(selectedOrgId, fromTs, toTs)
        }}
      />

      <div className="flex flex-1 min-h-0">
        {/* Sidebar tree */}
        <div className="w-52 shrink-0 border-r border-white/8 overflow-y-auto">
          <ConfigTree
            orgId={selectedOrgId ?? ''}
            orgName={selectedOrg?.name ?? 'Org'}
            tree={tree}
            loading={treeLoading}
            selected={treeSelected}
            onSelect={sel => { setTreeSelected(sel); setActiveTab('overview') }}
            showAll={showAllTree}
            onShowAll={() => setShowAllTree(true)}
            diffResult={orgDiff.result}
          />
        </div>

        {/* Right panel */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Tabs */}
          <div className="flex border-b border-white/8 text-xs">
            <button
              className={`px-4 py-2 ${activeTab === 'overview' ? 'border-b-2 border-purple-500 bg-white/5' : 'opacity-50'}`}
              onClick={() => setActiveTab('overview')}
            >Overview</button>
            <button
              className={`px-4 py-2 ${activeTab === 'history' ? 'border-b-2 border-purple-500 bg-white/5' : 'opacity-50'}`}
              onClick={() => setActiveTab('history')}
            >History</button>
          </div>

          {/* Panel content */}
          <div className="flex-1 overflow-y-auto">
            {activeTab === 'overview' && entityViewProps && selectedOrgId && (
              <ConfigEntityView
                orgId={selectedOrgId}
                entityType={entityViewProps.entityType}
                entityId={entityViewProps.entityId}
              />
            )}
            {activeTab === 'overview' && !entityViewProps && (
              <div className="p-4 text-xs opacity-40">Select an entity from the tree.</div>
            )}
            {activeTab === 'history' && (
              <OrgDiffPanel
                result={orgDiff.result}
                loading={orgDiff.loading}
                error={orgDiff.error}
                estimatedSeconds={orgDiff.estimatedSeconds}
                elapsed={orgDiff.elapsed}
                selected={treeSelected}
                networkNameMap={networkNameMap}
                deviceNetworkMap={deviceNetworkMap}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
