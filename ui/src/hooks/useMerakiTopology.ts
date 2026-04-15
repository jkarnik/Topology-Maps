import { useState, useCallback, useRef } from 'react';
import { L2Topology, L3Topology, ViewMode, Device, DrillDownState } from '../types/topology';
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
  fetchNetworks: () => Promise<void>;

  // Meraki-specific: refresh
  refresh: (networkId?: string) => Promise<void>;
  isRefreshing: boolean;
  refreshPhase: RefreshPhase | null;
  refreshProgress: number;
  refreshTotal: number;
  remainingSeconds: number | null;
  lastUpdated: Date | null;
  clientCounts: Record<string, number>;

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
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);
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

  const fetchNetworks = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      // 1. Check configuration / org info
      const statusRes = await fetch('/api/meraki/status');
      if (!statusRes.ok) {
        if (statusRes.status === 401) {
          setIsConfigured(false);
          setError('Meraki API key is not configured');
          return;
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
      setNetworks(networksData.networks ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch Meraki networks');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // -------------------------------------------------------------------------
  // refresh — fetch L2 + L3 topology via REST endpoints
  // -------------------------------------------------------------------------

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
    setRefreshTotal(3);
    setRemainingSeconds(null);
    setError(null);

    try {
      const networkParam = targetNetwork ? `?network=${encodeURIComponent(targetNetwork)}` : '';

      // Step 1: Fetch L2 topology (devices + infrastructure edges)
      setRefreshPhase('topology');
      setRefreshProgress(1);
      const l2Resp = await fetch(`/api/meraki/topology/l2${networkParam}`, {
        signal: controller.signal,
      });
      if (!l2Resp.ok) {
        throw new Error(`L2 fetch failed: ${l2Resp.status} ${l2Resp.statusText}`);
      }
      const l2Data = await l2Resp.json() as L2Topology;
      setL2Topology(l2Data);

      // Step 2: Fetch L3 topology (VLANs + subnets)
      setRefreshPhase('clients');
      setRefreshProgress(2);
      const l3Resp = await fetch(`/api/meraki/topology/l3${networkParam}`, {
        signal: controller.signal,
      });
      if (!l3Resp.ok) {
        throw new Error(`L3 fetch failed: ${l3Resp.status} ${l3Resp.statusText}`);
      }
      const l3Data = await l3Resp.json() as L3Topology;
      setL3Topology(l3Data);

      setRefreshProgress(3);
      setRefreshPhase('complete');
      setLastUpdated(new Date());
      setRemainingSeconds(0);
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        return;
      }
      setError(err instanceof Error ? err.message : 'Refresh failed');
    } finally {
      setIsRefreshing(false);
      setRefreshPhase(null);
      abortControllerRef.current = null;
    }
  }, [selectedNetwork]);

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

    // Config
    isConfigured,
    orgName,

    // General
    isLoading,
    error,
  };
}
