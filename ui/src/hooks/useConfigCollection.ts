import { useEffect, useState } from 'react';
import type { ConfigWsEvent } from '../types/config';

export function useConfigCollection(orgId: string | null) {
  const [lastEvent, setLastEvent] = useState<ConfigWsEvent | null>(null);
  const [connected, setConnected] = useState(false);

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
      } catch { /* ignore */ }
    };
    return () => ws.close();
  }, [orgId]);

  return { connected, lastEvent };
}
