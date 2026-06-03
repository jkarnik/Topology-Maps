import { useState } from 'react'
import type { ConfigTree } from '../../types/config'
import { CoverageView } from './CoverageView'
import { TemplatesView } from './TemplatesView'

type SubView = 'coverage' | 'templates'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

const PILLS: { id: SubView; label: string }[] = [
  { id: 'templates', label: 'Golden Template Comparator' },
  { id: 'coverage', label: 'Coverage' },
]

export function CompareTab({ orgId, tree }: Props) {
  const [active, setActive] = useState<SubView>('templates')

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
        {active === 'templates' && <TemplatesView orgId={orgId} tree={tree} />}
        {active === 'coverage' && <CoverageView orgId={orgId} />}
      </div>
    </div>
  )
}
