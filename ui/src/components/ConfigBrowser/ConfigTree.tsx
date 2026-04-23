import type { ConfigTree as ConfigTreeData, OrgDiffResponse } from '../../types/config'

export type TreeSelection =
  | { level: 'org'; orgId: string }
  | { level: 'network'; networkId: string }
  | { level: 'device'; entityType: string; entityId: string }

interface Props {
  orgId: string
  orgName: string
  tree: ConfigTreeData | null
  loading: boolean
  selected: TreeSelection | null
  onSelect: (sel: TreeSelection) => void
  diffResult: OrgDiffResponse | null
  showAll?: boolean
  onShowAll?: () => void
}

function changeCountForOrg(diff: OrgDiffResponse): number {
  return diff.results.length
}

function changeCountForNetwork(diff: OrgDiffResponse, networkId: string, deviceSerials: string[]): number {
  return diff.results.filter(r =>
    r.entity_id === networkId || deviceSerials.includes(r.entity_id)
  ).length
}

function changeCountForEntity(diff: OrgDiffResponse, entityId: string): number {
  return diff.results.filter(r => r.entity_id === entityId).length
}

export function ConfigTree({
  orgId,
  orgName,
  tree,
  loading,
  selected,
  onSelect,
  diffResult,
  showAll = false,
  onShowAll,
}: Props) {
  if (loading) {
    return <div className="p-3 text-xs opacity-40">Loading…</div>
  }

  if (!tree) {
    return <div className="p-3 text-xs opacity-40">No configuration data</div>
  }

  const isSelected = (sel: TreeSelection): boolean => {
    if (!selected) return false
    if (sel.level !== selected.level) return false
    if (sel.level === 'org') return true
    if (sel.level === 'network' && selected.level === 'network') return sel.networkId === selected.networkId
    if (sel.level === 'device' && selected.level === 'device') return sel.entityId === selected.entityId
    return false
  }

  const nodeClass = (sel: TreeSelection): string =>
    `flex items-center gap-1.5 px-2 py-1 rounded text-xs cursor-pointer hover:bg-white/5 ${
      isSelected(sel) ? 'bg-white/8 border border-white/15' : ''
    }`

  const orgSel: TreeSelection = { level: 'org', orgId }
  const orgCount = diffResult ? changeCountForOrg(diffResult) : null

  const allNetworks = tree?.networks ?? []
  const visibleNetworks = (diffResult && !showAll)
    ? allNetworks.filter(net =>
        diffResult.results.some(r =>
          r.entity_id === net.id ||
          net.devices.some((d: { serial: string; name?: string | null }) => r.entity_id === d.serial)
        )
      )
    : allNetworks

  return (
    <div className="p-2 overflow-y-auto text-xs">
      {/* Org root */}
      <div className={nodeClass(orgSel)} onClick={() => onSelect(orgSel)}>
        <span className="opacity-50">▾</span>
        <span className="font-semibold flex-1 truncate">{orgName}</span>
        {orgCount !== null && orgCount > 0 && (
          <span className="text-[9px] bg-purple-500/20 text-purple-300 rounded px-1">{orgCount}</span>
        )}
      </div>

      {/* Networks */}
      <div className="pl-3.5 mt-0.5 space-y-0.5">
        {visibleNetworks.map((net: { id: string; name: string | null; devices: Array<{ serial: string; name?: string | null }> }) => {
          const netSel: TreeSelection = { level: 'network', networkId: net.id }
          const deviceSerials = net.devices.map((d: { serial: string; name?: string | null }) => d.serial)
          const netCount = diffResult ? changeCountForNetwork(diffResult, net.id, deviceSerials) : null
          return (
            <div key={net.id}>
              <div className={nodeClass(netSel)} onClick={() => onSelect(netSel)}>
                <span className="opacity-40">▾</span>
                <span className="flex-1 truncate">{net.name ?? net.id}</span>
                {netCount !== null && netCount > 0 && (
                  <span className="text-[9px] bg-amber-500/20 text-amber-300 rounded px-1">{netCount}</span>
                )}
              </div>

              {/* Devices under network */}
              <div className="pl-3.5 space-y-0.5">
                {net.devices.map((dev: { serial: string; name?: string | null }) => {
                  const devSel: TreeSelection = { level: 'device', entityType: 'device', entityId: dev.serial }
                  const devCount = diffResult ? changeCountForEntity(diffResult, dev.serial) : null
                  return (
                    <div
                      key={dev.serial}
                      className={`${nodeClass(devSel)} ${devCount === 0 && !isSelected(devSel) ? 'opacity-40' : ''}`}
                      onClick={() => onSelect(devSel)}
                    >
                      <span className="opacity-30">▸</span>
                      <span className="flex-1 truncate">{dev.name ?? dev.serial}</span>
                      {devCount !== null && devCount > 0 && (
                        <span className="text-[9px] bg-amber-500/20 text-amber-300 rounded px-1">{devCount}</span>
                      )}
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      {/* Footer: show all toggle when diff is loaded and some networks are filtered */}
      {diffResult && !showAll && visibleNetworks.length < allNetworks.length && (
        <div className="pt-2 pl-2">
          <button
            className="text-[9px] text-purple-400 opacity-60 hover:opacity-100"
            onClick={() => onShowAll?.()}
          >
            Show all networks & devices
          </button>
        </div>
      )}
    </div>
  )
}
