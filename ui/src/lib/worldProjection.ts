import { geoNaturalEarth1, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import type { GeometryCollection, Topology } from 'topojson-specification';
import landTopologyRaw from 'world-atlas/land-110m.json';

/**
 * Real-coastline world map, projected once at module load with a Natural
 * Earth projection fitted to WORLD_VIEWBOX. `project()` reuses the same
 * projection instance so site points and the WORLD_LAND_PATH background
 * stay aligned regardless of zoom/pan (those are applied afterward, via
 * an SVG transform — see lib/worldMapZoom.ts).
 */
export const WORLD_VIEWBOX = { width: 1000, height: 500 };

const landTopology = landTopologyRaw as unknown as Topology<{ land: GeometryCollection }>;
const landFeature = feature(landTopology, landTopology.objects.land);

const projection = geoNaturalEarth1().fitSize(
  [WORLD_VIEWBOX.width, WORLD_VIEWBOX.height],
  landFeature,
);

export function project(lat: number, lng: number): { x: number; y: number } {
  const point = projection([lng, lat]);
  if (!point) return { x: WORLD_VIEWBOX.width / 2, y: WORLD_VIEWBOX.height / 2 };
  return { x: point[0], y: point[1] };
}

/** Single SVG path `d` attribute for the whole landmass background. */
export const WORLD_LAND_PATH: string = geoPath(projection)(landFeature) ?? '';

/**
 * Square-root scaling (perceptual area accuracy, not linear radius) from
 * device count to circle radius, clamped so small sites stay clickable
 * and huge sites don't dominate the map. Also the clamp range applied
 * when correcting circle size for zoom (see lib/worldMapZoom.ts users).
 */
export const MIN_RADIUS = 6;
export const MAX_RADIUS = 26;

export function radiusForDeviceCount(deviceCount: number, maxDeviceCount: number): number {
  if (maxDeviceCount <= 0) return MIN_RADIUS;
  const scale = Math.sqrt(Math.max(deviceCount, 0) / maxDeviceCount);
  return Math.max(MIN_RADIUS, Math.min(MAX_RADIUS, MIN_RADIUS + scale * (MAX_RADIUS - MIN_RADIUS)));
}
