import { useState, useEffect, useCallback, useRef } from 'react';

interface SimulationStatus {
  running: boolean;
  remaining_seconds: number;
}

interface UseSimulationReturn {
  isRunning: boolean;
  remainingSeconds: number;
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

export function useSimulation(): UseSimulationReturn {
  const [isRunning, setIsRunning] = useState(false);
  const [remainingSeconds, setRemainingSeconds] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    fetch('/api/simulation/status')
      .then(r => r.json())
      .then((data: SimulationStatus) => {
        setIsRunning(data.running);
        setRemainingSeconds(data.remaining_seconds);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (isRunning && remainingSeconds > 0) {
      timerRef.current = setInterval(() => {
        setRemainingSeconds(prev => {
          if (prev <= 1) {
            setIsRunning(false);
            if (timerRef.current) clearInterval(timerRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [isRunning, remainingSeconds]);

  const start = useCallback(async () => {
    const resp = await fetch('/api/simulation/start', { method: 'POST' });
    if (resp.ok) {
      const data: SimulationStatus = await resp.json();
      setIsRunning(true);
      setRemainingSeconds(data.remaining_seconds);
    }
  }, []);

  const stop = useCallback(async () => {
    const resp = await fetch('/api/simulation/stop', { method: 'POST' });
    if (resp.ok) {
      setIsRunning(false);
      setRemainingSeconds(0);
    }
  }, []);

  return { isRunning, remainingSeconds, start, stop };
}
