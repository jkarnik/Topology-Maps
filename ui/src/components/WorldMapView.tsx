import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { MerakiSite } from '../types/meraki';
import { HEALTH_COLORS, HEALTH_LABELS } from '../lib/healthColors';
import {
  MAX_RADIUS,
  MIN_RADIUS,
  WORLD_LAND_PATH,
  WORLD_VIEWBOX,
  project,
  radiusForDeviceCount,
} from '../lib/worldProjection';
import { attachWorldMapZoom, WorldMapZoomController } from '../lib/worldMapZoom';

interface WorldMapViewProps {
  sites: MerakiSite[];
  isConfigured: boolean;
  isLoading: boolean;
  error: string | null;
  onSelectSite: (networkId: string, origin: { xPct: number; yPct: number }) => void;
}

const LEGEND_BUCKETS: MerakiSite['health_bucket'][] = ['green', 'yellow', 'orange', 'red', 'unknown'];

const CENTER_ORIGIN = { xPct: 50, yPct: 50 };

const ZOOM_BUTTON_STYLE: React.CSSProperties = {
  width: '26px',
  height: '26px',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  background: 'var(--bg-tertiary)',
  border: '1px solid var(--border-subtle)',
  borderRadius: '6px',
  color: 'var(--text-secondary)',
  cursor: 'pointer',
  fontFamily: "'JetBrains Mono', monospace",
  fontSize: '14px',
  fontWeight: 600,
};

/**
 * Applies zoom-corrected radius/stroke to one site circle DOM node directly
 * (no React re-render) — called on every d3-zoom transform tick and on
 * hover enter/leave, so a circle's visual state is always a pure function
 * of (baseRadius, current zoom scale, is-this-circle-hovered).
 */
function updateCircleVisual(circle: SVGCircleElement, zoomScale: number, isHovered: boolean) {
  const baseRadius = Number(circle.dataset.baseRadius);
  const r = Math.max(MIN_RADIUS, Math.min(MAX_RADIUS, baseRadius / zoomScale));
  circle.setAttribute('r', String(r));
  circle.setAttribute('stroke', isHovered ? 'var(--text-primary)' : 'var(--bg-primary)');
  circle.setAttribute('stroke-width', String((isHovered ? 2 : 1) / zoomScale));
}

/**
 * Positions the tooltip element at `circleEl`'s live on-screen position,
 * relative to `containerEl` — computed from actual rendered geometry so
 * it's correct regardless of the map's current pan/zoom transform.
 */
