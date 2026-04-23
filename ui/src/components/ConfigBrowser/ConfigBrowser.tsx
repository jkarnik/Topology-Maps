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

  const [sidebarWidth, setSidebarWidth] = useState(220)
  const [fromTs, setFromTs] = useState('')
  const [toTs, setToTs] = useState('')

  const handleResizeStart = (e: React.MouseEvent) => {
    const startX = e.clientX
    const startWidth = sidebarWidth
    const onMove = (me: MouseEvent) => {
      setSidebarWidth(Math.max(150, Math.min(480, startWidth + me.clientX - startX)))
    }
    const onUp = () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }

  const { orgs } = useConfigOrgs()
  const { tree, loading: treeLoading, reload: reloadTree } = useConfigTree(selectedOrgId)
  const { lastEvent, sweepProgress } = useConfigCollection(selectedOrgId)
  const orgDiff = useOrgDiff()

  // Auto-select first org
  useEffect(() => {
    if (!selectedOrgId && orgs.length > 0) setSelectedOrgId(orgs[0].org_id)
  }, [orgs, selectedOrgId])


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

  // Default fromTs to first baseline timestamp when it becomes available
  useEffect(() => {
    if (!fromTs && baselineTimestamps.length > 0) setFromTs(baselineTimestamps[0])
  }, [baselineTimestamps, fromTs])

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
    if (!treeSelected) return null
    if (treeSelected.level === 'org') {
      return { entityType: 'org' as EntityType, entityId: treeSelected.orgId }
    }
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
        sweepProgress={sweepProgress}
        onOrgChange={setSelectedOrgId}
        onStartBaseline={async () => { if (selectedOrgId) await startBaseline(selectedOrgId) }}
        onStartSweep={async () => { if (selectedOrgId) await startSweep(selectedOrgId) }}
      />

      {/* Tabs */}
      <div className="flex border-b border-white/8 text-xs" style={{ flexShrink: 0 }}>
        <button
          className={`px-4 py-2 ${activeTab === 'overview' ? 'border-b-2 border-purple-500 bg-white/5' : 'opacity-50'}`}
          onClick={() => setActiveTab('overview')}
        >Overview</button>
        <button
          className={`px-4 py-2 ${activeTab === 'history' ? 'border-b-2 border-purple-500 bg-white/5' : 'opacity-50'}`}
          onClick={() => setActiveTab('history')}
        >History</button>
      </div>

      {/* Tab content */}
      <div className="flex-1 min-h-0">

        {/* Overview tab: tree (left) + entity view (right) */}
        {activeTab === 'overview' && (
          <div className="flex h-full">
            <div style={{ width: sidebarWidth, flexShrink: 0, borderRight: '1px solid var(--border-subtle)', overflowY: 'auto' }}>
              <ConfigTree
                orgId={selectedOrgId ?? ''}
                orgName={selectedOrg?.name ?? 'Org'}
                tree={tree}
                loading={treeLoading}
                selected={treeSelected}
                onSelect={sel => setTreeSelected(sel)}
                showAll={true}
                onShowAll={() => {}}
                diffResult={orgDiff.result}
              />
            </div>
            <div
              style={{ width: '4px', cursor: 'col-resize', flexShrink: 0, background: 'transparent' }}
              onMouseDown={handleResizeStart}
              onMouseEnter={e => (e.currentTarget.style.background = 'var(--accent-amber-glow)')}
              onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
            />
            <div className="flex-1 overflow-y-auto min-w-0">
              {entityViewProps && selectedOrgId ? (
                <ConfigEntityView
                  orgId={selectedOrgId}
                  entityType={entityViewProps.entityType}
                  entityId={entityViewProps.entityId}
                />
              ) : (
                <div className="p-4 text-xs opacity-40">Select an entity from the tree.</div>
              )}
            </div>
          </div>
        )}

        {/* History tab: compare controls + diff results (full width) */}
        {activeTab === 'history' && (
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
              padding: '10px 16px', borderBottom: '1px solid var(--border-subtle)',
              background: 'var(--bg-secondary)', fontFamily: "'JetBrains Mono', monospace",
              flexShrink: 0,
            }}>
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', letterSpacing: '0.06em' }}>Compare:</span>
              {(['from', 'to'] as const).map(which => (
                <select
                  key={which}
                  value={which === 'from' ? fromTs : toTs}
                  onChange={e => which === 'from' ? setFromTs(e.target.value) : setToTs(e.target.value)}
                  style={{
                    background: 'var(--bg-tertiary)', color: 'var(--text-primary)',
                    border: '1px solid var(--border-subtle)', borderRadius: '5px',
                    padding: '4px 8px', fontSize: '11px', fontFamily: "'JetBrains Mono', monospace", cursor: 'pointer',
                  }}
                >
                  {which === 'from'
                    ? <option value="">— select from —</option>
                    : <option value="">Now (latest)</option>
                  }
                  {baselineTimestamps.map(ts => (
                    <option key={ts} value={ts}>{new Date(ts).toLocaleString()}</option>
                  ))}
                  {which === 'from' && <option value="last7">Last 7 days</option>}
                  {which === 'from' && <option value="last30">Last 30 days</option>}
                </select>
              ))}
              <button
                disabled={!fromTs || orgDiff.loading}
                onClick={() => {
                  if (!selectedOrgId) return
                  const resolved = fromTs === 'last7'
                    ? new Date(Date.now() - 7 * 86400_000).toISOString()
                    : fromTs === 'last30'
                    ? new Date(Date.now() - 30 * 86400_000).toISOString()
                    : fromTs
                  orgDiff.compare(selectedOrgId, resolved, toTs || undefined)
                }}
                style={{
                  fontFamily: "'JetBrains Mono', monospace", fontSize: '11px', fontWeight: 600,
                  letterSpacing: '0.08em', textTransform: 'uppercase', padding: '5px 14px',
                  borderRadius: '5px', border: '1px solid var(--border-subtle)', cursor: (!fromTs || orgDiff.loading) ? 'not-allowed' : 'pointer',
                  background: 'var(--bg-tertiary)', color: (!fromTs || orgDiff.loading) ? 'var(--text-muted)' : 'var(--text-primary)',
                  opacity: (!fromTs || orgDiff.loading) ? 0.5 : 1,
                }}
              >
                {orgDiff.loading ? 'Loading…' : 'Compare'}
              </button>
              {orgDiff.result && !orgDiff.loading && (
                <button
                  onClick={() => orgDiff.clear()}
                  style={{
                    fontFamily: "'JetBrains Mono', monospace", fontSize: '11px',
                    padding: '5px 10px', borderRadius: '5px', border: '1px solid var(--border-subtle)',
                    cursor: 'pointer', background: 'transparent', color: 'var(--text-muted)',
                  }}
                >
                  Clear
                </button>
              )}
            </div>
            <div style={{ flex: 1, overflowY: 'auto' }}>
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
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
