import type { DiffResult, DiffChangeType } from '../../types/config'

interface Props {
  diff: DiffResult
}

function renderValue(v: unknown): string {
  if (v === null) return 'null'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function ObjectDiff({ changes, unchangedCount }: { changes: DiffChangeType[]; unchangedCount: number }) {
  return (
    <div>
      <div className="grid gap-x-2 gap-y-1" role="grid" style={{ gridTemplateColumns: '140px 1fr 1fr' }}>
        {changes.map((c, i) => {
          if (c.type === 'FieldChanged') return (
            <div key={i} role="row" className="contents">
              <span role="gridcell" className="font-mono text-[9px] opacity-60 truncate self-center">{c.key}</span>
              <span role="gridcell" className="font-mono text-[10px] bg-red-500/15 text-red-400 px-1.5 py-0.5 rounded truncate">{renderValue(c.before)}</span>
              <span role="gridcell" className="font-mono text-[10px] bg-green-500/15 text-green-400 px-1.5 py-0.5 rounded truncate">{renderValue(c.after)}</span>
            </div>
          )
          if (c.type === 'FieldAdded') return (
            <div key={i} role="row" className="contents">
              <span role="gridcell" className="font-mono text-[9px] opacity-60 truncate self-center">{c.key}</span>
              <span role="gridcell" className="opacity-30 text-[10px] italic self-center">—</span>
              <span role="gridcell" className="font-mono text-[10px] bg-green-500/15 text-green-400 px-1.5 py-0.5 rounded truncate">{renderValue(c.value)}</span>
            </div>
          )
          if (c.type === 'FieldRemoved') return (
            <div key={i} role="row" className="contents">
              <span role="gridcell" className="font-mono text-[9px] opacity-60 truncate self-center">{c.key}</span>
              <span role="gridcell" className="font-mono text-[10px] bg-red-500/15 text-red-400 px-1.5 py-0.5 rounded truncate">{renderValue(c.value)}</span>
              <span role="gridcell" className="opacity-30 text-[10px] italic self-center">—</span>
            </div>
          )
          if (c.type === 'SecretChanged') return (
            <div key={i} role="row" className="contents">
              <span role="gridcell" className="font-mono text-[9px] opacity-60 truncate self-center">{c.key}</span>
              <span role="gridcell" className="text-purple-400 italic text-[9px] col-span-2 self-center">🔒 Secret changed — value not stored</span>
            </div>
          )
          return null
        })}
      </div>
      {unchangedCount > 0 && (
        <p className="text-[9px] opacity-30 italic mt-1">{unchangedCount} field{unchangedCount !== 1 ? 's' : ''} unchanged · hidden</p>
      )}
    </div>
  )
}

function ArrayDiff({ changes, unchangedCount }: { changes: DiffChangeType[]; unchangedCount: number }) {
  return (
    <div className="space-y-1">
      {changes.map((c, i) => {
        if (c.type === 'RowAdded') return (
          <div key={i} className="bg-green-500/8 border border-green-500/20 rounded px-2 py-1 text-green-400 text-[10px]">
            + {JSON.stringify(c.row)}
          </div>
        )
        if (c.type === 'RowRemoved') return (
          <div key={i} className="bg-red-500/8 border border-red-500/20 rounded px-2 py-1 text-red-400 text-[10px]">
            − {JSON.stringify(c.row)}
          </div>
        )
        if (c.type === 'RowChanged') return (
          <div key={i} className="bg-amber-500/8 border border-amber-500/20 rounded px-2 py-1">
            <div className="text-[9px] text-amber-300 mb-1">Row {String(c.identity)} changed</div>
            <ObjectDiff changes={c.field_changes} unchangedCount={0} />
          </div>
        )
        return null
      })}
      {unchangedCount > 0 && (
        <p className="text-[9px] opacity-30 italic">{unchangedCount} row{unchangedCount !== 1 ? 's' : ''} unchanged · hidden</p>
      )}
    </div>
  )
}

export function DiffViewer({ diff }: Props) {
  if (diff.shape === 'object') {
    return <ObjectDiff changes={diff.changes} unchangedCount={diff.unchanged_count} />
  }
  return <ArrayDiff changes={diff.changes} unchangedCount={diff.unchanged_count} />
}
