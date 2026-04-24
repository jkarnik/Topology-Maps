import { useState, useCallback, useRef, useEffect } from 'react';
import { L2Topology, L3Topology, ViewMode, Device, Edge, DrillDownState } from '../types/topology';
import { MerakiNetwork, MerakiStatus, RefreshPhase, MerakiDeviceDetail } from '../types/meraki';
import { loadCache, saveCache, SCHEMA_VERSION, CachedNetwork } from '../lib/merakiCache';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Filter a cached All-Networks topology down to a single network.
 *
 * Nodes carry `network_id` (infrastructure from /topology/l2, clients are
 * annotated by the /topology/l2/clients route).  Subnets carry `network_id`
 * (populated by the backend transformer).  Edges are kept when both ends
 * resolve to a node in the filtered set.
 */
function filterByNetwork(
  cached: CachedNetwork,
  networkId: string,
): CachedNetwork {
  const nodes = cached.l2.nodes.filter((n) => n.network_id === networkId);
  const ids = new Set(nodes.map((n) => n.id));
  const edges = cached.l2.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
  const subnets = cached.l3.subnets.filter((s) => s.network_id === networkId);
  // L3 routes in the current data model don't carry a network_id; they're
  // keyed by subnet id.  Keep only routes whose endpoints survive the filter.
  const subnetIds = new Set(subnets.map((s) => s.id));
  const routes = cached.l3.routes.filter(
    (r) => subnetIds.has(r.from_subnet) && subnetIds.has(r.to_subnet),
  );
  // Device details keyed by serial — keep only detail for nodes surviving
  // the node filter.
  const deviceDetails: Record<string, MerakiDeviceDetail> = {};
  for (const id of ids) {
    const d = cached.deviceDetails?.[id];
    if (d) deviceDetails[id] = d;
  }
  return {
    l2: { nodes, edges },
    l3: { subnets, routes },
    deviceDetails,
  };
}

// ---------------------------------------------------------------------------
// Return type
// ---------------------------------------------------------------------------

export interface UseMerakiTopologyReturn {
  // Topology (same shape as useTopology)
  l2Topology: L2Topology | null;
  l3Topology: L3Topology | null;
  viewMode: ViewMode;
  setViewMode: (mode: ViewMode) => void;
  selectedDevice: Device | null;
  setSelectedDevice: (device: Device | null) => void;
  drillDown: DrillDownState;
  drillInto: (deviceId: string, label: string) => void;
  drillBack: (index: number) => void;
  drillReset: () => void;

  // Meraki-specific: networks
  networks: MerakiNetwork[];
  selectedNetwork: string | null;
  setSelectedNetwork: (networkId: string | null) => void;
  fetchNetworks: () => Promise<string | null>;

  // Meraki-specific: refresh
  refresh: (networkId?: string | null) => Promise<void>;

  // Seed-file integration: check `ui/public/meraki-topology-seed.json` to
  // paint the first page load without any Meraki API calls, and let the
  // user persist their current cache back to that file for commit.
  loadSeedFile: () => Promise<boolean>;
  saveSnapshot: () => Promise<boolean>;

  // Per-device detail lookup.  Returns the pre-fetched detail from the
  // cache when available; only falls back to the live API if the cache
  // doesn't contain an entry for this serial.
  getDeviceDetail: (serial: string) => Promise<MerakiDeviceDetail | null>;
  isRefreshing: boolean;
  refreshPhase: RefreshPhase | null;
  refreshProgress: number;
  refreshTotal: number;
  remainingSeconds: number | null;
  lastUpdated: Date | null;
  clientCounts: Record<string, number>;
  loadingMessage: string;

  // Meraki-specific: config
  isConfigured: boolean;
  orgId: string | null;
  orgName: string | null;

