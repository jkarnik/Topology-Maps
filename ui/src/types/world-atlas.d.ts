declare module 'world-atlas/land-110m.json' {
  import type { Topology, GeometryCollection } from 'topojson-specification';
  const topology: Topology<{ land: GeometryCollection }>;
  export default topology;
}
