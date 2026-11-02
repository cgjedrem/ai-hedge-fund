import { useCallback, useEffect, useRef, useState } from "react";

import {
  forgetPendingOperation,
  forgetSavedOperationIdentity,
  readPendingOperations,
  readSavedOperationIdentities,
  rememberPendingOperation,
  saveOperationIdentity,
  type PendingOperation,
  type SavedOperationIdentity,
  type SavedOperationObservation,
} from "@/lib/pending-operations";

interface PendingSnapshot {
  items: PendingOperation[];
  saved: SavedOperationIdentity[];
  error: string | null;
}

function snapshot(): PendingSnapshot {
  try {
    return { items: readPendingOperations(), saved: readSavedOperationIdentities(), error: null };
  } catch (cause) {
    return { items: [], saved: [], error: cause instanceof Error ? cause.message : "Pending operation storage is unavailable." };
  }
}

export function usePendingOperations(kind: "backtest" | "paper", subjectId?: string) {
  const [state, setState] = useState<PendingSnapshot>(snapshot);
  const [observed, setObserved] = useState<Record<string, {
    operationId: string;
    action: string;
    subjectId: string;
    scope: number;
    status: SavedOperationObservation;
  }>>({});
  const scope = `${kind}\0${subjectId ?? ""}`;
  const scopeRef = useRef({ key: scope, version: 0 });
  if (scopeRef.current.key !== scope) {
    scopeRef.current = { key: scope, version: scopeRef.current.version + 1 };
  }
  const scopeVersion = scopeRef.current.version;
  const refresh = useCallback(() => {
    const next = snapshot();
    setState(next);
    setObserved((current) => Object.fromEntries(
      Object.entries(current).filter(([requestId]) => next.saved.some((item) => item.requestId === requestId)),
    ));
  }, []);

  useEffect(() => {
    const changed = (event: StorageEvent) => {
      if (event.key === null || event.key.startsWith("aihf.pending-operation.") || event.key.startsWith("aihf.operation-identity.")) refresh();
    };
    window.addEventListener("storage", changed);
    return () => window.removeEventListener("storage", changed);
  }, [refresh]);

  const remember = useCallback((item: PendingOperation): boolean => {
    try {
      const current = readPendingOperations();
      const saved = readSavedOperationIdentities();
      const unresolved = current.some((existing) =>
        item.action === "backtest"
          ? existing.action === "backtest"
          : existing.action !== "backtest" && existing.subjectId === item.subjectId,
      );
      const savedUnverified = saved.some((existing) => {
        const sameSurface = item.action === "backtest"
          ? existing.action === "backtest"
          : existing.action !== "backtest" && existing.subjectId === item.subjectId;
        if (!sameSurface) return false;
        const result = observed[existing.requestId];
        return !result || result.scope !== scopeVersion || result.operationId !== existing.operationId
          || result.action !== existing.action || result.subjectId !== existing.subjectId || result.status !== "terminal";
      });
      if (unresolved || savedUnverified) {
        setState({ items: current, saved, error: null });
        return false;
      }
      rememberPendingOperation(item);
      refresh();
      return true;
    } catch (cause) {
      setState((current) => ({ ...current, error: cause instanceof Error ? cause.message : "Pending operation storage is unavailable." }));
      return false;
    }
  }, [observed, refresh, scopeVersion]);

  const save = useCallback((item: PendingOperation, operationId: string): boolean => {
    try {
      saveOperationIdentity(item, operationId);
      refresh();
      return true;
    } catch (cause) {
      setState((current) => ({ ...current, error: cause instanceof Error ? cause.message : "Operation identity storage is unavailable." }));
      return false;
    }
  }, [refresh]);

  const forgetSaved = useCallback((item: SavedOperationIdentity): boolean => {
    try {
      forgetSavedOperationIdentity(item);
      refresh();
      return true;
    } catch (cause) {
      setState((current) => ({ ...current, error: cause instanceof Error ? cause.message : "Operation identity storage is unavailable." }));
      return false;
    }
  }, [refresh]);

  const observe = useCallback((item: SavedOperationIdentity, status: SavedOperationObservation) => {
    setObserved((current) => {
      const previous = current[item.requestId];
      if (previous?.operationId === item.operationId && previous.action === item.action
          && previous.subjectId === item.subjectId && previous.scope === scopeVersion && previous.status === status) return current;
      return {
        ...current,
        [item.requestId]: {
          operationId: item.operationId, action: item.action, subjectId: item.subjectId, scope: scopeVersion, status,
        },
      };
    });
  }, [scopeVersion]);

  const forget = useCallback((item: PendingOperation): boolean => {
    try {
      forgetPendingOperation(item);
      refresh();
      return true;
    } catch (cause) {
      setState((current) => ({ ...current, error: cause instanceof Error ? cause.message : "Pending operation storage is unavailable." }));
      return false;
    }
  }, [refresh]);

  const items = state.items.filter((item) =>
    kind === "backtest"
      ? item.action === "backtest"
      : item.action !== "backtest" && item.subjectId === subjectId,
  );
  const saved = state.saved.filter((item) =>
    kind === "backtest"
      ? item.action === "backtest"
      : item.action !== "backtest" && item.subjectId === subjectId,
  );
  const savedBlocked = saved.some((item) => {
    const result = observed[item.requestId];
    return !result || result.scope !== scopeVersion || result.operationId !== item.operationId
      || result.action !== item.action || result.subjectId !== item.subjectId || result.status !== "terminal";
  });
  return {
    items, saved, error: state.error, blocked: Boolean(state.error || items.length || savedBlocked),
    remember, forget, save, forgetSaved, observe, refresh,
  };
}