  // Errors / loading
  isLoading: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useMerakiTopology(): UseMerakiTopologyReturn {
  // Load the persisted cache ONCE at first render.  Lazy initializers below
  // read from this snapshot, so the UI can paint cached data on the first
  // paint without waiting for an effect — that's what makes a full page
  // reload feel instant and API-free.
  const bootCacheRef = useRef<ReturnType<typeof loadCache> | undefined>(undefined);
  if (bootCacheRef.current === undefined) {
    bootCacheRef.current = loadCache();
  }
  const bootCache = bootCacheRef.current;
  const cacheKey = (id: string | null) => id ?? '__all__';
  const initialTopology = bootCache
    ? bootCache.topology[cacheKey(bootCache.selectedNetwork)] ?? null
    : null;

  // --- Topology state -------------------------------------------------------
  const [l2Topology, setL2Topology] = useState<L2Topology | null>(
    initialTopology?.l2 ?? null,
  );
  const [l3Topology, setL3Topology] = useState<L3Topology | null>(
    initialTopology?.l3 ?? null,
  );
  const [viewMode, setViewMode] = useState<ViewMode>('l2');
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [drillDown, setDrillDown] = useState<DrillDownState>({
    path: [],
    currentDeviceId: null,
    currentVlanId: null,
  });

  // --- Network state --------------------------------------------------------
  const [networks, setNetworks] = useState<MerakiNetwork[]>(
    bootCache?.networks ?? [],
  );
  const [selectedNetwork, setSelectedNetwork] = useState<string | null>(
    bootCache?.selectedNetwork ?? null,
  );

  // --- Refresh state --------------------------------------------------------
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshPhase, setRefreshPhase] = useState<RefreshPhase | null>(null);
  const [refreshProgress, setRefreshProgress] = useState(0);
  const [refreshTotal, setRefreshTotal] = useState(0);
  const [remainingSeconds] = useState<number | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(
    bootCache?.lastUpdated ? new Date(bootCache.lastUpdated) : null,
  );
  const [clientCounts] = useState<Record<string, number>>({});

  // --- Config state ---------------------------------------------------------
  // If we successfully loaded a cache, we know the key was valid at some
  // point — treat it as configured until /status says otherwise.
  const [isConfigured, setIsConfigured] = useState<boolean>(!!bootCache);
  const [orgId, setOrgId] = useState<string | null>(
    bootCache?.orgId ?? null,
  );
  const [orgName, setOrgName] = useState<string | null>(
    bootCache?.orgName ?? null,
  );

  // --- General --------------------------------------------------------------
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref to abort an in-progress refresh stream
  const abortControllerRef = useRef<AbortController | null>(null);

  // Per-network cache of the fully-assembled topology. Key is the network ID,
  // or the '__all__' sentinel for the "All Networks" view.
  const cacheRef = useRef<Map<string, CachedNetwork>>(
    new Map(bootCache ? Object.entries(bootCache.topology) : []),
  );

