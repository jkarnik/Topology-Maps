import { useState } from 'react'
import { useNetworkCompare } from '../../hooks/useNetworkCompare'
import type { ConfigTree, NetworkCompareArea } from '../../types/config'
import { DiffViewer } from './DiffViewer'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

function AreaRow({ area, nameA, nameB }: { area: NetworkCompareArea; nameA: string; nameB: string }) {
  const [open, setOpen] = useState(false)
  const changeCount = area.diff?.changes.length ?? 0
  const isOnly = area.status === 'only_in_a' || area.status === 'only_in_b'

  return (
    <div className="border border-white/10 rounded mb-1 overflow-hidden">
      <button
        onClick={() => !isOnly && setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-white/5 transition-colors"
      >
        <span className="text-xs font-mono opacity-80">{area.config_area}</span>
        {isOnly ? (
          <span className="text-xs opacity-40">
            Only in {area.status === 'only_in_a' ? nameA : nameB}
          </span>
        ) : (
          <span className={[
            'text-xs px-2 py-0.5 rounded-full',
            changeCount > 0 ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400',
          ].join(' ')}>
            {changeCount > 0 ? `${changeCount} diff${changeCount !== 1 ? 's' : ''}` : 'identical'}
          </span>
        )}
      </button>
      {open && area.diff && (
        <div className="border-t border-white/10 p-2">
          <DiffViewer diff={area.diff} />
        </div>
      )}
    </div>
  )
}

export function CompareNetworksView({ orgId, tree }: Props) {
  const networks = tree?.networks ?? []
  const [netA, setNetA] = useState('')
  const [netB, setNetB] = useState('')
  const { result, loading, error, compare, clear } = useNetworkCompare()

  const canCompare = netA && netB && netA !== netB
  const nameA = networks.find(n => n.id === netA)?.name ?? netA
  const nameB = networks.find(n => n.id === netB)?.name ?? netB

  const handleCompare = () => {
    if (canCompare) compare(orgId, netA, netB)
  }

  const handleNetAChange = (v: string) => { setNetA(v); clear() }
  const handleNetBChange = (v: string) => { setNetB(v); clear() }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <select
          value={netA}
          onChange={e => handleNetAChange(e.target.value)}
          className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
        >
          <option value="">Select network A…</option>
          {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
        </select>
        <span className="text-xs opacity-40">vs</span>
        <select
          value={netB}
          onChange={e => handleNetBChange(e.target.value)}
          className="flex-1 bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
        >
          <option value="">Select network B…</option>
          {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
        </select>
        <button
          onClick={handleCompare}
          disabled={!canCompare || loading}
          className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs transition-colors"
        >
          {loading ? 'Comparing…' : 'Compare'}
        </button>
      </div>

      {netA && netB && netA === netB && (
        <p className="text-xs text-amber-400/70">Select two different networks.</p>
      )}

      {error && <p className="text-xs text-red-400">{error}</p>}

      {result && (
        <div>
          {result.differing_areas === 0 ? (
            <p className="text-xs opacity-50 text-center py-6">
              No differences found — these networks have identical config across all areas.
            </p>
          ) : (
            <>
              <p className="text-xs opacity-50 mb-2">
                {result.differing_areas} area{result.differing_areas !== 1 ? 's' : ''} differ · {result.total_changes} field{result.total_changes !== 1 ? 's' : ''} changed
              </p>
              {result.areas
                .filter(area =>
                  area.status === 'only_in_a' ||
                  area.status === 'only_in_b' ||
                  (area.diff?.changes.length ?? 0) > 0
                )
                .map((area, i) => (
                  <AreaRow key={i} area={area} nameA={nameA} nameB={nameB} />
                ))}
            </>
          )}
        </div>
      )}

      {!result && !loading && networks.length === 0 && (
        <p className="text-xs opacity-40 text-center py-6">
          No networks collected yet — run a baseline first.
        </p>
      )}
    </div>
  )
}
