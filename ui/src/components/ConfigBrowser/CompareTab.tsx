import { useState } from 'react'
import type { ConfigTree } from '../../types/config'
import { CompareNetworksView } from './CompareNetworksView'
import { CoverageView } from './CoverageView'
import { TemplatesView } from './TemplatesView'

type SubView = 'networks' | 'coverage' | 'templates'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

const PILLS: { id: SubView; label: string }[] = [
  { id: 'networks', label: 'Compare Networks' },
  { id: 'coverage', label: 'Coverage' },
  { id: 'templates', label: 'Templates' },
]

export function CompareTab({ orgId, tree }: Props) {
  const [active, setActive] = useState<SubView>('networks')

  return (
    <div className="flex flex-col gap-3 p-3 h-full">
      <div className="flex gap-1">
        {PILLS.map(p => (
          <button
            key={p.id}
            onClick={() => setActive(p.id)}
            className={[
              'px-3 py-1 rounded-full text-xs transition-colors',
              active === p.id
                ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/50'
                : 'text-white/50 hover:text-white/80 hover:bg-white/5',
            ].join(' ')}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {active === 'networks' && <CompareNetworksView orgId={orgId} tree={tree} />}
        {active === 'coverage' && <CoverageView orgId={orgId} />}
        {active === 'templates' && <TemplatesView orgId={orgId} tree={tree} />}
      </div>
    </div>
  )
}
