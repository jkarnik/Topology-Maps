import { useState } from 'react'
import { useTemplates } from '../../hooks/useTemplates'
import { useTemplateScores, isSiteScores } from '../../hooks/useTemplateScores'
import { useDevicesForTemplate } from '../../hooks/useDevicesForTemplate'
import type {
  ConfigTemplate,
  ConfigTree,
  NetworkTemplateScore,
  TemplateKind,
  TemplateScoresResponse,
  DeviceTemplateScoresResponse,
  NetworkDeviceScores,
  DeviceScore,
} from '../../types/config'

const KIND_META: Record<TemplateKind, { label: string; color: string; badge: string }> = {
  site:         { label: 'Site',         color: 'text-blue-400',   badge: 'bg-blue-500/20 text-blue-300 border-blue-500/30' },
  gateway:      { label: 'Gateway',      color: 'text-violet-400', badge: 'bg-violet-500/20 text-violet-300 border-violet-500/30' },
  switch:       { label: 'Switch',       color: 'text-teal-400',   badge: 'bg-teal-500/20 text-teal-300 border-teal-500/30' },
  access_point: { label: 'Access Point', color: 'text-amber-400',  badge: 'bg-amber-500/20 text-amber-300 border-amber-500/30' },
}

const KIND_AREA_PREFIX: Partial<Record<TemplateKind, string>> = {
  gateway:      'appliance_',
  switch:       'switch_',
  access_point: 'wireless_',
  // site has no prefix filter — shows all networks
}

const KIND_ORDER: TemplateKind[] = ['site', 'gateway', 'switch', 'access_point']

function KindBadge({ kind }: { kind: TemplateKind | null }) {
  if (!kind) return null
  const m = KIND_META[kind]
  return (
    <span className={`inline-block px-1.5 py-0.5 text-[10px] rounded border ${m.badge} leading-none`}>
      {m.label}
    </span>
  )
}

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
  orgId: string
  tree: ConfigTree | null
  onConfirm: (name: string, networkId: string, kind: TemplateKind | null, deviceSerial: string | null, deviceName: string | null) => void
  onCancel: () => void
}

