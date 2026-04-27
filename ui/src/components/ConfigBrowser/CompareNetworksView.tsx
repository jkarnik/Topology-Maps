import type { ConfigTree } from '../../types/config'

interface Props {
  orgId: string
  tree: ConfigTree | null
}

export function CompareNetworksView(_: Props) {
  return <div className="text-xs opacity-50 p-4">Compare Networks — coming soon</div>
}
