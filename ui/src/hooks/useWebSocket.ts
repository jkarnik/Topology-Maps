import { useEffect, useRef, useCallback, useState } from 'react';
import { WSEvent } from '../types/topology';

interface UseWebSocketOptions {
  url: string;
  onEvent?: (event: WSEvent) => void;
  reconnectInterval?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastEvent: WSEvent | null;
}

export function useWebSocket({ url, onEvent, reconnectInterval = 3000 }: UseWebSocketOptions): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url);

      ws.onopen = () => {
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const parsed: WSEvent = JSON.parse(event.data);
          setLastEvent(parsed);
          onEvent?.(parsed);
        } catch {
          // ignore malformed messages
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        wsRef.current = null;
        // Auto-reconnect
        reconnectTimerRef.current = window.setTimeout(connect, reconnectInterval);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch {
      reconnectTimerRef.current = window.setTimeout(connect, reconnectInterval);
    }
  }, [url, onEvent, reconnectInterval]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { isConnected, lastEvent };
}
