import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { apiGet, setMutationToken, subscribeApiEvents } from "@/lib/api";
import { toActionableError, type ActionableError } from "@/lib/errors";
import type { Capabilities } from "@/lib/types";

export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  apiError: ActionableError | null;
  refresh: () => void;
}

export type ConnectionState = "online" | "offline" | "reconnecting";

const RECONNECT_TIMEOUT_MS = 10_000;

interface DeskState {
  capabilities: Capabilities | null;
  capabilityError: string | null;
  connection: ConnectionState;
  /** Set after the server rejected a mutation session; cleared when the operator dismisses it. */
  sessionRenewed: boolean;
  /** Increments after every successful reconnect/renewal so read views refetch. */
  generation: number;
  reconnect: () => Promise<boolean>;
  dismissSessionNotice: () => void;
}

const DeskContext = createContext<DeskState>({
  capabilities: null,
  capabilityError: null,
  connection: "online",
  sessionRenewed: false,
  generation: 0,
  reconnect: async () => false,
  dismissSessionNotice: () => undefined,
});

export function useResource<T>(path: string | null): Resource<T> {
  const { generation } = useContext(DeskContext);
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [apiError, setApiError] = useState<ActionableError | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      setApiError(null);
      return;
    }
    let active = true;
    setData(null);
    setLoading(true);
    setApiError(null);
    apiGet<T>(path)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((cause: unknown) => {
        if (active) setApiError(toActionableError(cause));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, version, generation]);

  return useMemo(
    () => ({
      data,
      loading,
      error: apiError?.message ?? null,
      apiError,
      refresh: () => setVersion((current) => current + 1),
    }),
    [data, loading, apiError],
  );
}

export function DeskProvider({ children }: { children: ReactNode }) {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("online");
  const [sessionRenewed, setSessionRenewed] = useState(false);
  const [generation, setGeneration] = useState(0);
  const mounted = useRef(true);
  const inflight = useRef<Promise<boolean> | null>(null);

  // Read-only renewal: a fresh capabilities GET rotates the session cookie and mutation token. Never resubmits.
  const loadCapabilities = useCallback((fresh = false): Promise<boolean> => {
    // An explicit reconnect never waits on a check that started before the connection dropped.
    if (inflight.current && !fresh) return inflight.current;
    const attempt = apiGet<Capabilities>("/api/capabilities", fresh ? { timeoutMs: RECONNECT_TIMEOUT_MS } : {})
      .then((value) => {
        if (!mounted.current) return false;
        setCapabilities(value);
        setCapabilityError(null);
        setMutationToken(value.mutation_token);
        // Background checks recover only via the epoch-gated connection-ok event.
        if (fresh) setConnection("online");
        return true;
      })
      .catch((cause: unknown) => {
        if (!mounted.current) return false;
        setMutationToken(null);
        setCapabilityError(toActionableError(cause, "Capabilities unavailable.").message);
        return false;
      })
      .finally(() => {
        if (inflight.current === attempt) inflight.current = null;
      });
    inflight.current = attempt;
    return attempt;
  }, []);

  const reconnect = useCallback(async () => {
    setConnection("reconnecting");
    const ok = await loadCapabilities(true);
    if (!mounted.current) return ok;
    if (ok) setGeneration((current) => current + 1);
    else setConnection("offline");
    return ok;
  }, [loadCapabilities]);

  useEffect(() => {
    mounted.current = true;
    void loadCapabilities();
    const unsubscribe = subscribeApiEvents((event) => {
      if (event === "connection-lost") setConnection("offline");
      if (event === "connection-ok") setConnection((current) => (current === "offline" ? "online" : current));
      if (event === "session-expired") {
        setSessionRenewed(true);
        void loadCapabilities();
      }
    });
    return () => {
      mounted.current = false;
      unsubscribe();
      setMutationToken(null);
    };
  }, [loadCapabilities]);

  const dismissSessionNotice = useCallback(() => setSessionRenewed(false), []);
  const value = useMemo(
    () => ({ capabilities, capabilityError, connection, sessionRenewed, generation, reconnect, dismissSessionNotice }),
    [capabilities, capabilityError, connection, sessionRenewed, generation, reconnect, dismissSessionNotice],
  );
  return <DeskContext.Provider value={value}>{children}</DeskContext.Provider>;
}

export function useDesk() {
  return useContext(DeskContext);
}
