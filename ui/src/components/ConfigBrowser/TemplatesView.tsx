import type { ConfigTree } from '../../types/config'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

export function TemplatesView(_: Props) {
  return <div className="text-xs opacity-50 p-4">Templates — coming soon</div>
}
