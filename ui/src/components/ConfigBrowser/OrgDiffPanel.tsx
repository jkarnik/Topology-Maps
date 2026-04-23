import type { OrgDiffResponse, OrgDiffResultItem } from '../../types/config'
import type { TreeSelection } from './ConfigTree'
import { DiffViewer } from './DiffViewer'

interface Props {
  result: OrgDiffResponse | null
  loading: boolean
  error: string | null
  estimatedSeconds: number | null
  elapsed: number
  selected: TreeSelection | null
  networkNameMap: Record<string, string>
  deviceNetworkMap: Record<string, string>
}

function scopeLabel(sel: TreeSelection | null, networkNameMap: Record<string, string>): string {
  if (!sel || sel.level === 'org') return 'org-wide'
  if (sel.level === 'network') return `network: ${networkNameMap[sel.networkId] ?? sel.networkId}`
  return `device: ${sel.entityId}`
}

function filterResults(
  items: OrgDiffResultItem[],
  selected: TreeSelection | null,
  deviceNetworkMap: Record<string, string>,
): OrgDiffResultItem[] {
  if (!selected || selected.level === 'org') return items
  if (selected.level === 'network') {
    return items.filter(r =>
      r.entity_id === selected.networkId ||
      deviceNetworkMap[r.entity_id] === selected.networkId
    )
  }
  return items.filter(r => r.entity_id === selected.entityId)
}

function formatTs(ts: string): string {
  return new Date(ts).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export function OrgDiffPanel({
  result,
  loading,
  error,
  estimatedSeconds,
  elapsed,
  selected,
  networkNameMap,
  deviceNetworkMap,
}: Props) {
  if (loading) {
    const pct = estimatedSeconds
      ? Math.min(95, Math.round((elapsed / estimatedSeconds) * 100))
      : null
    return (
      <div className="p-4 space-y-3">
        <div className="text-xs opacity-60">Calculating diff across org…</div>
        <div className="h-1.5 bg-white/10 rounded overflow-hidden">
          <div
            className="h-full bg-purple-500 transition-all duration-1000"
            style={{ width: `${pct ?? 30}%` }}
          />
        </div>
        {estimatedSeconds && (
          <div className="text-[10px] opacity-40">
            ~{Math.max(0, estimatedSeconds - elapsed)}s remaining
          </div>
        )}
      </div>
    )
  }

  if (error) {
    return <div className="p-4 text-xs text-red-400">Error: {error}</div>
  }

  if (!result) {
    return (
      <div className="p-4 text-xs opacity-40">
        Select a time range above and click Compare to see changes.
      </div>
    )
  }

  const filtered = filterResults(result.results, selected, deviceNetworkMap)

  if (filtered.length === 0) {
    return (
      <div className="p-4 text-xs opacity-40">
        No changes in this window for {scopeLabel(selected, networkNameMap)}.
      </div>
    )
  }

  return (
    <div className="p-3 space-y-2 overflow-y-auto">
      <div className="text-[10px] opacity-40 mb-1">
        {filtered.length} change{filtered.length !== 1 ? 's' : ''} · {scopeLabel(selected, networkNameMap)}
      </div>
      {filtered.map((item, i) => (
        <div key={i} className="rounded border border-amber-500/20 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 bg-amber-500/7">
            <div className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="font-semibold text-xs truncate">
                {item.config_area.replace(/_/g, ' ')}
                <span className="font-normal opacity-50 ml-1.5">
                  · {item.diff.changes.length} change{item.diff.changes.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div className="text-[9px] opacity-45 mt-0.5">
                {formatTs(item.to_observed_at)}
                {item.name_hint ? ` · ${item.name_hint}` : ''}
              </div>
            </div>
          </div>
          <div className="px-3 py-2 bg-black/20 border-t border-white/5 text-[10px]">
            <DiffViewer diff={item.diff} />
          </div>
        </div>
      ))}
    </div>
  )
}