  // -------------------------------------------------------------------------
  // Persist cache to localStorage whenever a write-worthy state changes.
  // `lastUpdated` is bumped after every successful refresh, and
  // `selectedNetwork`/`networks` change through their own flows, so
  // listening to these three keys plus `orgName` covers every mutation
  // path — including client-side filtering, which updates cacheRef and
  // selectedNetwork together.
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (networks.length === 0 && cacheRef.current.size === 0) return;
    saveCache({
      orgId,
      orgName,
      networks,
      selectedNetwork,
      topology: Object.fromEntries(cacheRef.current),
      lastUpdated: lastUpdated ? lastUpdated.toISOString() : null,
    });
  }, [orgId, orgName, networks, selectedNetwork, lastUpdated]);

  // -------------------------------------------------------------------------
  // fetchNetworks — calls /api/meraki/status then /api/meraki/networks
  // -------------------------------------------------------------------------

  const fetchNetworks = useCallback(async (): Promise<string | null> => {
    setIsLoading(true);
    setError(null);
    try {
      // 1. Check configuration / org info
      const statusRes = await fetch('/api/meraki/status');
      if (!statusRes.ok) {
        if (statusRes.status === 401) {
          setIsConfigured(false);
          setError('Meraki API key is not configured');
          return null;
        }
        throw new Error(`Status check failed: ${statusRes.statusText}`);
      }
      const statusData = (await statusRes.json()) as MerakiStatus & {
        organizations?: { id: string; name: string }[];
      };
      setIsConfigured(statusData.configured ?? true);
      // The /status endpoint returns organizations array; pick first name
      if (statusData.organizations && statusData.organizations.length > 0) {
        setOrgId(statusData.organizations[0].id ?? null);
        setOrgName(statusData.organizations[0].name ?? null);
      } else if (statusData.org_name) {
        setOrgName(statusData.org_name);
      }

      // 2. Fetch network list
      const networksRes = await fetch('/api/meraki/networks');
      if (!networksRes.ok) {
        throw new Error(`Failed to fetch networks: ${networksRes.statusText}`);
      }
      const networksData = (await networksRes.json()) as { networks: MerakiNetwork[] };
      const networkList = networksData.networks ?? [];
      setNetworks(networkList);
      // Auto-select first network if none selected (all-networks is too slow)
      if (!selectedNetwork && networkList.length > 0) {
        setSelectedNetwork(networkList[0].id);
        return networkList[0].id;
      }
      return selectedNetwork;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch Meraki networks');
      return null;
    } finally {
      setIsLoading(false);
    }
  }, []);

  // -------------------------------------------------------------------------
  // refresh — fetch L2 + L3 topology via REST endpoints
  // -------------------------------------------------------------------------

  // Loading status message shown in the overlay
  const [loadingMessage, setLoadingMessage] = useState<string>('');

  const refresh = useCallback(async (networkId?: string | null) => {
    // Three cases:
    //   - string:    fetch that specific network
    //   - null:      fetch "All Networks"
    //   - undefined: use whatever the current selectedNetwork is
    // Anything else (e.g. an accidental event object) falls back to state.
    let targetNetwork: string | null;
    if (networkId === null) {
      targetNetwork = null;
    } else if (typeof networkId === 'string') {
      targetNetwork = networkId;
    } else {
      targetNetwork = selectedNetwork;
    }

    // Cancel any previous in-flight refresh
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    // Clear old data and reset state for clean transition
    setL2Topology(null);
    setL3Topology(null);
    setSelectedDevice(null);
    setDrillDown({ path: [], currentDeviceId: null, currentVlanId: null });
    setIsRefreshing(true);
    setRefreshPhase('discovery');
    setRefreshProgress(0);
    setRefreshTotal(0);
    setError(null);
    setLoadingMessage('Discovering networks...');

    try {
      // Single network — 5 granular stages
      if (targetNetwork) {
        const param = `?network=${encodeURIComponent(targetNetwork)}`;
        const networkName = networks.find(n => n.id === targetNetwork)?.name ?? targetNetwork;
        setRefreshTotal(5);

        // Stage 1: Infrastructure topology (devices + links + stacks)
        setRefreshPhase('topology');
        setRefreshProgress(1);
        setLoadingMessage(`Fetching infrastructure for ${networkName}...`);
        const l2Resp = await fetch(`/api/meraki/topology/l2${param}`, { signal: controller.signal });
        if (!l2Resp.ok) throw new Error(`Infrastructure fetch failed: ${l2Resp.status}`);
        const l2Data = await l2Resp.json() as L2Topology;
        setL2Topology(l2Data);
        setLoadingMessage(`${networkName}: ${l2Data.nodes.length} devices, ${l2Data.edges.length} links`);

        // Stage 2: VLANs & subnets
        setRefreshProgress(2);
        setLoadingMessage(`Fetching VLANs for ${networkName}...`);
        const l3Resp = await fetch(`/api/meraki/topology/l3${param}`, { signal: controller.signal });
        if (!l3Resp.ok) throw new Error(`VLAN fetch failed: ${l3Resp.status}`);
        const l3Data = await l3Resp.json() as L3Topology;
        setL3Topology(l3Data);
        setLoadingMessage(`${l3Data.subnets.length} VLANs loaded`);

        // Stage 3: Wireless clients (separate call, can be slow)
        setRefreshPhase('clients');
        setRefreshProgress(3);
        setLoadingMessage(`Fetching wireless clients for ${networkName}...`);
        let finalL2: L2Topology = l2Data;
        try {
          const clientsResp = await fetch(`/api/meraki/topology/l2/clients${param}`, { signal: controller.signal });
          if (clientsResp.ok) {
            const clientsData = await clientsResp.json();
            const clientNodes = clientsData.nodes as Device[];
            const clientEdges = clientsData.edges as Edge[];
            if (clientNodes.length > 0) {
              finalL2 = {
                nodes: [...l2Data.nodes, ...clientNodes],
                edges: [...l2Data.edges, ...clientEdges],
              };
              setL2Topology(finalL2);
              setLoadingMessage(`Added ${clientsData.client_count} wireless clients from ${clientsData.ap_count} APs`);
            } else {
              setLoadingMessage('No wireless clients found');
            }
          }
        } catch (err) {
          if ((err as Error).name === 'AbortError') throw err;
          setLoadingMessage('Clients fetch skipped');
        }

        // Stage 4: Per-device detail (clients + switch ports) for every
        // device in this network.  Pre-loading these lets the right-hand
        // detail panel open without firing any additional API calls.
        setRefreshProgress(4);
        setLoadingMessage(`Fetching device details for ${networkName}...`);
        let deviceDetails: Record<string, MerakiDeviceDetail> = {};
        try {
          const detailResp = await fetch(
            `/api/meraki/topology/device-details${param}`,
            { signal: controller.signal },
          );
          if (detailResp.ok) {
            deviceDetails = (await detailResp.json()) as Record<string, MerakiDeviceDetail>;
            const n = Object.keys(deviceDetails).length;
            setLoadingMessage(`Cached detail for ${n} device${n === 1 ? '' : 's'}`);
          }
        } catch (err) {
          if ((err as Error).name === 'AbortError') throw err;
          setLoadingMessage('Device-detail fetch skipped');
        }

        // Stage 5: Done — cache the assembled payload for instant return visits
        cacheRef.current.set(cacheKey(targetNetwork), {
          l2: finalL2,
          l3: l3Data,
          deviceDetails,
        });
        setRefreshProgress(5);
        setRefreshPhase('complete');
        setLastUpdated(new Date());
        setLoadingMessage(`Done — ${networkName}`);
      } else {
        // All Networks — fetch each network with granular stages
        const networkList = networks.length > 0 ? networks : [];
        if (networkList.length === 0) {
          throw new Error('No networks available');
        }

        const totalSteps = networkList.length * 4; // 4 stages per network
        setRefreshTotal(totalSteps);
        setRefreshPhase('topology');

        const allNodes: Device[] = [];
        const allEdges: Edge[] = [];
        const allSubnets: L3Topology['subnets'] = [];
        const allRoutes: L3Topology['routes'] = [];
        const allDeviceDetails: Record<string, MerakiDeviceDetail> = {};

        for (let i = 0; i < networkList.length; i++) {
          const net = networkList[i];
          const param = `?network=${encodeURIComponent(net.id)}`;
          const stepBase = i * 4;

          // Stage A: Infrastructure
          setRefreshProgress(stepBase + 1);
          setLoadingMessage(`${net.name}: fetching infrastructure (${i + 1}/${networkList.length})...`);
          try {
            const l2Resp = await fetch(`/api/meraki/topology/l2${param}`, { signal: controller.signal });
            if (l2Resp.ok) {
              const l2Data = await l2Resp.json() as L2Topology;
              allNodes.push(...l2Data.nodes);
              allEdges.push(...l2Data.edges);
            }
          } catch (err) {
            if ((err as Error).name === 'AbortError') throw err;
          }
          setL2Topology({ nodes: [...allNodes], edges: [...allEdges] });

          // Stage B: VLANs
          setRefreshProgress(stepBase + 2);
          setLoadingMessage(`${net.name}: fetching VLANs...`);
          try {
            const l3Resp = await fetch(`/api/meraki/topology/l3${param}`, { signal: controller.signal });
            if (l3Resp.ok) {
              const l3Data = await l3Resp.json() as L3Topology;
              allSubnets.push(...l3Data.subnets);
              allRoutes.push(...l3Data.routes);
            }
          } catch (err) {
            if ((err as Error).name === 'AbortError') throw err;
          }
          setL3Topology({ subnets: [...allSubnets], routes: [...allRoutes] });

          // Stage C: Wireless clients
          setRefreshPhase('clients');
          setRefreshProgress(stepBase + 3);
          setLoadingMessage(`${net.name}: fetching wireless clients...`);
          try {
            const clientsResp = await fetch(`/api/meraki/topology/l2/clients${param}`, { signal: controller.signal });
            if (clientsResp.ok) {
              const clientsData = await clientsResp.json();
              allNodes.push(...(clientsData.nodes as Device[]));
              allEdges.push(...(clientsData.edges as Edge[]));
              setL2Topology({ nodes: [...allNodes], edges: [...allEdges] });
            }
          } catch (err) {
            if ((err as Error).name === 'AbortError') throw err;
          }

          // Stage D: Per-device detail (clients + switch ports) for this network
          const netDetails: Record<string, MerakiDeviceDetail> = {};
          setRefreshProgress(stepBase + 4);
          setLoadingMessage(`${net.name}: fetching device details...`);
          try {
            const detailResp = await fetch(
              `/api/meraki/topology/device-details${param}`,
              { signal: controller.signal },
            );
            if (detailResp.ok) {
              const detailData = (await detailResp.json()) as Record<string, MerakiDeviceDetail>;
              Object.assign(netDetails, detailData);
              Object.assign(allDeviceDetails, detailData);
            }
          } catch (err) {
            if ((err as Error).name === 'AbortError') throw err;
          }

          // Record a per-site cache entry so switching back to this site
          // later is instant without leaning on the All-Networks filter.
          const netNodes = allNodes.filter((n) => n.network_id === net.id);
          const netNodeIds = new Set(netNodes.map((n) => n.id));
          const netEdges = allEdges.filter(
            (e) => netNodeIds.has(e.source) && netNodeIds.has(e.target),
          );
          const netSubnets = allSubnets.filter((s) => s.network_id === net.id);
          const netSubnetIds = new Set(netSubnets.map((s) => s.id));
          const netRoutes = allRoutes.filter(
            (r) => netSubnetIds.has(r.from_subnet) && netSubnetIds.has(r.to_subnet),
          );
          cacheRef.current.set(net.id, {
            l2: { nodes: netNodes, edges: netEdges },
            l3: { subnets: netSubnets, routes: netRoutes },
            deviceDetails: netDetails,
          });

          setRefreshPhase('topology');
          setLoadingMessage(`Loaded ${allNodes.length} devices from ${i + 1}/${networkList.length} networks`);
        }

        // Cache the assembled All-Networks topology for instant return visits
        cacheRef.current.set('__all__', {
          l2: { nodes: [...allNodes], edges: [...allEdges] },
          l3: { subnets: [...allSubnets], routes: [...allRoutes] },
          deviceDetails: { ...allDeviceDetails },
        });
        setRefreshPhase('complete');
        setLastUpdated(new Date());
        setLoadingMessage(`Done — ${allNodes.length} devices, ${allSubnets.length} VLANs from ${networkList.length} networks`);
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return;
      }
      const msg = err instanceof Error ? err.message : 'Refresh failed';
      setError(msg);
      setLoadingMessage(`Error: ${msg}`);
    } finally {
      setIsRefreshing(false);
      setRefreshPhase(null);
      abortControllerRef.current = null;
    }
  }, [selectedNetwork, networks]);

  // -------------------------------------------------------------------------
  // selectNetwork — swap the visible network, using cache when possible
  // -------------------------------------------------------------------------
  // Replaces raw setSelectedNetwork in the hook's public surface.  If we
  // already have topology data cached for the chosen network, hydrate
  // immediately (no API calls).  Otherwise trigger a refresh for that
  // network so the view auto-updates.

  const selectNetwork = useCallback((id: string | null) => {
    setSelectedNetwork(id);

    const hydrate = (l2: L2Topology, l3: L3Topology) => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
      setIsRefreshing(false);
      setRefreshPhase(null);
      setL2Topology(l2);
      setL3Topology(l3);
      setSelectedDevice(null);
      setDrillDown({ path: [], currentDeviceId: null, currentVlanId: null });
    };

    // 1) Exact cache hit — use it directly.
    const exact = cacheRef.current.get(cacheKey(id));
    if (exact) {
      hydrate(exact.l2, exact.l3);
      return;
    }

    // 2) Asking for a specific site but we already have an All-Networks
    //    payload in cache?  Filter it client-side, save the filtered
    //    result under the site key, and hydrate.
    if (id !== null) {
      const all = cacheRef.current.get('__all__');
      if (all) {
        const filtered = filterByNetwork(all, id);
        cacheRef.current.set(cacheKey(id), filtered);
        hydrate(filtered.l2, filtered.l3);
        return;
      }
    }

    // 3) Nothing cached — fetch from the API.
    refresh(id);
  }, [refresh]);

  // -------------------------------------------------------------------------
  // Seed-file integration
  // -------------------------------------------------------------------------
  // loadSeedFile: fetch ui/public/meraki-topology-seed.json and hydrate
  // state from it.  Called by App.tsx on first Meraki tab entry when no
  // localStorage cache is present, so a fresh clone can paint topology
  // without hitting the Meraki API.  Returns true if the seed was loaded.
  //
  // saveSnapshot: POSTs the current cache to /api/meraki/save-seed, which
  // writes the file back into the repo.  Commit the file and the next
  // fresh clone will paint instantly.

  const loadSeedFile = useCallback(async (): Promise<boolean> => {
    try {
      // Server-side cache (SQLite-backed).  404 means nothing stored yet —
      // caller will fall through to the live Meraki fetch.
      const resp = await fetch('/api/meraki/cache/load', { cache: 'no-store' });
      if (!resp.ok) return false;
      const data = await resp.json();
      if (!data || typeof data !== 'object' || data.version !== SCHEMA_VERSION) return false;

      // Populate cacheRef from the seed topology map.  Defensively default
      // deviceDetails to an empty object if an older/corrupt file omitted it.
      const entries: [string, CachedNetwork][] = Object.entries(
        data.topology ?? {},
      ).map(([k, v]) => {
        const payload = v as Partial<CachedNetwork>;
        return [
          k,
          {
            l2: payload.l2 ?? { nodes: [], edges: [] },
            l3: payload.l3 ?? { subnets: [], routes: [] },
            deviceDetails: payload.deviceDetails ?? {},
          },
        ];
      });
      cacheRef.current = new Map(entries);

      setNetworks(data.networks ?? []);
      setOrgId(data.orgId ?? null);
      setOrgName(data.orgName ?? null);
      setIsConfigured(true);

      const nextSelected: string | null = data.selectedNetwork ?? null;
      setSelectedNetwork(nextSelected);

      const current = cacheRef.current.get(cacheKey(nextSelected));
      if (current) {
        setL2Topology(current.l2);
        setL3Topology(current.l3);
      }
      setLastUpdated(data.lastUpdated ? new Date(data.lastUpdated) : null);
      return true;
    } catch {
      return false;
    }
  }, []);

  const saveSnapshot = useCallback(async (): Promise<boolean> => {
    if (networks.length === 0) {
      console.warn('[saveSnapshot] aborting: no networks loaded');
      return false;
    }
    if (cacheRef.current.size === 0) {
      console.warn('[saveSnapshot] aborting: cacheRef is empty');
      return false;
    }
    const payload = {
      version: SCHEMA_VERSION,
      orgId,
      orgName,
      networks,
      selectedNetwork,
      topology: Object.fromEntries(cacheRef.current),
      lastUpdated: lastUpdated ? lastUpdated.toISOString() : null,
    };
    let body: string;
    try {
      body = JSON.stringify(payload);
    } catch (err) {
      console.error('[saveSnapshot] JSON.stringify failed:', err);
      return false;
    }
    console.log(
      `[saveSnapshot] POSTing ${(body.length / 1024 / 1024).toFixed(2)} MB `
      + `(${cacheRef.current.size} cache keys, ${networks.length} networks)`,
    );
    try {
      const resp = await fetch('/api/meraki/cache/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
      });
      if (!resp.ok) {
        const text = await resp.text().catch(() => '<no body>');
        console.error(`[saveSnapshot] HTTP ${resp.status} ${resp.statusText}: ${text}`);
      }
      return resp.ok;
    } catch (err) {
      console.error('[saveSnapshot] fetch failed:', err);
      return false;
    }
  }, [networks, orgId, orgName, selectedNetwork, lastUpdated]);

  // -------------------------------------------------------------------------
  // getDeviceDetail — cache-first device detail (clients + switch ports)
  // -------------------------------------------------------------------------
  // Walks every cached network looking for a pre-fetched entry before
  // hitting the API.  Writes any live-fetched detail back into the
  // current network's cache so the next click is also instant and the
  // next saveSnapshot includes it.

  const getDeviceDetail = useCallback(
    async (serial: string): Promise<MerakiDeviceDetail | null> => {
      for (const entry of cacheRef.current.values()) {
        const hit = entry.deviceDetails?.[serial];
        if (hit) return hit;
      }
      try {
        const resp = await fetch(`/api/meraki/devices/${encodeURIComponent(serial)}`);
        if (!resp.ok) return null;
        const data = (await resp.json()) as MerakiDeviceDetail;
        const currentEntry = cacheRef.current.get(cacheKey(selectedNetwork));
        if (currentEntry) {
          currentEntry.deviceDetails = {
            ...(currentEntry.deviceDetails ?? {}),
            [serial]: data,
          };
        }
        return data;
      } catch {
        return null;
      }
    },
    [selectedNetwork],
  );

  // -------------------------------------------------------------------------
  // Drill-down navigation (mirrors useTopology)
  // -------------------------------------------------------------------------

  const drillInto = useCallback((deviceId: string, label: string) => {
    setDrillDown(prev => ({
      path: [...prev.path, { id: deviceId, label }],
      currentDeviceId: deviceId,
      currentVlanId: null,
    }));
  }, []);

  const drillBack = useCallback((index: number) => {
    setDrillDown(prev => {
      const newPath = prev.path.slice(0, index + 1);
      const last = newPath[newPath.length - 1];
      return {
        path: newPath,
        currentDeviceId: last?.id ?? null,
        currentVlanId: null,
      };
    });
  }, []);

  const drillReset = useCallback(() => {
    setDrillDown({ path: [], currentDeviceId: null, currentVlanId: null });
  }, []);

  // -------------------------------------------------------------------------
  // Return
  // -------------------------------------------------------------------------

  return {
    // Topology
    l2Topology,
    l3Topology,
    viewMode,
    setViewMode,
    selectedDevice,
    setSelectedDevice,
    drillDown,
    drillInto,
    drillBack,
    drillReset,

    // Networks
    networks,
    selectedNetwork,
    setSelectedNetwork: selectNetwork,
    fetchNetworks,

    // Refresh + seed
    refresh,
    loadSeedFile,
    saveSnapshot,
    getDeviceDetail,
    isRefreshing,
    refreshPhase,
    refreshProgress,
    refreshTotal,
    remainingSeconds,
    lastUpdated,
    clientCounts,
    loadingMessage,

    // Config
    isConfigured,
    orgId,
    orgName,

    // General
    isLoading,
    error,
  };
}
