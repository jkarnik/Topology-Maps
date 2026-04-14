import { useState, useCallback } from 'react';

export interface PendingChange {
  type: 'connect' | 'disconnect';
  sourceDevice: string;
  targetDevice: string;
  sourcePort?: string;
  targetPort?: string;
  edgeId?: string;
}

export interface UseEditModeReturn {
  editMode: boolean;
  toggleEditMode: () => void;
  pendingChange: PendingChange | null;
  isApplying: boolean;
  createConnection: (source: string, target: string, sourcePort?: string, targetPort?: string) => void;
  disconnectEdge: (edgeId: string, source: string, target: string) => void;
  applyChange: () => Promise<void>;
  cancelChange: () => void;
}

export function useEditMode(): UseEditModeReturn {
  const [editMode, setEditMode] = useState(false);
  const [pendingChange, setPendingChange] = useState<PendingChange | null>(null);
  const [isApplying, setIsApplying] = useState(false);

  const toggleEditMode = useCallback(() => {
    setEditMode((prev) => {
      if (prev) {
        // Exiting edit mode — clear any pending change
        setPendingChange(null);
      }
      return !prev;
    });
  }, []);

  const createConnection = useCallback(
    (source: string, target: string, sourcePort?: string, targetPort?: string) => {
      setPendingChange({
        type: 'connect',
        sourceDevice: source,
        targetDevice: target,
        sourcePort,
        targetPort,
      });
    },
    [],
  );

  const disconnectEdge = useCallback(
    (edgeId: string, source: string, target: string) => {
      setPendingChange({
        type: 'disconnect',
        sourceDevice: source,
        targetDevice: target,
        edgeId,
      });
    },
    [],
  );

  const applyChange = useCallback(async () => {
    if (!pendingChange) return;

    setIsApplying(true);
    try {
      const body =
        pendingChange.type === 'connect'
          ? {
              action: 'create',
              source: pendingChange.sourceDevice,
              target: pendingChange.targetDevice,
              source_port: pendingChange.sourcePort ?? null,
              target_port: pendingChange.targetPort ?? null,
            }
          : {
              action: 'delete',
              edge_id: pendingChange.edgeId,
              source: pendingChange.sourceDevice,
              target: pendingChange.targetDevice,
            };

      const res = await fetch('/api/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        const msg = (errData as { error?: string } | null)?.error ?? `Request failed (${res.status})`;
        throw new Error(msg);
      }

      // Success — clear pending change
      setPendingChange(null);
    } catch (err) {
      // Surface error to console; a future iteration could push to a toast
      console.error('[useEditMode] applyChange failed:', err);
    } finally {
      setIsApplying(false);
    }
  }, [pendingChange]);

  const cancelChange = useCallback(() => {
    setPendingChange(null);
  }, []);

  return {
    editMode,
    toggleEditMode,
    pendingChange,
    isApplying,
    createConnection,
    disconnectEdge,
    applyChange,
    cancelChange,
  };
}
