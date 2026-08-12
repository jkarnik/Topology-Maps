/**
 * Simplified continent silhouettes for the world map background.
 * Coordinates are equirectangular-projected (see lib/worldProjection.ts)
 * from real coastline reference points into a 1000x500 viewBox —
 * intentionally low-fidelity; only WorldMapView's site dots need to be
 * geographically precise.
 */
export const WORLD_OUTLINE_PATHS: string[] = [
  // North America
  'M67,53 L311,56 L353,114 L294,139 L278,181 L256,192 L278,225 L194,186 L175,158 L153,117 L144,111 L125,89 Z',
  // South America
  'M286,225 L322,219 L403,264 L381,314 L344,347 L311,403 L300,342 L286,283 L278,250 Z',
  // Africa
  'M483,153 L528,147 L594,164 L642,219 L614,256 L550,344 L539,314 L536,275 L522,239 L453,208 Z',
  // Europe
  'M475,142 L486,89 L569,53 L583,69 L597,117 L564,144 L536,136 Z',
  // Asia
  'M597,142 L667,61 L972,67 L944,94 L889,150 L839,164 L794,222 L786,244 L714,228 L689,189 L672,175 L625,194 L597,161 Z',
  // Australia
  'M850,289 L867,283 L895,281 L925,325 L903,356 L883,347 L822,339 Z',
];