function positionTooltip(tooltipEl: HTMLDivElement, containerEl: HTMLDivElement, circleEl: SVGCircleElement) {
  const circleRect = circleEl.getBoundingClientRect();
  const containerRect = containerEl.getBoundingClientRect();
  tooltipEl.style.left = `${circleRect.left + circleRect.width / 2 - containerRect.left}px`;
  tooltipEl.style.top = `${circleRect.top - containerRect.top}px`;
}

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
  const hoveredIdRef = useRef<string | null>(null);
  const currentScaleRef = useRef(1);
  const svgRef = useRef<SVGSVGElement>(null);
  const mapGroupRef = useRef<SVGGElement>(null);
  const zoomControllerRef = useRef<WorldMapZoomController | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const hoveredCircleElRef = useRef<SVGCircleElement | null>(null);

  const mappedSites = useMemo(
    () => sites.filter((s) => s.mapped && s.lat !== null && s.lng !== null),
    [sites],
  );
  const unmappedSites = useMemo(() => sites.filter((s) => !s.mapped), [sites]);
  const maxDeviceCount = useMemo(
    () => sites.reduce((max, s) => Math.max(max, s.device_count), 1),
    [sites],
  );

  // d3-zoom owns the continuous pan/zoom transform imperatively (see
  // lib/worldMapZoom.ts) — routing every zoom/pan/pinch tick through a
  // React re-render would be visibly less smooth. React only re-mounts
  // this effect (resetting to the fitted view) when the site list itself
  // changes, e.g. after a refresh poll.
  useEffect(() => {
    const svgEl = svgRef.current;
    const groupEl = mapGroupRef.current;
    if (!svgEl || !groupEl) return;

    const controller = attachWorldMapZoom(svgEl, (transform) => {
      groupEl.setAttribute('transform', transform.toString());
      currentScaleRef.current = transform.k;
      groupEl.querySelectorAll<SVGCircleElement>('circle[data-network-id]').forEach((circle) => {
        updateCircleVisual(circle, transform.k, circle.dataset.networkId === hoveredIdRef.current);
      });
      if (hoveredCircleElRef.current && tooltipRef.current && containerRef.current) {
        positionTooltip(tooltipRef.current, containerRef.current, hoveredCircleElRef.current);
      }
    });
    zoomControllerRef.current = controller;

    return () => {
      controller.destroy();
      zoomControllerRef.current = null;
    };
  }, [mappedSites]);

  // Position the tooltip once React has actually mounted its DOM node for
  // the currently-hovered site — the mouse-enter handler below fires before
  // that commit, so `tooltipRef.current` isn't available there yet.
  useLayoutEffect(() => {
    if (hoveredId && hoveredCircleElRef.current && tooltipRef.current && containerRef.current) {
      positionTooltip(tooltipRef.current, containerRef.current, hoveredCircleElRef.current);
    }
  }, [hoveredId]);

  // `isConfigured` only flips true after an async status check, so gate the
  // message on there being nothing to show — otherwise a fresh load flashes
  // "not configured" and cached sites get hidden behind it.
  if (!isConfigured && sites.length === 0) {
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

  const handleCircleEnter = (networkId: string, circleEl: SVGCircleElement) => {
    setHoveredId(networkId);
    hoveredIdRef.current = networkId;
    hoveredCircleElRef.current = circleEl;
    updateCircleVisual(circleEl, currentScaleRef.current, true);
  };

  const handleCircleLeave = (networkId: string, circleEl: SVGCircleElement) => {
    setHoveredId((id) => (id === networkId ? null : id));
    if (hoveredIdRef.current === networkId) hoveredIdRef.current = null;
    if (hoveredCircleElRef.current === circleEl) hoveredCircleElRef.current = null;
    updateCircleVisual(circleEl, currentScaleRef.current, false);
  };

  // The container box must match the viewBox aspect ratio: percentage-positioned
  // overlays (tooltip, unmapped panel) and the click handler's viewBox-derived
  // xPct/yPct only share a coordinate space when the SVG isn't letterboxed
  // inside its container.
  return (
    <div
      ref={containerRef}
      style={{
        position: 'relative',
        width: '100%',
        maxHeight: '100%',
        aspectRatio: `${WORLD_VIEWBOX.width} / ${WORLD_VIEWBOX.height}`,
        background: 'var(--bg-primary)',
        overflow: 'hidden',
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WORLD_VIEWBOX.width} ${WORLD_VIEWBOX.height}`}
        preserveAspectRatio="xMidYMid meet"
        style={{ width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
      >
        <g ref={mapGroupRef}>
          <path d={WORLD_LAND_PATH} fill="var(--bg-tertiary)" stroke="var(--border-subtle)" strokeWidth={1} />

          {mappedSites.map((site) => {
            const { x, y } = project(site.lat as number, site.lng as number);
            const baseRadius = radiusForDeviceCount(site.device_count, maxDeviceCount);
            return (
              <circle
                key={site.network_id}
                data-network-id={site.network_id}
                data-base-radius={baseRadius}
                cx={x}
                cy={y}
                r={baseRadius}
                fill={HEALTH_COLORS[site.health_bucket]}
                fillOpacity={0.82}
                stroke="var(--bg-primary)"
                strokeWidth={1}
                style={{ cursor: 'pointer' }}
                onMouseEnter={(e) => handleCircleEnter(site.network_id, e.currentTarget)}
                onMouseLeave={(e) => handleCircleLeave(site.network_id, e.currentTarget)}
                onClick={(e) => {
                  const containerRect = containerRef.current?.getBoundingClientRect();
                  const circleRect = e.currentTarget.getBoundingClientRect();
                  const origin = containerRect
                    ? {
                        xPct: ((circleRect.left + circleRect.width / 2 - containerRect.left) / containerRect.width) * 100,
                        yPct: ((circleRect.top + circleRect.height / 2 - containerRect.top) / containerRect.height) * 100,
                      }
                    : { xPct: 50, yPct: 50 };
                  onSelectSite(site.network_id, origin);
                }}
              />
            );
          })}
        </g>
      </svg>

      {hoveredSite && (
        <div
          ref={tooltipRef}
          style={{
            position: 'absolute',
            left: 0,
            top: 0,
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

      {/* Zoom controls */}
      <div style={{ position: 'absolute', right: '14px', bottom: '12px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
        <button
          type="button"
          aria-label="Zoom in"
          onClick={() => zoomControllerRef.current?.zoomIn()}
          style={ZOOM_BUTTON_STYLE}
        >
          +
        </button>
        <button
          type="button"
          aria-label="Zoom out"
          onClick={() => zoomControllerRef.current?.zoomOut()}
          style={ZOOM_BUTTON_STYLE}
        >
          −
        </button>
      </div>

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
