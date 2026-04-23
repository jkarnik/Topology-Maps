import React from 'react';
import type { ConfigWsEvent } from '../../types/config';

interface Props {
  progress: Extract<ConfigWsEvent, { type: 'sweep.progress' }> | null;
  kind: string | null;
  onClose: () => void;
}

export const BaselineProgressOverlay: React.FC<Props> = ({ progress, kind, onClose }) => {
  if (!progress) return null;
  const pct = progress.total_calls > 0
    ? Math.round((progress.completed_calls / progress.total_calls) * 100)
    : 0;

  return (
    <div
      role="dialog"
      aria-live="polite"
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    >
      <div className="bg-white rounded shadow-lg p-6 w-[420px]">
        <h3 className="text-lg font-semibold mb-2">
          {kind === 'anti_drift' ? 'Anti-drift sweep running' : 'Baseline in progress'}
        </h3>
        <div className="text-sm text-gray-600 mb-4">
          {progress.completed_calls.toLocaleString()} of {progress.total_calls.toLocaleString()} calls
        </div>
        <div className="h-3 bg-gray-200 rounded overflow-hidden mb-4" aria-label="progress">
          <div className="h-full bg-blue-600" style={{ width: `${pct}%` }} />
        </div>
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>{pct}% complete</span>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">Dismiss</button>
        </div>
      </div>
    </div>
  );
};
