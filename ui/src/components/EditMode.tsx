import React from 'react';
import type { PendingChange } from '../hooks/useEditMode';

interface EditModeProps {
  isActive: boolean;
  pendingChange: PendingChange | null;
  isApplying: boolean;
  onApply: () => void;
  onCancel: () => void;
}

/* ---------- Pulsing amber dot ---------- */

const PulsingDot: React.FC = () => (
  <span
    className="animate-pulse-dot"
    style={{
      display: 'inline-block',
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: 'var(--accent-amber)',
      boxShadow: '0 0 6px rgba(245, 166, 35, 0.6)',
      flexShrink: 0,
    }}
  />
);

/* ---------- Spinner ---------- */

const Spinner: React.FC = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    style={{ animation: 'spin 0.8s linear infinite', flexShrink: 0 }}
  >
    <circle cx="12" cy="12" r="10" stroke="var(--accent-amber)" strokeWidth="3" strokeOpacity="0.25" />
    <path
      d="M12 2a10 10 0 0 1 10 10"
      stroke="var(--accent-amber)"
      strokeWidth="3"
      strokeLinecap="round"
    />
  </svg>
);

/* ---------- Arrow icon ---------- */

const ArrowRight: React.FC = () => (
  <svg
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="var(--text-muted)"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);

/* ---------- Component ---------- */

export const EditMode: React.FC<EditModeProps> = ({
  isActive,
  pendingChange,
  isApplying,
  onApply,
  onCancel,
}) => {
  if (!isActive) return null;

  return (
    <>
      {/* Edit Mode Banner */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          padding: '8px 20px',
          background: 'rgba(245, 166, 35, 0.10)',
          borderBottom: '1px solid rgba(245, 166, 35, 0.18)',
          position: 'relative',
          flexShrink: 0,
          zIndex: 40,
        }}
      >
        {/* Left amber strip */}
        <div
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
            bottom: 0,
            width: 4,
            background: 'var(--accent-amber)',
          }}
        />

        <PulsingDot />

        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.08em',
            color: 'var(--accent-amber)',
            textTransform: 'uppercase',
          }}
        >
          Edit Mode
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: 11,
            color: 'var(--text-secondary)',
            letterSpacing: '0.04em',
          }}
        >
          — Drag to connect, click edge to disconnect
        </span>
      </div>

      {/* Pending Change Preview Panel */}
      {pendingChange && (
        <div
          style={{
            position: 'fixed',
            bottom: 28,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 100,
            background: 'var(--bg-elevated)',
            border: '1px solid var(--accent-amber)',
            borderRadius: 8,
            padding: '14px 20px',
            boxShadow: '0 8px 32px rgba(0, 0, 0, 0.5), 0 0 12px rgba(245, 166, 35, 0.12)',
            minWidth: 320,
            fontFamily: "'JetBrains Mono', monospace",
          }}
        >
          {/* Header */}
          <div
            style={{
              fontSize: 10,
              fontWeight: 700,
              letterSpacing: '0.14em',
              textTransform: 'uppercase',
              color: 'var(--accent-amber)',
              marginBottom: 10,
            }}
          >
            Pending Change
          </div>

          {/* Change details */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              fontSize: 12,
              color: 'var(--text-primary)',
              marginBottom: 14,
              flexWrap: 'wrap',
            }}
          >
            {/* Source */}
            <span style={{ fontWeight: 600 }}>
              {pendingChange.sourceDevice}
              {pendingChange.sourcePort && (
                <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: 4 }}>
                  :{pendingChange.sourcePort}
                </span>
              )}
            </span>

            {/* Arrow */}
            <span style={{ display: 'flex', alignItems: 'center' }}>
              {pendingChange.type === 'disconnect' ? (
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--accent-red)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              ) : (
                <ArrowRight />
              )}
            </span>

            {/* Target */}
            <span style={{ fontWeight: 600 }}>
              {pendingChange.targetDevice}
              {pendingChange.targetPort && (
                <span style={{ color: 'var(--text-muted)', fontWeight: 400, marginLeft: 4 }}>
                  :{pendingChange.targetPort}
                </span>
              )}
            </span>

            {/* Action badge */}
            <span
              style={{
                fontSize: 9,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.1em',
                padding: '2px 6px',
                borderRadius: 3,
                marginLeft: 4,
                background:
                  pendingChange.type === 'connect'
                    ? 'rgba(0, 214, 143, 0.15)'
                    : 'rgba(255, 71, 87, 0.15)',
                color:
                  pendingChange.type === 'connect'
                    ? 'var(--accent-green)'
                    : 'var(--accent-red)',
              }}
            >
              {pendingChange.type}
            </span>
          </div>

          {/* Action buttons or loading state */}
          {isApplying ? (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 11,
                fontWeight: 600,
                color: 'var(--accent-amber)',
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
              }}
            >
              <Spinner />
              Applying...
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 8 }}>
              {/* Apply button */}
              <button
                onClick={onApply}
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  padding: '6px 18px',
                  borderRadius: 4,
                  border: 'none',
                  background: 'var(--accent-amber)',
                  color: 'var(--bg-primary)',
                  cursor: 'pointer',
                  transition: 'opacity 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.opacity = '0.85';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLButtonElement).style.opacity = '1';
                }}
              >
                Apply
              </button>

              {/* Cancel button */}
              <button
                onClick={onCancel}
                style={{
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 11,
                  fontWeight: 600,
                  letterSpacing: '0.1em',
                  textTransform: 'uppercase',
                  padding: '6px 18px',
                  borderRadius: 4,
                  border: '1px solid var(--border-subtle)',
                  background: 'transparent',
                  color: 'var(--text-secondary)',
                  cursor: 'pointer',
                  transition: 'border-color 0.15s ease, color 0.15s ease',
                }}
                onMouseEnter={(e) => {
                  const el = e.currentTarget as HTMLButtonElement;
                  el.style.borderColor = 'var(--text-secondary)';
                  el.style.color = 'var(--text-primary)';
                }}
                onMouseLeave={(e) => {
                  const el = e.currentTarget as HTMLButtonElement;
                  el.style.borderColor = 'var(--border-subtle)';
                  el.style.color = 'var(--text-secondary)';
                }}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
};

export default EditMode;
