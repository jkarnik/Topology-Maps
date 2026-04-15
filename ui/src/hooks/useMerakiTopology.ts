import { useState, useCallback, useRef } from 'react';
import { L2Topology, L3Topology, ViewMode, Device, Edge, DrillDownState } from '../types/topology';
import { MerakiNetwork, MerakiStatus, RefreshPhase } from '../types/meraki';

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
  refresh: (networkId?: string) => Promise<void>;
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
  orgName: string | null;

  // Errors / loading
  isLoading: boolean;
  error: string | null;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useMerakiTopology(): UseMerakiTopologyReturn {
  // --- Topology state -------------------------------------------------------
  const [l2Topology, setL2Topology] = useState<L2Topology | null>(null);
  const [l3Topology, setL3Topology] = useState<L3Topology | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('l2');
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [drillDown, setDrillDown] = useState<DrillDownState>({
    path: [],
    currentDeviceId: null,
    currentVlanId: null,
  });

  // --- Network state --------------------------------------------------------
  const [networks, setNetworks] = useState<MerakiNetwork[]>([]);
  const [selectedNetwork, setSelectedNetwork] = useState<string | null>(null);

  // --- Refresh state --------------------------------------------------------
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshPhase, setRefreshPhase] = useState<RefreshPhase | null>(null);
  const [refreshProgress, setRefreshProgress] = useState(0);
  const [refreshTotal, setRefreshTotal] = useState(0);
  const [remainingSeconds] = useState<number | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [clientCounts] = useState<Record<string, number>>({});

  // --- Config state ---------------------------------------------------------
  const [isConfigured, setIsConfigured] = useState(false);
  const [orgName, setOrgName] = useState<string | null>(null);

  // --- General --------------------------------------------------------------
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ref to abort an in-progress refresh stream
  const abortControllerRef = useRef<AbortController | null>(null);

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

  const refresh = useCallback(async (networkId?: string) => {
    const targetNetwork = networkId ?? selectedNetwork;

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
      // Single network — 4 granular stages
      if (targetNetwork) {
        const param = `?network=${encodeURIComponent(targetNetwork)}`;
        const networkName = networks.find(n => n.id === targetNetwork)?.name ?? targetNetwork;
        setRefreshTotal(4);

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
        try {
          const clientsResp = await fetch(`/api/meraki/topology/l2/clients${param}`, { signal: controller.signal });
          if (clientsResp.ok) {
            const clientsData = await clientsResp.json();
            const clientNodes = clientsData.nodes as Device[];
            const clientEdges = clientsData.edges as Edge[];
            if (clientNodes.length > 0) {
              setL2Topology(prev => prev ? {
                nodes: [...prev.nodes, ...clientNodes],
                edges: [...prev.edges, ...clientEdges],
              } : prev);
              setLoadingMessage(`Added ${clientsData.client_count} wireless clients from ${clientsData.ap_count} APs`);
            } else {
              setLoadingMessage('No wireless clients found');
            }
          }
        } catch (err) {
          if ((err as Error).name === 'AbortError') throw err;
          setLoadingMessage('Clients fetch skipped');
        }

        // Stage 4: Done
        setRefreshProgress(4);
        setRefreshPhase('complete');
        setLastUpdated(new Date());
        setLoadingMessage(`Done — ${networkName}`);
      } else {
        // All Networks — fetch each network with granular stages
        const networkList = networks.length > 0 ? networks : [];
        if (networkList.length === 0) {
          throw new Error('No networks available');
        }

        const totalSteps = networkList.length * 3; // 3 stages per network
        setRefreshTotal(totalSteps);
        setRefreshPhase('topology');

        const allNodes: Device[] = [];
        const allEdges: Edge[] = [];
        const allSubnets: L3Topology['subnets'] = [];
        const allRoutes: L3Topology['routes'] = [];

        for (let i = 0; i < networkList.length; i++) {
          const net = networkList[i];
          const param = `?network=${encodeURIComponent(net.id)}`;
          const stepBase = i * 3;

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

          setRefreshPhase('topology');
          setLoadingMessage(`Loaded ${allNodes.length} devices from ${i + 1}/${networkList.length} networks`);
        }

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
    setSelectedNetwork,
    fetchNetworks,

    // Refresh
    refresh,
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
    orgName,

    // General
    isLoading,
    error,
  };
}
