import { useState } from 'react'
import { useCoverage } from '../../hooks/useCoverage'
import type { CoverageArea } from '../../types/config'

function usePanelResize(defaultWidth: number, min = 120, max = 480) {
  const [width, setWidth] = useState(defaultWidth)

  const onDragStart = (e: React.MouseEvent) => {
    e.preventDefault()
    const startX = e.clientX
    const startW = width

    const onMove = (ev: MouseEvent) =>
      setWidth(Math.max(min, Math.min(max, startW + ev.clientX - startX)))

    const onUp = () => {
      document.removeEventListener('mousemove', onMove)
      document.removeEventListener('mouseup', onUp)
    }

    document.addEventListener('mousemove', onMove)
    document.addEventListener('mouseup', onUp)
  }

  return { width, onDragStart }
}

function coverageColor(count: number, total: number): string {
  if (total === 0) return 'text-white/40'
  const pct = count / total
  if (pct === 1) return 'text-green-400'
  if (pct >= 0.5) return 'text-amber-400'
  return 'text-red-400'
}

interface Props { orgId: string }

export function CoverageView({ orgId }: Props) {
  const { data, loading, error } = useCoverage(orgId)
  const [selected, setSelected] = useState<CoverageArea | null>(null)
  const { width: leftWidth, onDragStart } = usePanelResize(192)

  if (loading) return <p className="text-xs opacity-40 p-4">Loading coverage…</p>
  if (error) return <p className="text-xs text-red-400 p-4">{error}</p>
  if (!data || data.areas.length === 0) return (
    <p className="text-xs opacity-40 text-center py-6">No networks collected yet — run a baseline first.</p>
  )

  return (
    <div className="flex h-full min-h-0">
      {/* Left: area list */}
      <div style={{ width: leftWidth }} className="shrink-0 flex flex-col gap-0.5 overflow-y-auto">
        {data.areas.map(area => (
          <button
            key={area.config_area}
            onClick={() => setSelected(area)}
            className={[
              'flex items-center justify-between px-2 py-1.5 rounded text-left transition-colors',
              selected?.config_area === area.config_area
                ? 'bg-indigo-500/20 border border-indigo-500/40'
                : 'hover:bg-white/5',
            ].join(' ')}
          >
            <span className="text-xs font-mono truncate opacity-80">{area.config_area}</span>
            <span className={`text-xs ml-2 shrink-0 ${coverageColor(area.network_count, area.network_total)}`}>
              {area.network_count}/{area.network_total}
            </span>
          </button>
        ))}
      </div>

      {/* Drag handle */}
      <div
        onMouseDown={onDragStart}
        className="w-1 mx-1 shrink-0 cursor-col-resize rounded hover:bg-indigo-500/40 transition-colors bg-white/5"
      />

      {/* Right: detail panel */}
      <div className="flex-1 min-w-0 overflow-y-auto pl-1">
        {!selected ? (
          <p className="text-xs opacity-30 p-4">Select a config area to see details.</p>
        ) : (
          <div>
            <p className="text-xs font-mono mb-3 opacity-70">{selected.config_area}</p>
            {selected.missing_networks.length === 0 ? (
              <p className="text-xs text-green-400/70">All networks have this config area.</p>
            ) : (
              <>
                <p className="text-xs opacity-40 mb-2">
                  {selected.missing_networks.length} network{selected.missing_networks.length !== 1 ? 's' : ''} missing
                </p>
                {selected.missing_networks.map(n => (
                  <div key={n.id} className="text-xs px-2 py-1 rounded bg-red-500/10 text-red-400/80 mb-1">
                    {n.name ?? n.id}
                  </div>
                ))}
              </>
            )}
            {selected.device_breakdown.length > 0 && (
              <div className="mt-4">
                <p className="text-xs opacity-40 mb-2">Devices with this area</p>
                {selected.device_breakdown.map(d => (
                  <div key={d.id} className="text-xs px-2 py-1 rounded bg-white/5 mb-1 opacity-70">
                    {d.name ?? d.id}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
