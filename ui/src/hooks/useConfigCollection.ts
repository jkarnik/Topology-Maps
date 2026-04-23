import { useEffect, useState } from 'react';
import type { ConfigWsEvent } from '../types/config';

export interface SweepProgress {
  completed: number;
  total: number;
  startedAt: number;
}

export function useConfigCollection(orgId: string | null) {
  const [lastEvent, setLastEvent] = useState<ConfigWsEvent | null>(null);
  const [connected, setConnected] = useState(false);
  const [sweepProgress, setSweepProgress] = useState<SweepProgress | null>(null);

  useEffect(() => {
    if (!orgId) { setConnected(false); return; }
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${proto}//${window.location.host}/ws/config?org_id=${orgId}`;
    const ws = new WebSocket(url);
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (evt) => {
      try {
        const data: ConfigWsEvent = JSON.parse(evt.data);
        setLastEvent(data);
        if (data.type === 'sweep.started') {
          setSweepProgress({ completed: 0, total: data.total_calls, startedAt: Date.now() });
        } else if (data.type === 'sweep.progress') {
          setSweepProgress(prev => ({
            completed: data.completed_calls,
            total: data.total_calls,
            startedAt: prev?.startedAt ?? Date.now(),
          }));
        } else if (data.type === 'sweep.completed' || data.type === 'sweep.failed') {
          setSweepProgress(null);
        }
      } catch { /* ignore */ }
    };
    return () => ws.close();
  }, [orgId]);

  return { connected, lastEvent, sweepProgress };
}