function PromoteModal({ orgId, tree, onConfirm, onCancel }: PromoteModalProps) {
  const [name, setName] = useState('')
  const [networkId, setNetworkId] = useState('')
  const [kind, setKind] = useState<TemplateKind | ''>('')
  const [deviceSerial, setDeviceSerial] = useState<string | null>(null)
  const networks = tree?.networks ?? []

  const needsDevice = kind && kind !== 'site'
  const { devices, loading: devicesLoading } = useDevicesForTemplate(
    orgId,
    needsDevice ? networkId : null,
    needsDevice ? kind as TemplateKind : null,
  )

  const canSave = name.trim() && networkId && (kind === 'site' || !needsDevice || deviceSerial)

  const selectedDevice = devices.find(d => d.serial === deviceSerial) ?? null

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-[#1a1a2e] border border-white/10 rounded-lg p-5 w-80 space-y-3">
        <h3 className="text-sm font-medium">Promote as Golden Template</h3>

        <div>
          <label className="text-xs opacity-50 block mb-1">Template type</label>
          <select
            value={kind}
            onChange={e => { setKind(e.target.value as TemplateKind | ''); setDeviceSerial(null) }}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          >
            <option value="">Select a type…</option>
            {KIND_ORDER.map(k => (
              <option key={k} value={k}>{KIND_META[k].label}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs opacity-50 block mb-1">{needsDevice ? 'Step 1 — Pick a network' : 'Network'}</label>
          <select
            value={networkId}
            onChange={e => { setNetworkId(e.target.value); setDeviceSerial(null) }}
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          >
            <option value="">Select a network…</option>
            {networks.map(n => <option key={n.id} value={n.id}>{n.name ?? n.id}</option>)}
          </select>
        </div>

        {needsDevice && networkId && (
          <div>
            <label className="text-xs opacity-50 block mb-1">Step 2 — Pick a {KIND_META[kind as TemplateKind].label.toLowerCase()}</label>
            {devicesLoading ? (
              <p className="text-xs opacity-40 py-2">Loading devices…</p>
            ) : devices.length === 0 ? (
              <p className="text-xs text-amber-400/70 py-1">No {KIND_META[kind as TemplateKind].label.toLowerCase()} devices found in this network.</p>
            ) : (
              <div className="border border-white/10 rounded overflow-hidden max-h-36 overflow-y-auto">
                {devices.map(d => (
                  <button
                    key={d.serial}
                    onClick={() => setDeviceSerial(d.serial)}
                    className={[
                      'w-full flex items-center gap-2 px-3 py-2 text-xs text-left transition-colors',
                      deviceSerial === d.serial
                        ? 'bg-indigo-500/20 border-l-2 border-indigo-500'
                        : 'hover:bg-white/5 border-l-2 border-transparent',
                    ].join(' ')}
                  >
                    <span className="flex-1 font-medium">{d.name ?? d.serial}</span>
                    <span className="opacity-40 font-mono text-[10px]">{d.serial}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        <div>
          <label className="text-xs opacity-50 block mb-1">Template name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="e.g. Standard Core Switch"
            className="w-full bg-white/5 border border-white/10 rounded px-2 py-1.5 text-xs"
          />
        </div>

        <div className="flex gap-2 justify-end pt-1">
          <button onClick={onCancel} className="px-3 py-1.5 text-xs opacity-60 hover:opacity-100">Cancel</button>
          <button
            disabled={!canSave}
            onClick={() => onConfirm(
              name.trim(),
              networkId,
              kind || null,
              needsDevice ? deviceSerial : null,
              needsDevice ? (selectedDevice?.name ?? null) : null,
            )}
            className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-xs"
          >
            Save Template
          </button>
        </div>
      </div>
    </div>
  )
}

interface TemplateCardProps {
  tmpl: ConfigTemplate
  selected: boolean
  onSelect: () => void
  onDelete: () => void
}

function TemplateCard({ tmpl, selected, onSelect, onDelete }: TemplateCardProps) {
  return (
    <div
      onClick={onSelect}
      className={[
        'p-2 rounded cursor-pointer group transition-colors',
        selected
          ? 'bg-indigo-500/20 border border-indigo-500/40'
          : 'hover:bg-white/5 border border-transparent',
      ].join(' ')}
    >
      <div className="flex items-start justify-between gap-1">
        <span className="text-xs font-medium truncate">{tmpl.name}</span>
        <button
          onClick={e => { e.stopPropagation(); onDelete() }}
          className="opacity-0 group-hover:opacity-60 hover:!opacity-100 text-red-400 text-xs ml-1 shrink-0"
          title="Delete template"
        >✕</button>
      </div>
      <div className="text-xs opacity-40 mt-0.5 truncate">
        {tmpl.source_device_serial
          ? (tmpl.source_device_name ?? tmpl.source_device_serial)
          : (tmpl.source_network_name ?? tmpl.source_network_id)}
      </div>
      <div className="text-xs opacity-30 mt-0.5">{tmpl.areas.length} areas</div>
    </div>
  )
}

function DeviceScoreRow({ device }: { device: DeviceScore }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-white/10 rounded mb-1 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition-colors"
      >
        <span className="text-xs opacity-80 w-32 text-left truncate">{device.name ?? device.serial}</span>
        <span className="text-[10px] opacity-40 font-mono w-24 text-left truncate">{device.serial}</span>
        <div className="flex-1"><ScoreBar pct={device.score_pct} /></div>
      </button>
      {open && (
        <div className="border-t border-white/10 p-2 space-y-1">
          {device.missing_areas.length > 0 && (
            <p className="text-xs text-red-400/70">Missing areas: {device.missing_areas.join(', ')}</p>
          )}
          {device.area_scores.map(as => (
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

function NetworkDeviceGroup({ group }: { group: NetworkDeviceScores }) {
  const [open, setOpen] = useState(false)
  const color = group.aggregate_score >= 90 ? 'text-green-400' : group.aggregate_score >= 60 ? 'text-amber-400' : 'text-red-400'
  return (
    <div className="border border-white/10 rounded mb-2 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/5 transition-colors"
      >
        <span className="text-xs opacity-50">{open ? '▼' : '▶'}</span>
        <span className="text-xs font-medium flex-1 text-left truncate">{group.network_name}</span>
        <span className="text-xs opacity-40">{group.device_count} device{group.device_count !== 1 ? 's' : ''}</span>
        <span className={`text-xs font-semibold ml-2 ${color}`}>{group.aggregate_score}%</span>
      </button>
      {open && (
        <div className="border-t border-white/10 p-2">
          {group.devices.map(d => <DeviceScoreRow key={d.serial} device={d} />)}
        </div>
      )}
    </div>
  )
}

function ScoresPanel({ scoresData, kind }: { scoresData: TemplateScoresResponse | DeviceTemplateScoresResponse; kind: TemplateKind | null }) {
  if (isSiteScores(scoresData)) {
    const prefix = kind ? KIND_AREA_PREFIX[kind] : undefined
    const scores = prefix
      ? scoresData.scores.filter(s =>
          s.area_scores.some(a => a.config_area.startsWith(prefix) && !s.missing_areas.includes(a.config_area))
        )
      : scoresData.scores
    return (
      <div>
        <div className="flex items-center gap-2 mb-3">
          <p className="text-xs opacity-50">
            {scoresData.template.name} · {scores.length} network{scores.length !== 1 ? 's' : ''} · {scoresData.template.area_count} template areas
          </p>
          <KindBadge kind={kind} />
        </div>
        {scores.length === 0 ? (
          <p className="text-xs opacity-40 p-4 text-center">
            {scoresData.scores.length === 0
              ? 'No networks collected yet — run a baseline first.'
              : `No networks with ${kind ? KIND_META[kind].label.toLowerCase() : ''} devices found.`}
          </p>
        ) : (
          scores.map(score => <NetworkScoreRow key={score.network_id} score={score} />)
        )}
      </div>
    )
  }

  // Device template
  const { networks } = scoresData as DeviceTemplateScoresResponse
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <p className="text-xs opacity-50">
          {scoresData.template.name} · {networks.length} network{networks.length !== 1 ? 's' : ''} · {scoresData.template.area_count} template areas
        </p>
        <KindBadge kind={kind} />
      </div>
      {networks.length === 0 ? (
        <p className="text-xs opacity-40 p-4 text-center">No devices collected yet — run a baseline first.</p>
      ) : (
        networks.map(g => <NetworkDeviceGroup key={g.network_id} group={g} />)
      )}
    </div>
  )
}

interface Props { orgId: string; tree: ConfigTree | null }

export function TemplatesView({ orgId, tree }: Props) {
  const { templates, loading, promote, remove } = useTemplates(orgId)
  const [selected, setSelected] = useState<ConfigTemplate | null>(null)
  const [showPromote, setShowPromote] = useState(false)
  const { data: scoresData, loading: scoresLoading, error: scoresError } = useTemplateScores(selected?.id ?? null, orgId)

  const handlePromote = async (
    name: string,
    networkId: string,
    kind: TemplateKind | null,
    deviceSerial: string | null,
    deviceName: string | null,
  ) => {
    await promote(name, networkId, kind, deviceSerial, deviceName)
    setShowPromote(false)
  }

  const handleDelete = async (tmpl: ConfigTemplate) => {
    if (!confirm(`Delete template "${tmpl.name}"?`)) return
    if (selected?.id === tmpl.id) setSelected(null)
    await remove(tmpl.id)
  }

  const grouped = KIND_ORDER.map(kind => ({
    kind,
    items: templates.filter(t => t.kind === kind),
  })).filter(g => g.items.length > 0)

  const ungrouped = templates.filter(t => !t.kind)

  return (
    <div className="flex gap-3 h-full min-h-0">
      {showPromote && (
        <PromoteModal orgId={orgId} tree={tree} onConfirm={handlePromote} onCancel={() => setShowPromote(false)} />
      )}

      {/* Left: template list grouped by kind */}
      <div className="w-52 shrink-0 flex flex-col gap-0.5 overflow-y-auto">
        {loading && <p className="text-xs opacity-40 p-2">Loading…</p>}
        {!loading && templates.length === 0 && (
          <p className="text-xs opacity-40 p-2">No templates yet.</p>
        )}

        {grouped.map(({ kind, items }) => (
          <div key={kind} className="mb-1">
            <div className={`flex items-center gap-1.5 px-1 py-1 mb-0.5`}>
              <span className={`text-[10px] font-semibold uppercase tracking-wider ${KIND_META[kind].color}`}>
                {KIND_META[kind].label}
              </span>
              <span className="text-[10px] opacity-30">{items.length}</span>
            </div>
            {items.map(tmpl => (
              <TemplateCard
                key={tmpl.id}
                tmpl={tmpl}
                selected={selected?.id === tmpl.id}
                onSelect={() => setSelected(tmpl)}
                onDelete={() => handleDelete(tmpl)}
              />
            ))}
          </div>
        ))}

        {ungrouped.length > 0 && (
          <div className="mb-1">
            <div className="flex items-center gap-1.5 px-1 py-1 mb-0.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider opacity-40">Other</span>
              <span className="text-[10px] opacity-30">{ungrouped.length}</span>
            </div>
            {ungrouped.map(tmpl => (
              <TemplateCard
                key={tmpl.id}
                tmpl={tmpl}
                selected={selected?.id === tmpl.id}
                onSelect={() => setSelected(tmpl)}
                onDelete={() => handleDelete(tmpl)}
              />
            ))}
          </div>
        )}

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
        ) : scoresError ? (
          <p className="text-xs text-red-400 p-4">{scoresError}</p>
        ) : scoresData ? (
          <ScoresPanel scoresData={scoresData} kind={selected.kind} />
        ) : null}
      </div>
    </div>
  )
}
