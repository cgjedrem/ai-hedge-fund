import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { apiGet, setMutationToken } from "@/lib/api";
import type { Capabilities } from "@/lib/types";

export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refresh: () => void;
}

export function useResource<T>(path: string | null): Resource<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState<string | null>(null);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    if (!path) {
      setData(null);
      setLoading(false);
      setError(null);
      return;
    }
    let active = true;
    setData(null);
    setLoading(true);
    setError(null);
    apiGet<T>(path)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((cause: unknown) => {
        if (active) setError(cause instanceof Error ? cause.message : "Request failed.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [path, version]);

  return useMemo(
    () => ({ data, loading, error, refresh: () => setVersion((current) => current + 1) }),
    [data, loading, error],
  );
}

const DeskContext = createContext<{
  capabilities: Capabilities | null;
  capabilityError: string | null;
}>({ capabilities: null, capabilityError: null });

export function DeskProvider({ children }: { children: ReactNode }) {
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [capabilityError, setCapabilityError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    apiGet<Capabilities>("/api/capabilities")
      .then((value) => {
        if (active) {
          setCapabilities(value);
          setMutationToken(value.mutation_token);
        }
      })
      .catch((cause: unknown) => {
        if (active) setCapabilityError(cause instanceof Error ? cause.message : "Capabilities unavailable.");
      });
    return () => {
      active = false;
      setMutationToken(null);
    };
  }, []);

  const value = useMemo(() => ({ capabilities, capabilityError }), [capabilities, capabilityError]);
  return <DeskContext.Provider value={value}>{children}</DeskContext.Provider>;
}

export function useDesk() {
  return useContext(DeskContext);
}
