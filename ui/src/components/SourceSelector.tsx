import React, { useState, useRef, useEffect } from 'react';
import { DataSource } from '../types/topology';

interface SourceSelectorProps {
  value: DataSource;
  onChange: (source: DataSource) => void;
}

const SOURCES: { id: DataSource; label: string; tag: string; accent: string; tagBg: string }[] = [
  {
    id: 'meraki',
    label: 'Meraki Live',
    tag: 'API',
    accent: 'var(--accent-amber)',
    tagBg: 'rgba(245, 166, 35, 0.12)',
  },
  {
    id: 'simulated',
    label: 'Simulated',
    tag: 'SNMP',
    accent: 'var(--accent-cyan)',
    tagBg: 'rgba(0, 229, 200, 0.12)',
  },
];

export const SourceSelector: React.FC<SourceSelectorProps> = ({ value, onChange }) => {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) {
      document.addEventListener('mousedown', handleClickOutside);
    }
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const active = SOURCES.find((s) => s.id === value) ?? SOURCES[0];

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      {/* Trigger button */}
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          height: '32px',
          padding: '0 12px',
          background: 'var(--bg-tertiary)',
          border: `1px solid ${open ? active.accent : 'var(--border-subtle)'}`,
          borderRadius: '6px',
          cursor: 'pointer',
          transition: 'border-color 0.15s ease',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {/* Accent dot */}
        <span
          style={{
            width: '7px',
            height: '7px',
            borderRadius: '50%',
            background: active.accent,
            flexShrink: 0,
          }}
        />
        {/* Label */}
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: 'var(--text-primary)',
            letterSpacing: '0.04em',
          }}
        >
          {active.label}
        </span>
        {/* Tag */}
        <span
          style={{
            fontSize: '10px',
            fontWeight: 600,
            letterSpacing: '0.08em',
            color: active.accent,
            background: active.tagBg,
            padding: '1px 5px',
            borderRadius: '3px',
          }}
        >
          {active.tag}
        </span>
        {/* Chevron */}
        <svg
          width="10"
          height="6"
          viewBox="0 0 10 6"
          fill="none"
          style={{
            color: 'var(--text-muted)',
            transition: 'transform 0.15s ease',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
          }}
        >
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {/* Dropdown */}
      {open && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            minWidth: '180px',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            overflow: 'hidden',
            zIndex: 200,
            boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          }}
        >
          {SOURCES.map((src) => {
            const isSelected = src.id === value;
            return (
              <button
                key={src.id}
                onClick={() => {
                  onChange(src.id);
                  setOpen(false);
                }}
                style={{
                  width: '100%',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '10px',
                  padding: '10px 14px',
                  background: isSelected ? 'var(--bg-tertiary)' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  fontFamily: "'JetBrains Mono', monospace",
                  textAlign: 'left',
                  transition: 'background 0.1s ease',
                }}
                onMouseEnter={(e) => {
                  if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'var(--bg-surface)';
                }}
                onMouseLeave={(e) => {
                  if (!isSelected) (e.currentTarget as HTMLButtonElement).style.background = 'transparent';
                }}
              >
                <span
                  style={{
                    width: '7px',
                    height: '7px',
                    borderRadius: '50%',
                    background: src.accent,
                    flexShrink: 0,
                  }}
                />
                <span
                  style={{
                    flex: 1,
                    fontSize: '12px',
                    fontWeight: 600,
                    color: isSelected ? 'var(--text-primary)' : 'var(--text-secondary)',
                    letterSpacing: '0.04em',
                  }}
                >
                  {src.label}
                </span>
                <span
                  style={{
                    fontSize: '10px',
                    fontWeight: 600,
                    letterSpacing: '0.08em',
                    color: src.accent,
                    background: src.tagBg,
                    padding: '1px 5px',
                    borderRadius: '3px',
                  }}
                >
                  {src.tag}
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SourceSelector;
