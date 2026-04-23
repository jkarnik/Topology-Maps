import React from 'react';
import type { ConfigWsEvent } from '../../types/config';

interface Props {
  progress: Extract<ConfigWsEvent, { type: 'sweep.progress' }> | null;
  kind: string | null;
  onClose: () => void;
}

const MONO: React.CSSProperties = { fontFamily: "'JetBrains Mono', monospace" };

export const BaselineProgressOverlay: React.FC<Props> = ({ progress, kind, onClose }) => {
  if (!progress) return null;
  const pct = progress.total_calls > 0
    ? Math.round((progress.completed_calls / progress.total_calls) * 100)
    : 0;

  const accent = kind === 'anti_drift' ? 'var(--accent-cyan)' : 'var(--accent-amber)';

  return (
    <div
      role="dialog"
      aria-live="polite"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.65)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 50,
        backdropFilter: 'blur(2px)',
      }}
    >
      <div
        style={{
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '8px',
          padding: '22px 24px',
          width: '440px',
          boxShadow: '0 20px 60px rgba(0, 0, 0, 0.6)',
          ...MONO,
        }}
      >
        <h3
          style={{
            margin: 0,
            fontSize: '14px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '0.04em',
            marginBottom: '14px',
          }}
        >
          {kind === 'anti_drift' ? 'Anti-drift sweep running' : 'Baseline in progress'}
        </h3>
        <div
          style={{
            fontSize: '11px',
            color: 'var(--text-secondary)',
            marginBottom: '10px',
            letterSpacing: '0.04em',
          }}
        >
          <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
            {progress.completed_calls.toLocaleString()}
          </span>
          <span style={{ color: 'var(--text-muted)' }}>{' / '}</span>
          <span>{progress.total_calls.toLocaleString()} calls</span>
        </div>
        <div
          style={{
            height: '6px',
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '3px',
            overflow: 'hidden',
            marginBottom: '14px',
          }}
          aria-label="progress"
        >
          <div
            style={{
              height: '100%',
              background: accent,
              boxShadow: `0 0 10px ${accent}`,
              width: `${pct}%`,
              transition: 'width 0.3s ease',
            }}
          />
        </div>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '10px',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}
        >
          <span style={{ color: accent, fontWeight: 600 }}>{pct}% complete</span>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid var(--border-subtle)',
              borderRadius: '4px',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              padding: '4px 10px',
              fontSize: '10px',
              fontFamily: "'JetBrains Mono', monospace",
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
            }}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
};
