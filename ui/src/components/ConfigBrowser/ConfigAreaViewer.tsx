import React, { useState } from 'react';
import JsonView from '@uiw/react-json-view';
import type { ConfigArea } from '../../types/config';

interface Props {
  area: ConfigArea;
  onRefresh: () => void;
  refreshing: boolean;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.round(diff / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.round(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const d = Math.round(hr / 24);
  return `${d}d ago`;
}

export const ConfigAreaViewer: React.FC<Props> = ({ area, onRefresh, refreshing }) => {
  const [open, setOpen] = useState(false);
  const label = area.config_area.replace(/_/g, ' ');

  return (
    <div className="border rounded mb-2 bg-white">
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b">
        <button
          className="text-sm text-gray-700 hover:text-black"
          onClick={() => setOpen((o) => !o)}
        >{open ? '▾' : '▸'} {label}</button>
        <span className="text-xs text-gray-500 ml-auto">
          last: {relativeTime(area.observed_at)} ({area.source_event})
        </span>
        <button
          className="text-sm px-2 py-0.5 rounded hover:bg-gray-200"
          onClick={onRefresh}
          disabled={refreshing}
          title="Refresh this area"
        >{refreshing ? '⟳' : '↻'}</button>
      </div>
      {open && (
        <div className="p-3 text-sm overflow-auto max-h-96">
          <JsonView
            value={area.payload as object}
            displayDataTypes={false}
            collapsed={2}
          />
        </div>
      )}
    </div>
  );
};
