import { useState } from 'react'
import { useTemplates } from '../../hooks/useTemplates'
import { useTemplateScores } from '../../hooks/useTemplateScores'
import type { ConfigTemplate, ConfigTree, NetworkTemplateScore } from '../../types/config'

function ScoreBar({ pct }: { pct: number }) {
  const color = pct >= 90 ? 'bg-green-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500'
  const textColor = pct >= 90 ? 'text-green-400' : pct >= 60 ? 'text-amber-400' : 'text-red-400'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-white/10 rounded overflow-hidden">
        <div className={`h-full ${color} rounded`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs w-8 text-right ${textColor}`}>{pct}%</span>
    </div>
  )
}

function NetworkScoreRow({ score }: { score: NetworkTemplateScore }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-white/10 rounded mb-1 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition-colors"
      >
        <span className="text-xs opacity-80 w-32 text-left truncate">{score.network_name}</span>
        <div className="flex-1"><ScoreBar pct={score.score_pct} /></div>
      </button>
      {open && (
        <div className="border-t border-white/10 p-2 space-y-1">
          {score.missing_areas.length > 0 && (
            <p className="text-xs text-red-400/70">Missing areas: {score.missing_areas.join(', ')}</p>
          )}
          {score.area_scores.map(as => (
            <div key={as.config_area} className="flex items-center gap-2">
              <span className="text-xs font-mono opacity-60 w-40 truncate">{as.config_area}</span>
              <div className="flex-1"><ScoreBar pct={as.score_pct} /></div>
              {as.change_count > 0 && (
                <span className="text-xs text-red-400/60">{as.change_count} change{as.change_count !== 1 ? 's' : ''}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

interface PromoteModalProps {
  tree: ConfigTree | null
  onConfirm: (name: string, networkId: string) => void
  onCancel: () => void
}

function PromoteModal({ tree, onConfirm, onCancel }: PromoteModalProps) {
  const [name, setName] = useState('')
  const [networkId, setNetworkId] = useState('')
  const networks = tree?.networks ?? []
  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1a1a2e] border border-white/10 rounded-lg p-5 w-80 space-y-3">
        <h3 className="text-sm font-medium">Promote Network as Template</h3>
        <div>
          <label className="text-xs opacity-50 block mb-1">Network</label>
          <select
            value={networkId}
            onChange={e => setNetworkId(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          >
            <option value="">Select a network…</option>
            {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs opacity-50 block mb-1">Template name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Standard Retail"
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          />
        </div>
        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onCancel} className="px-3 py-1.5 text-xs opacity-60 hover:opacity-100">Cancel</button>
          <button
            disabled={!name.trim() || !networkId}
            onClick={() => onConfirm(name.trim(), networkId)}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs"
          >
            Save Template
          </button>
        </div>
      </div>
    </div>
  )
}

interface Props { orgId: string; tree: ConfigTree | null }

export function TemplatesView({ orgId, tree }: Props) {
  const { templates, loading, promote, remove } = useTemplates(orgId)
  const [selected, setSelected] = useState<ConfigTemplate | null>(null)
  const [showPromote, setShowPromote] = useState(false)
  const { data: scoresData, loading: scoresLoading } = useTemplateScores(selected?.id ?? null, orgId)

  const handlePromote = async (name: string, networkId: string) => {
    await promote(name, networkId)
    setShowPromote(false)
  }

  const handleDelete = async (tmpl: ConfigTemplate) => {
    if (!confirm(`Delete template "${tmpl.name}"?`)) return
    if (selected?.id === tmpl.id) setSelected(null)
    await remove(tmpl.id)
  }

  return (
    <div className="flex gap-3 h-full min-h-0">
      {showPromote && (
        <PromoteModal tree={tree} onConfirm={handlePromote} onCancel={() => setShowPromote(false)} />
      )}

      {/* Left: template list */}
      <div className="w-48 shrink-0 flex flex-col gap-1 overflow-y-auto">
        {loading && <p className="text-xs opacity-40 p-2">Loading…</p>}
        {!loading && templates.length === 0 && (
          <p className="text-xs opacity-40 p-2">No templates yet.</p>
        )}
        {templates.map(tmpl => (
          <div
            key={tmpl.id}
            onClick={() => setSelected(tmpl)}
            className={[
              'p-2 rounded cursor-pointer group transition-colors',
              selected?.id === tmpl.id
                ? 'bg-indigo-500/20 border border-indigo-500/40'
                : 'hover:bg-white/5 border border-transparent',
            ].join(' ')}
          >
            <div className="flex items-start justify-between">
              <span className="text-xs font-medium truncate">{tmpl.name}</span>
              <button
                onClick={e => { e.stopPropagation(); handleDelete(tmpl) }}
                className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-red-400 text-xs ml-1"
                title="Delete template"
              >✕</button>
            </div>
            <div className="text-xs opacity-40 mt-0.5 truncate">{tmpl.source_network_name ?? tmpl.source_network_id}</div>
            <div className="text-xs opacity-30 mt-0.5">{tmpl.areas.length} areas</div>
          </div>
        ))}
        <button
          onClick={() => setShowPromote(true)}
          className="mt-1 p-2 border border-dashed border-white/20 rounded text-xs opacity-50 hover:opacity-80 text-center"
        >
          + Promote a network
        </button>
      </div>

      {/* Right: scoring panel */}
      <div className="flex-1 min-w-0 overflow-y-auto">
        {!selected ? (
          <p className="text-xs opacity-30 p-4">Select a template to see network scores.</p>
        ) : scoresLoading ? (
          <p className="text-xs opacity-40 p-4">Scoring networks…</p>
        ) : scoresData ? (
          <div>
            <p className="text-xs opacity-50 mb-3">
              {scoresData.template.name} · {scoresData.scores.length} networks · {scoresData.template.area_count} template areas
            </p>
            {scoresData.scores.map(score => (
              <NetworkScoreRow key={score.network_id} score={score} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}
