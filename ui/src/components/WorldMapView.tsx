import React, { useMemo, useState } from 'react';
import { MerakiSite } from '../types/meraki';
import { HEALTH_COLORS, HEALTH_LABELS } from '../lib/healthColors';
import { WORLD_VIEWBOX, project, radiusForDeviceCount } from '../lib/worldProjection';
import { WORLD_OUTLINE_PATHS } from '../assets/worldOutline';

interface WorldMapViewProps {
  sites: MerakiSite[];
  isConfigured: boolean;
  isLoading: boolean;
  error: string | null;
  onSelectSite: (networkId: string, origin: { xPct: number; yPct: number }) => void;
}

const LEGEND_BUCKETS: MerakiSite['health_bucket'][] = ['green', 'yellow', 'orange', 'red', 'unknown'];

const CENTER_ORIGIN = { xPct: 50, yPct: 50 };

function centeredMessage(text: string, color = 'var(--text-muted)') {
  return (
    <div className="flex items-center justify-center h-full">
      <div style={{ fontFamily: "'JetBrains Mono', monospace", color, textAlign: 'center' }}>
        <div style={{ fontSize: '14px' }}>{text}</div>
      </div>
    </div>
  );
}

export const WorldMapView: React.FC<WorldMapViewProps> = ({
  sites,
  isConfigured,
  isLoading,
  error,
  onSelectSite,
}) => {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  const mappedSites = useMemo(
    () => sites.filter((s) => s.mapped && s.lat !== null && s.lng !== null),
    [sites],
  );
  const unmappedSites = useMemo(() => sites.filter((s) => !s.mapped), [sites]);
  const maxDeviceCount = useMemo(
    () => sites.reduce((max, s) => Math.max(max, s.device_count), 1),
    [sites],
  );

  if (!isConfigured) {
    return centeredMessage('Meraki API key is not configured.');
  }
  if (isLoading && sites.length === 0) {
    return centeredMessage('LOADING SITES...');
  }
  if (error && sites.length === 0) {
    return centeredMessage(error, 'var(--accent-red)');
  }
  if (sites.length === 0) {
    return centeredMessage('No sites found.');
  }

  const hoveredSite = sites.find((s) => s.network_id === hoveredId) ?? null;
  const hoveredPoint = hoveredSite?.lat != null && hoveredSite?.lng != null
    ? project(hoveredSite.lat, hoveredSite.lng)
    : null;

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', background: 'var(--bg-primary)', overflow: 'hidden' }}>
      <svg
        viewBox={`0 0 ${WORLD_VIEWBOX.width} ${WORLD_VIEWBOX.height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', display: 'block' }}
      >
        {WORLD_OUTLINE_PATHS.map((d, i) => (
          <path key={i} d={d} fill="var(--bg-tertiary)" stroke="var(--border-subtle)" strokeWidth={1} />
        ))}

        {mappedSites.map((site) => {
          const { x, y } = project(site.lat as number, site.lng as number);
          const r = radiusForDeviceCount(site.device_count, maxDeviceCount);
          return (
            <circle
              key={site.network_id}
              cx={x}
              cy={y}
              r={r}
              fill={HEALTH_COLORS[site.health_bucket]}
              stroke={hoveredId === site.network_id ? 'var(--text-primary)' : 'none'}
              strokeWidth={2}
              style={{ cursor: 'pointer' }}
              onMouseEnter={() => setHoveredId(site.network_id)}
              onMouseLeave={() => setHoveredId((id) => (id === site.network_id ? null : id))}
              onClick={() =>
                onSelectSite(site.network_id, {
                  xPct: (x / WORLD_VIEWBOX.width) * 100,
                  yPct: (y / WORLD_VIEWBOX.height) * 100,
                })
              }
            />
          );
        })}
      </svg>

      {hoveredSite && hoveredPoint && (
        <div
          style={{
            position: 'absolute',
            left: `${(hoveredPoint.x / WORLD_VIEWBOX.width) * 100}%`,
            top: `${(hoveredPoint.y / WORLD_VIEWBOX.height) * 100}%`,
            transform: 'translate(-50%, -140%)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '4px',
            padding: '5px 9px',
            fontSize: '11px',
            color: 'var(--text-primary)',
            fontFamily: "'JetBrains Mono', monospace",
            pointerEvents: 'none',
            whiteSpace: 'nowrap',
            zIndex: 10,
          }}
        >
          {hoveredSite.name} — {hoveredSite.device_count} device{hoveredSite.device_count === 1 ? '' : 's'}
          {hoveredSite.unhealthy_pct ? `, ${Math.round(hoveredSite.unhealthy_pct * 100)}% alerting` : ''}
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          position: 'absolute', left: '14px', bottom: '12px',
          background: 'rgba(13,17,23,0.85)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', padding: '8px 12px', fontSize: '10px', color: 'var(--text-secondary)',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        <div style={{ marginBottom: '6px' }}>Size = device count</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span>Health:</span>
          {LEGEND_BUCKETS.map((bucket) => (
            <span
              key={bucket}
              title={HEALTH_LABELS[bucket]}
              style={{ width: '10px', height: '10px', borderRadius: '50%', background: HEALTH_COLORS[bucket], display: 'inline-block' }}
            />
          ))}
        </div>
      </div>

      {/* Unmapped sites panel */}
      {unmappedSites.length > 0 && (
        <div
          style={{
            position: 'absolute', right: '14px', top: '14px', width: '160px',
            background: 'rgba(13,17,23,0.9)', border: '1px solid var(--border-subtle)',
            borderRadius: '6px', padding: '8px 12px', fontSize: '11px', color: 'var(--text-secondary)',
            fontFamily: "'JetBrains Mono', monospace", maxHeight: '200px', overflowY: 'auto',
          }}
        >
          <div style={{ color: 'var(--text-muted)', fontSize: '10px', marginBottom: '6px', letterSpacing: '0.05em' }}>
            UNMAPPED ({unmappedSites.length})
          </div>
          {unmappedSites.map((site) => (
            <div
              key={site.network_id}
              onClick={() => onSelectSite(site.network_id, CENTER_ORIGIN)}
              style={{ padding: '3px 0', cursor: 'pointer', color: 'var(--text-primary)' }}
            >
              <span style={{ color: HEALTH_COLORS[site.health_bucket] }}>●</span> {site.name}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default WorldMapView;
