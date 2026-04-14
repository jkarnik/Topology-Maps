import { useState, useCallback, useRef } from 'react';
import { L2Topology, L3Topology, ViewMode, Device, DrillDownState } from '../types/topology';
import { MerakiNetwork, MerakiStatus, RefreshPhase, RefreshProgress } from '../types/meraki';

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
  const [clientCounts, setClientCounts] = useState<Record<string, number>>({});

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
  // refresh — POST /api/meraki/refresh with streaming SSE body
  // -------------------------------------------------------------------------

  const refresh = useCallback(async (networkId?: string) => {
    const targetNetwork = networkId ?? selectedNetwork;

    // Cancel any previous in-flight refresh
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setIsRefreshing(true);
    setRefreshPhase(null);
    setRefreshProgress(0);
    setRefreshTotal(0);
    setRemainingSeconds(null);
    setError(null);

    try {
      const url = targetNetwork
        ? `/api/meraki/refresh?network=${encodeURIComponent(targetNetwork)}`
        : '/api/meraki/refresh';
      const resp = await fetch(url, {
        method: 'POST',
        signal: controller.signal,
      });

      if (!resp.ok) {
        throw new Error(`Refresh request failed: ${resp.status} ${resp.statusText}`);
      }

      if (!resp.body) {
        throw new Error('No response body for SSE stream');
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });

        // SSE format: blocks separated by double newline
        // Each block may contain:
        //   event: message\n
        //   data: {...}\n
        //   \n
        const blocks = buffer.split(/\n\n/);
        // Keep the last (potentially incomplete) block in the buffer
        buffer = blocks.pop() ?? '';

        for (const block of blocks) {
          if (!block.trim()) continue;

          let dataLine = '';
          for (const line of block.split('\n')) {
            if (line.startsWith('data: ')) {
              dataLine = line.slice('data: '.length);
            }
          }

          if (!dataLine) continue;

          let payload: RefreshProgress;
          try {
            payload = JSON.parse(dataLine) as RefreshProgress;
          } catch {
            continue; // skip malformed lines
          }

          // Update state based on phase
          setRefreshPhase(payload.phase);

          switch (payload.phase) {
            case 'discovery':
              if (payload.estimated_seconds != null) {
                setRemainingSeconds(payload.estimated_seconds);
              }
              break;

            case 'topology':
              if (payload.progress != null) setRefreshProgress(payload.progress);
              if (payload.total != null) setRefreshTotal(payload.total);
              if (payload.remaining_seconds != null) setRemainingSeconds(payload.remaining_seconds);
              // Stream partial L2 topology as it arrives (nodes/edges are raw objects)
              if (payload.nodes && payload.edges) {
                setL2Topology({
                  nodes: payload.nodes as unknown as L2Topology['nodes'],
                  edges: payload.edges as unknown as L2Topology['edges'],
                });
              }
              break;

            case 'clients':
              if (payload.client_counts) {
                setClientCounts(payload.client_counts);
              }
              if (payload.remaining_seconds != null) setRemainingSeconds(payload.remaining_seconds);
              break;

            case 'complete':
              if (payload.l2) {
                setL2Topology(payload.l2 as unknown as L2Topology);
              }
              if (payload.l3) {
                setL3Topology(payload.l3 as unknown as L3Topology);
              }
              setLastUpdated(new Date());
              setRemainingSeconds(0);
              break;
          }
        }
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        // Intentionally cancelled — not an error
        return;
      }
      setError(err instanceof Error ? err.message : 'Refresh failed');
    } finally {
      setIsRefreshing(false);
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
