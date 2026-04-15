import React from 'react';
import type { RefreshPhase } from '../types/meraki';

/* ---------- Props ---------- */

interface RefreshOverlayProps {
  phase: RefreshPhase | null;
  progress: number;
  total: number;
}

/* ---------- Helpers ---------- */

const phaseLabel: Record<RefreshPhase, string> = {
  discovery: 'Discovering devices...',
  devices: 'Placing devices...',
  topology: 'Fetching topology & clients...',
  clients: 'Loading VLANs & subnets...',
  complete: 'Complete',
};

/* ---------- Component ---------- */

const RefreshOverlay: React.FC<RefreshOverlayProps> = ({
  phase,
  progress,
  total,
}) => {
  // Hide when no phase or complete
  if (phase === null || phase === 'complete') return null;

  const isNearDone = phase === 'clients';
  const barColor = isNearDone ? 'var(--accent-green)' : 'var(--accent-amber)';
  const barGlow = isNearDone
    ? 'rgba(0, 214, 143, 0.35)'
    : 'rgba(245, 166, 35, 0.35)';

  // Progress fraction — clamp to [0, 1]
  const fraction = total > 0 ? Math.min(1, Math.max(0, progress / total)) : 0;
  const pct = Math.round(fraction * 100);

  // Detail text
  let detailText = '';
  if (total > 0) {
    detailText = `Step ${progress}/${total}`;
  }

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 40,
        background: 'var(--bg-secondary)',
        borderBottom: '1px solid var(--border-subtle)',
        padding: '8px 16px 10px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        boxShadow: '0 4px 20px rgba(0, 0, 0, 0.4)',
      }}
    >
      {/* Top row: phase label + remaining time */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Pulsing dot */}
          <span
            className="animate-pulse-dot"
            style={{
              display: 'inline-block',
              width: 7,
              height: 7,
              borderRadius: '50%',
              background: barColor,
              boxShadow: `0 0 6px ${barGlow}`,
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.08em',
              color: 'var(--text-primary)',
            }}
          >
            {phaseLabel[phase]}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {detailText && (
            <span
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: 10,
                color: 'var(--text-secondary)',
              }}
            >
              {detailText}
            </span>
          )}
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: 10,
              fontWeight: 600,
              color: barColor,
              minWidth: 32,
              textAlign: 'right',
            }}
          >
            {pct}%
          </span>
        </div>
      </div>

      {/* Progress bar */}
      <div
        style={{
          width: '100%',
          height: 3,
          borderRadius: 2,
          background: 'var(--bg-tertiary)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 2,
            background: barColor,
            boxShadow: `0 0 6px ${barGlow}`,
            transition: 'width 0.4s ease',
          }}
        />
      </div>
    </div>
  );
};

export default RefreshOverlay;
