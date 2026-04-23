import React, { useState } from 'react';
import type { ConfigTree as ConfigTreeData, EntityType } from '../../types/config';

interface Props {
  tree: ConfigTreeData | null;
  loading: boolean;
  onSelect: (entityType: EntityType, entityId: string) => void;
  selected: { entityType: EntityType; entityId: string } | null;
}

const caret = (open: boolean) => (open ? '▾' : '▸');

export const ConfigTree: React.FC<Props> = ({ tree, loading, onSelect, selected }) => {
  const [openNetworks, setOpenNetworks] = useState<Set<string>>(new Set());

  if (loading) return <div className="p-3 text-sm text-gray-500">Loading…</div>;
  if (!tree) return <div className="p-3 text-sm text-gray-500">No data yet.</div>;

  const isSelected = (t: EntityType, id: string) =>
    selected?.entityType === t && selected.entityId === id;

  const rowClass = (t: EntityType, id: string) =>
    `cursor-pointer px-2 py-1 rounded text-sm ${isSelected(t, id) ? 'bg-blue-100 font-semibold' : 'hover:bg-gray-100'}`;

  const toggleNetwork = (id: string) => {
    setOpenNetworks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div className="p-2 text-sm overflow-y-auto h-full">
      <div className="mb-2 text-xs uppercase tracking-wide text-gray-500">Org configs</div>
      <div
        className={rowClass('org', tree.org.id)}
        onClick={() => onSelect('org', tree.org.id)}
      >
        {tree.org.id}
        <span className="ml-2 text-gray-400">({tree.org.config_areas.length} areas)</span>
      </div>

      <div className="mt-3 mb-2 text-xs uppercase tracking-wide text-gray-500">Networks</div>
      {tree.networks.map((net) => {
        const open = openNetworks.has(net.id);
        return (
          <div key={net.id}>
            <div
              className="flex items-center gap-1 cursor-pointer hover:bg-gray-50 px-1"
              onClick={() => toggleNetwork(net.id)}
            >
              <span className="w-4">{caret(open)}</span>
              <span
                onClick={(e) => { e.stopPropagation(); onSelect('network', net.id); }}
                className={`flex-1 ${rowClass('network', net.id)}`}
              >
                {net.name ?? net.id}
                <span className="ml-2 text-gray-400">({net.config_areas.length})</span>
              </span>
            </div>
            {open && net.devices.map((d) => (
              <div
                key={d.serial}
                className={`ml-6 ${rowClass('device', d.serial)}`}
                onClick={() => onSelect('device', d.serial)}
              >
                {d.name ?? d.serial}
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};
