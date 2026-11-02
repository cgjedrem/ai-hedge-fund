import type { ApiErrorCode, ApiErrorShape, ApiRetryPolicy } from "@/lib/types";

const API_ERROR_CODES: ReadonlySet<string> = new Set<ApiErrorCode>([
  "invalid-request",
  "capability-denied",
  "protected-root",
  "read-only",
  "broker-not-web-supported",
  "not-found",
  "stale-preview",
  "request-conflict",
  "writer-conflict",
  "ownership-unknown",
  "halted",
  "replay-corrupt",
  "reconciliation-required",
  "readiness-denied",
  "unsupported-filesystem",
  "private-storage-unverified",
  "expired-confirmation",
  "capacity-denied",
  "budget-exhausted",
  "payload-too-large",
  "observation-conflict",
  "assets-unavailable",
  "internal-error",
]);
const RETRY_POLICIES: ReadonlySet<string> = new Set<ApiRetryPolicy>([
  "none",
  "review-again",
  "reload",
  "inspect-status",
  "retry-later",
  "retry-read-only",
]);

// Identity echoes are opaque bounded tokens; anything else is dropped rather than rendered.
const SAFE_IDENTITY = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,180}$/;

export interface ApiErrorOptions {
  code?: ApiErrorCode | null;
  refreshRequired?: boolean;
  retryPolicy?: ApiRetryPolicy;
  subjectId?: string | null;
  requestId?: string | null;
  currentHead?: string | null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | null;
  readonly refreshRequired: boolean;
  readonly retryPolicy: ApiRetryPolicy;
  readonly subjectId: string | null;
  readonly requestId: string | null;
  readonly currentHead: string | null;

  constructor(message: string, status: number, options: ApiErrorOptions = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options.code ?? null;
    this.refreshRequired = options.refreshRequired ?? false;
    this.retryPolicy = options.retryPolicy ?? "none";
    this.subjectId = safeIdentity(options.subjectId);
    this.requestId = safeIdentity(options.requestId);
    this.currentHead = safeIdentity(options.currentHead);
  }

  /** Status 0 means the server was never reached or the response was lost. */
  get offline(): boolean {
    return this.status === 0;
  }
}

export type ApiEvent = "connection-lost" | "connection-ok" | "session-expired";
type ApiListener = (event: ApiEvent) => void;
const listeners = new Set<ApiListener>();

export function subscribeApiEvents(listener: ApiListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function emit(event: ApiEvent): void {
  for (const listener of [...listeners]) listener(event);
}

function safeIdentity(value: unknown): string | null {
  return typeof value === "string" && SAFE_IDENTITY.test(value) ? value : null;
}

let mutationToken: string | null = null;
// Bumped on every lost connection; only a request started after the latest loss may report recovery.
let connectionEpoch = 0;

export function setMutationToken(token: string | null): void {
  mutationToken = token;
}

export async function apiGet<T>(path: string, options: { timeoutMs?: number } = {}): Promise<T> {
  // A bounded read fails as an unreachable server instead of hanging; only read-only callers opt in.
  return request<T>(path, options.timeoutMs ? { method: "GET", signal: AbortSignal.timeout(options.timeoutMs) } : { method: "GET" });
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (mutationToken) headers.set("X-CSRF-Token", mutationToken);
  return request<T>(path, {
    method: "POST",
    headers,
    body: JSON.stringify(body ?? {}),
  });
}

export async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (mutationToken) headers.set("X-CSRF-Token", mutationToken);
  return request<T>(path, {
    method: "PUT",
    headers,
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T>(path: string): Promise<T> {
  const headers = new Headers();
  if (mutationToken) headers.set("X-CSRF-Token", mutationToken);
  return request<T>(path, { method: "DELETE", headers });
}

async function request<T>(path: string, init: RequestInit): Promise<T> {
  if (!path.startsWith("/api/")) {
    throw new Error("API paths must stay under /api.");
  }
  const mutation = (init.method ?? "GET") !== "GET";
  const startedEpoch = connectionEpoch;
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      mode: "same-origin",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...Object.fromEntries(new Headers(init.headers).entries()),
      },
    });
  } catch {
    connectionEpoch += 1;
    emit("connection-lost");
    // A lost mutation may have reached the server; only durable status can tell, so never auto-retry it.
    throw mutation
      ? new ApiError("Connection to the local desk was lost; the request outcome is unknown.", 0, { retryPolicy: "inspect-status" })
      : new ApiError("The local desk server is unreachable.", 0, { retryPolicy: "retry-read-only" });
  }
  if (startedEpoch === connectionEpoch) emit("connection-ok");
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const shape = payload as ApiErrorShape | null;
    const error = new ApiError(errorMessage(shape), response.status, errorEnvelope(shape));
    if (mutation && response.status === 403 && error.retryPolicy === "reload") emit("session-expired");
    throw error;
  }
  return payload as T;
}

function errorEnvelope(payload: ApiErrorShape | null) {
  if (!payload || typeof payload !== "object") return {};
  const code = typeof payload.code === "string" && API_ERROR_CODES.has(payload.code) ? payload.code : null;
  const retryPolicy = typeof payload.retry_policy === "string" && RETRY_POLICIES.has(payload.retry_policy)
    ? payload.retry_policy
    : "none";
  return {
    code,
    refreshRequired: payload.refresh_required === true,
    retryPolicy,
    subjectId: payload.subject_id,
    requestId: payload.request_id,
    currentHead: payload.current_head,
  };
}

function errorMessage(payload: ApiErrorShape | null): string {
  if (!payload || !("detail" in payload)) return "Request failed.";
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item.message)
      .filter((message): message is string => Boolean(message))
      .join(" ") || "Request validation failed.";
  }
  return "Request failed.";
}
