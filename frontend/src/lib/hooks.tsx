import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { apiGet, getOperation, setMutationToken, subscribeApiEvents } from "@/lib/api";
import { toActionableError, type ActionableError } from "@/lib/errors";
import type { Capabilities, Operation } from "@/lib/types";

export interface Resource<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  apiError: ActionableError | null;
  refresh: () => void;
}

export type ConnectionState = "online" | "offline" | "reconnecting";

const RECONNECT_TIMEOUT_MS = 10_000;
const OPERATION_POLL_INTERVAL_MS = 1_200;
const OPERATION_READ_TIMEOUT_MS = 10_000;
const OPERATION_READ_RETRIES = 3;
const ACTIVE_OPERATION_STATUSES = new Set(["accepted", "running", "cancel-requested"]);
const OPERATION_STATUSES = new Set([
  ...ACTIVE_OPERATION_STATUSES,
  "completed",
  "failed",
  "interrupted",
  "cancelled",
]);
const OPERATION_STATUS_ORDER: Record<string, number> = {
  accepted: 0,
  running: 1,
  "cancel-requested": 2,
  completed: 3,
  failed: 3,
  interrupted: 3,
  cancelled: 3,
};

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

function operationCursor(value: string): bigint | null {
  const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return null;
  const seconds = Date.parse(`${match[1]}${match[3]}`) / 1_000;
  if (!Number.isFinite(seconds)) return null;
  return BigInt(seconds) * 1_000_000_000n + BigInt((match[2] ?? "").padEnd(9, "0"));
}

function sameOperationIdentity(first: Operation, next: Operation): boolean {
  return first.operation_id === next.operation_id
    && first.request_id === next.request_id
    && first.action === next.action
    && first.subject_id === next.subject_id
    && first.capture_id === next.capture_id
    && first.capture_digest === next.capture_digest
    && first.created_at === next.created_at;
}

export function useOperation(operationId: string | null, expectedSubject?: string): Resource<Operation> {
  const { generation } = useContext(DeskContext);
  const [version, setVersion] = useState(0);
  const key = `${operationId ?? ""}\0${expectedSubject ?? ""}`;
  const latest = useRef<{ key: string; data: Operation; cursor: bigint } | null>(null);
  const [state, setState] = useState<{
    key: string;
    data: Operation | null;
    loading: boolean;
    apiError: ActionableError | null;
  }>({ key: "", data: null, loading: false, apiError: null });
  const refresh = useCallback(() => setVersion((current) => current + 1), []);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    const controller = new AbortController();
    if (latest.current?.key !== key) latest.current = null;
    if (!operationId) {
      setState({ key, data: null, loading: false, apiError: null });
      return;
    }

    setState((current) => ({
      key,
      data: current.key === key ? current.data : null,
      loading: true,
      apiError: null,
    }));
    const poll = async () => {
      try {
        const data = await getOperation(operationId, {
          timeoutMs: OPERATION_READ_TIMEOUT_MS,
          signal: controller.signal,
        });
        if (!active) return;
        failures = 0;
        const previous = latest.current;
        if (
          !data || data.operation_id !== operationId || data.id !== operationId
          || typeof data.subject_id !== "string" || !data.subject_id || data.fund !== data.subject_id
          || typeof data.request_id !== "string" || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(data.request_id)
          || typeof data.action !== "string" || !data.action
          || typeof data.capture_id !== "string" || !/^[a-f0-9]{32}$/.test(data.capture_id)
          || typeof data.capture_digest !== "string" || !/^[a-f0-9]{64}$/.test(data.capture_digest)
          || typeof data.created_at !== "string" || operationCursor(data.created_at) === null
          || (expectedSubject !== undefined && data.subject_id !== expectedSubject)
          || (previous && !sameOperationIdentity(previous.data, data))
        ) {
          throw new Error("Operation status identity is inconsistent.");
        }
        const cursor = typeof data.updated_at === "string" ? operationCursor(data.updated_at) : null;
        if (
          cursor === null || !OPERATION_STATUSES.has(data.status)
          || !Number.isInteger(data.progress) || data.progress < 0 || data.progress > 100
        ) {
          throw new Error("Operation status cursor or progress is invalid.");
        }
        const stateAdvanced = previous && (
          OPERATION_STATUS_ORDER[data.status] > OPERATION_STATUS_ORDER[previous.data.status]
          || data.progress > previous.data.progress
        );
        if (previous && (
          (cursor < previous.cursor && !stateAdvanced)
          || data.progress < previous.data.progress
          || OPERATION_STATUS_ORDER[data.status] < OPERATION_STATUS_ORDER[previous.data.status]
          || (!ACTIVE_OPERATION_STATUSES.has(previous.data.status) && data.status !== previous.data.status)
        )) {
          setState({ key, data: previous.data, loading: false, apiError: null });
          if (ACTIVE_OPERATION_STATUSES.has(previous.data.status)) {
            timer = setTimeout(() => void poll(), OPERATION_POLL_INTERVAL_MS);
          }
          return;
        }
        // A server clock can move backwards; durable status and progress still advance monotonically.
        const highWaterCursor = previous && previous.cursor > cursor ? previous.cursor : cursor;
        latest.current = { key, data, cursor: highWaterCursor };
        setState({ key, data, loading: false, apiError: null });
        if (ACTIVE_OPERATION_STATUSES.has(data.status)) {
          timer = setTimeout(() => void poll(), OPERATION_POLL_INTERVAL_MS);
        }
      } catch (cause) {
        if (!active) return;
        const apiError = toActionableError(cause);
        setState((current) => ({
          key,
          data: current.key === key ? current.data : null,
          loading: false,
          apiError,
        }));
        if (apiError.retryPolicy === "retry-read-only" && failures < OPERATION_READ_RETRIES) {
          timer = setTimeout(() => void poll(), OPERATION_POLL_INTERVAL_MS * 2 ** failures);
          failures += 1;
        }
      }
    };
    void poll();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      controller.abort();
    };
  }, [operationId, expectedSubject, key, generation, version]);

  const matches = state.key === key;
  const data = matches ? state.data : null;
  const apiError = matches ? state.apiError : null;
  return {
    data,
    loading: matches ? state.loading : Boolean(operationId),
    error: apiError?.message ?? null,
    apiError,
    refresh,
  };
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
