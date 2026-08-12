import { select } from 'd3-selection';
import { zoom as d3Zoom, zoomIdentity, type ZoomTransform } from 'd3-zoom';
import { WORLD_VIEWBOX } from './worldProjection';

export type { ZoomTransform };

/**
 * 1 = the fitted "see the whole world" state (also the floor, so the user
 * can't pan into empty space past the world's edges while zoomed out).
 * 20 is deep enough to separate any realistically-close sites.
 */
const SCALE_EXTENT: [number, number] = [1, 20];

/** Multiplier applied per +/- button click. */
const ZOOM_STEP = 1.4;

export interface WorldMapZoomController {
  zoomIn: () => void;
  zoomOut: () => void;
  destroy: () => void;
}

/**
 * Attaches d3-zoom (scroll, drag, pinch, double-click — all d3-zoom
 * defaults, no custom gesture code) to `svgEl` and reports every zoom
 * transform via `onTransform`. Fires `onTransform` once immediately with
 * the identity transform so callers can size circles correctly before
 * the user has interacted at all.
 */
export function attachWorldMapZoom(
  svgEl: SVGSVGElement,
  onTransform: (transform: ZoomTransform) => void,
): WorldMapZoomController {
  const selection = select<SVGSVGElement, unknown>(svgEl);
  const worldExtent: [[number, number], [number, number]] = [
    [0, 0],
    [WORLD_VIEWBOX.width, WORLD_VIEWBOX.height],
  ];
  const behavior = d3Zoom<SVGSVGElement, unknown>()
    .scaleExtent(SCALE_EXTENT)
    // Without an explicit extent/translateExtent, d3-zoom leaves panning
    // unconstrained at any scale (including the scale-1 floor) — the
    // scaleExtent floor alone only stops zooming out further, it does not
    // stop dragging the world off-screen. Pinning both extents to the
    // viewBox keeps the fitted view's edges as the pan boundary, so at
    // scale 1 the map can't be dragged at all, and at higher scales you
    // can pan up to (but not past) the world's edges.
    .extent(worldExtent)
    .translateExtent(worldExtent)
    .on('zoom', (event) => onTransform(event.transform));

  selection.call(behavior);
  behavior.transform(selection, zoomIdentity);

  return {
    zoomIn: () => behavior.scaleBy(selection, ZOOM_STEP),
    zoomOut: () => behavior.scaleBy(selection, 1 / ZOOM_STEP),
    destroy: () => selection.on('.zoom', null),
  };
}
