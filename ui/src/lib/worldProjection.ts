/**
 * Equirectangular lat/lng -> x/y projection, calibrated to WORLD_VIEWBOX
 * and to the coordinates baked into assets/worldOutline.ts.
 */
export const WORLD_VIEWBOX = { width: 1000, height: 500 };

export function project(lat: number, lng: number): { x: number; y: number } {
  const x = ((lng + 180) / 360) * WORLD_VIEWBOX.width;
  const y = ((90 - lat) / 180) * WORLD_VIEWBOX.height;
  return { x, y };
}

/**
 * Square-root scaling (perceptual area accuracy, not linear radius) from
 * device count to circle radius, clamped so small sites stay clickable
 * and huge sites don't dominate the map.
 */
const MIN_RADIUS = 6;
const MAX_RADIUS = 26;

export function radiusForDeviceCount(deviceCount: number, maxDeviceCount: number): number {
  if (maxDeviceCount <= 0) return MIN_RADIUS;
  const scale = Math.sqrt(Math.max(deviceCount, 0) / maxDeviceCount);
  return Math.max(MIN_RADIUS, Math.min(MAX_RADIUS, MIN_RADIUS + scale * (MAX_RADIUS - MIN_RADIUS)));
}
