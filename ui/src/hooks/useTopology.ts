import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { L2Topology, L3Topology, ViewMode, WSEvent, Device, DrillDownState } from '../types/topology';
import { useWebSocket } from './useWebSocket';

interface UseTopologyReturn {
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
  isConnected: boolean;
  isLoading: boolean;
  pollCount: number;
  error: string | null;
  deviceAnimations: Map<string, 'new' | 'removing'>;
  pinnedDeviceIds: Set<string>;
}

export function useTopology(): UseTopologyReturn {
  const [l2Topology, setL2Topology] = useState<L2Topology | null>(null);
  const [l3Topology, setL3Topology] = useState<L3Topology | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('l2');
  const [selectedDevice, setSelectedDevice] = useState<Device | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pollCount, setPollCount] = useState(0);
  const [drillDown, setDrillDown] = useState<DrillDownState>({
    path: [],
    currentDeviceId: null,
    currentVlanId: null,
  });

  // Device change animation tracking
  const [deviceAnimations, setDeviceAnimations] = useState<Map<string, 'new' | 'removing'>>(new Map());
  const [removingDevices, setRemovingDevices] = useState<Device[]>([]);
  const [removingEdges, setRemovingEdges] = useState<import('../types/topology').Edge[]>([]);
  const prevL2NodeIdsRef = useRef<Set<string> | null>(null);
  const animationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch initial topology
  const fetchTopology = useCallback(async () => {
    try {
      const [l2Res, l3Res] = await Promise.all([
        fetch('/api/topology/l2'),
        fetch('/api/topology/l3'),
      ]);
      if (l2Res.ok) {
        const l2Data = await l2Res.json() as L2Topology;
        setL2Topology(l2Data);
        // Seed the previous node IDs from initial fetch (no animations on first load)
        prevL2NodeIdsRef.current = new Set(l2Data.nodes.map((n: Device) => n.id));
      }
      if (l3Res.ok) {
        const l3Data = await l3Res.json();
        setL3Topology(l3Data);
      }
      setError(null);
    } catch (_e) {
      setError('Failed to fetch topology');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTopology();
  }, [fetchTopology]);

  // Handle WebSocket events — detect new/removed devices
  const handleWSEvent = useCallback((event: WSEvent) => {
    if (event.type === 'topology_update') {
      const data = event.data as { l2?: L2Topology; l3?: L3Topology };

      if (data.l2) {
        const newTopo = data.l2;
        const newIds = new Set(newTopo.nodes.map(n => n.id));
        const oldIds = prevL2NodeIdsRef.current;

        if (oldIds) {
          const addedIds: string[] = [];
          const removedIds: string[] = [];

          for (const id of newIds) {
            if (!oldIds.has(id)) addedIds.push(id);
          }
          for (const id of oldIds) {
            if (!newIds.has(id)) removedIds.push(id);
          }

          if (addedIds.length > 0 || removedIds.length > 0) {
            // Clear any pending animation timer
            if (animationTimerRef.current) {
              clearTimeout(animationTimerRef.current);
            }

            // Build animation map
            const anims = new Map<string, 'new' | 'removing'>();
            for (const id of addedIds) anims.set(id, 'new');
            for (const id of removedIds) anims.set(id, 'removing');
            setDeviceAnimations(anims);

            // For removing devices, we need to keep them in the topology temporarily.
            // Look them up from the previous topology state (via the setter's prev value).
            if (removedIds.length > 0) {
              setL2Topology(prev => {
                if (!prev) return newTopo;
                const removedSet = new Set(removedIds);
                const devicesToKeep = prev.nodes.filter(d => removedSet.has(d.id));
                const edgesToKeep = prev.edges.filter(
                  e => removedSet.has(e.source) || removedSet.has(e.target),
                );
                setRemovingDevices(devicesToKeep);
                setRemovingEdges(edgesToKeep);
                return newTopo;
              });
            } else {
              setL2Topology(newTopo);
              setRemovingDevices([]);
              setRemovingEdges([]);
            }

            // After 3 seconds, clear animations and remove the "removing" nodes
            animationTimerRef.current = setTimeout(() => {
              setDeviceAnimations(new Map());
              setRemovingDevices([]);
              setRemovingEdges([]);
              animationTimerRef.current = null;
            }, 3000);
          } else {
            // No changes in device set, just update topology
            setL2Topology(newTopo);
          }
        } else {
          // First WS update after initial fetch had no data
          setL2Topology(newTopo);
        }

        prevL2NodeIdsRef.current = newIds;
      }

      if (data.l3) setL3Topology(data.l3);
      setPollCount(prev => prev + 1);
    }
  }, []);

  const wsUrl = `ws://${window.location.host}/ws/topology`;
  const { isConnected } = useWebSocket({ url: wsUrl, onEvent: handleWSEvent });

  // Cleanup animation timer on unmount
  useEffect(() => {
    return () => {
      if (animationTimerRef.current) clearTimeout(animationTimerRef.current);
    };
  }, []);

  // Merge "removing" devices into the topology so they remain visible during animation
  const mergedL2Topology = useMemo<L2Topology | null>(() => {
    if (!l2Topology) return null;
    if (removingDevices.length === 0) return l2Topology;

    const existingIds = new Set(l2Topology.nodes.map(n => n.id));
    const extraNodes = removingDevices.filter(d => !existingIds.has(d.id));

    const existingEdgeIds = new Set(l2Topology.edges.map(e => e.id));
    const extraEdges = removingEdges.filter(e => !existingEdgeIds.has(e.id));

    return {
      nodes: [...l2Topology.nodes, ...extraNodes],
      edges: [...l2Topology.edges, ...extraEdges],
    };
  }, [l2Topology, removingDevices, removingEdges]);

  // Pinned device IDs = devices with animations (always need to be visible)
  const pinnedDeviceIds = useMemo<Set<string>>(() => {
    const ids = new Set<string>();
    for (const [id] of deviceAnimations) ids.add(id);
    return ids;
  }, [deviceAnimations]);

  // Drill-down navigation
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

  return {
    l2Topology: mergedL2Topology,
    l3Topology,
    viewMode,
    setViewMode,
    selectedDevice,
    setSelectedDevice,
    drillDown,
    drillInto,
    drillBack,
    drillReset,
    isConnected,
    isLoading,
    pollCount,
    error,
    deviceAnimations,
    pinnedDeviceIds,
  };
}
