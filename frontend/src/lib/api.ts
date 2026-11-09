import type {
  ApiErrorCode,
  ApiErrorShape,
  ApiRetryPolicy,
  Operation,
  OperationAcceptRequest,
  OperationCancelRequest,
  OperationPreview,
  OperationPreviewRequest,
} from "@/lib/types";
import { matchesOperationIdentity, type ExpectedOperationIdentity } from "@/lib/operation-identity";

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
  "inspection-timeout",
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
  retryAfterSeconds?: number | string | null;
}

// Mirrors the server bound; a hint outside it is ignored rather than trusted.
const MAX_RETRY_AFTER_SECONDS = 300;

function boundedRetryAfter(status: number, value: unknown): number | null {
  if (status !== 429 && status !== 503) return null;
  const seconds = typeof value === "string" && /^\d{1,3}$/.test(value.trim()) ? Number(value.trim()) : value;
  return typeof seconds === "number" && Number.isInteger(seconds) && seconds >= 1 && seconds <= MAX_RETRY_AFTER_SECONDS ? seconds : null;
}

function retryAfterHeader(response: Response): string | null {
  return typeof response.headers?.get === "function" ? response.headers.get("Retry-After") : null;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | null;
  readonly refreshRequired: boolean;
  readonly retryPolicy: ApiRetryPolicy;
  readonly subjectId: string | null;
  readonly requestId: string | null;
  readonly currentHead: string | null;
  /** Advisory wait from a 429/503 denial; never a promise that a retry will succeed. */
  readonly retryAfterSeconds: number | null;

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
    this.retryAfterSeconds = boundedRetryAfter(status, options.retryAfterSeconds);
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

export interface ApiGetOptions {
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function apiGet<T>(path: string, options: ApiGetOptions = {}): Promise<T> {
  if (options.signal?.aborted) throw new DOMException("Read cancelled.", "AbortError");
  if (!options.timeoutMs && !options.signal) return request<T>(path, { method: "GET" });
  const controller = new AbortController();
  const cancel = () => controller.abort();
  options.signal?.addEventListener("abort", cancel, { once: true });
  const timer = options.timeoutMs ? setTimeout(cancel, options.timeoutMs) : undefined;
  try {
    return await request<T>(path, { method: "GET", signal: controller.signal }, options.signal);
  } finally {
    if (timer !== undefined) clearTimeout(timer);
    options.signal?.removeEventListener("abort", cancel);
  }
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

export function previewOperation(request: OperationPreviewRequest): Promise<OperationPreview> {
  return apiPost<OperationPreview>("/api/operations/preview", request);
}

export function requireMutationOperationReceipt(
  value: unknown,
  expected: ExpectedOperationIdentity,
  requestId: string,
  status = 202,
): Operation {
  if (!matchesOperationIdentity(value, expected)) {
    throw new ApiError("The operation receipt is incomplete or inconsistent; inspect durable status.", status, {
      retryPolicy: "inspect-status",
      requestId,
    });
  }
  return value;
}

export async function acceptOperation(request: OperationAcceptRequest): Promise<Operation> {
  const receipt = await apiPost<unknown>("/api/operations", request);
  return requireMutationOperationReceipt(receipt, {
    requestId: request.request_id,
    action: request.action,
    subjectId: request.subject_id,
  }, request.request_id);
}

function operationPath(operationId: string): string {
  if (!/^[a-f0-9]{32}$/.test(operationId)) throw new Error("Invalid operation ID.");
  return `/api/operations/${operationId}`;
}

export async function getOperation(operationId: string, options: ApiGetOptions = {}): Promise<Operation> {
  return apiGet<Operation>(operationPath(operationId), options);
}

export async function cancelOperation(operationId: string, request: OperationCancelRequest): Promise<Operation> {
  const receipt = await apiPost<unknown>(`${operationPath(operationId)}/cancel`, request);
  return requireMutationOperationReceipt(receipt, { operationId }, request.request_id, 200);
}

export function isExpiredConfirmation(cause: unknown): boolean {
  return cause instanceof ApiError && cause.status === 410 && cause.code === "expired-confirmation";
}

/**
 * True only when the server proved the request was refused before durable acceptance,
 * so its pending identity can be released. Capacity denials must echo the same request.
 */
export function isPreAdmissionDenial(cause: unknown, requestId: string): boolean {
  if (isExpiredConfirmation(cause)) return true;
  return cause instanceof ApiError && cause.status === 429 && cause.code === "capacity-denied" && cause.requestId === requestId;
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

export async function apiDelete<T = void>(path: string): Promise<T | undefined> {
  const headers = new Headers();
  if (mutationToken) headers.set("X-CSRF-Token", mutationToken);
  return request<T | undefined>(path, { method: "DELETE", headers });
}

function abortable<T>(promise: Promise<T>, signal: AbortSignal | null | undefined): Promise<T> {
  if (!signal) return promise;
  return new Promise<T>((resolve, reject) => {
    const abort = () => reject(new DOMException("Read cancelled.", "AbortError"));
    if (signal.aborted) {
      void promise.catch(() => undefined);
      abort();
      return;
    }
    signal.addEventListener("abort", abort, { once: true });
    promise.then(
      (value) => { signal.removeEventListener("abort", abort); resolve(value); },
      (cause: unknown) => { signal.removeEventListener("abort", abort); reject(cause); },
    );
  });
}

async function request<T>(path: string, init: RequestInit, cancelledBy?: AbortSignal): Promise<T> {
  if (!path.startsWith("/api/")) {
    throw new Error("API paths must stay under /api.");
  }
  const mutation = (init.method ?? "GET") !== "GET";
  const startedEpoch = connectionEpoch;
  let response: Response;
  let payload: unknown;
  try {
    response = await abortable(fetch(path, {
      ...init,
      mode: "same-origin",
      credentials: "same-origin",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...Object.fromEntries(new Headers(init.headers).entries()),
      },
    }), init.signal);
    if (startedEpoch === connectionEpoch) emit("connection-ok");
    if (response.status === 204 && init.method === "DELETE") return undefined as T;
    try {
      payload = await abortable(response.json(), init.signal);
    } catch (cause) {
      if (init.signal?.aborted) throw cause;
      if (response.ok) {
        throw new ApiError(
          mutation
            ? "The response could not be read; the request outcome is unknown."
            : "The response could not be read; retry the observation.",
          response.status,
          { retryPolicy: mutation ? "inspect-status" : "retry-read-only" },
        );
      }
      payload = null;
    }
    if (response.ok && mutation && payload === null) {
      throw new ApiError("The response was empty; the request outcome is unknown.", response.status, { retryPolicy: "inspect-status" });
    }
    const hasErrorObject = payload !== null && typeof payload === "object" && !Array.isArray(payload);
    const shape = hasErrorObject ? payload as ApiErrorShape : null;
    const hasErrorEnvelope = shape !== null && typeof shape.code === "string" && API_ERROR_CODES.has(shape.code)
      && typeof shape.retry_policy === "string" && RETRY_POLICIES.has(shape.retry_policy);
    if (!response.ok && !hasErrorEnvelope && (mutation || response.status >= 500 || response.status === 429)) {
      const detail = errorMessage(shape);
      throw new ApiError(
        detail !== "Request failed." ? detail : mutation
          ? "The error response could not be read; inspect the request outcome."
          : "The error response could not be read; retry the observation.",
        response.status,
        { retryPolicy: mutation ? "inspect-status" : "retry-read-only" },
      );
    }
  } catch (cause) {
    if (cancelledBy?.aborted) throw cause;
    if (cause instanceof ApiError) throw cause;
    connectionEpoch += 1;
    emit("connection-lost");
    // A lost mutation may have reached the server; only durable status can tell, so never auto-retry it.
    throw mutation
      ? new ApiError("Connection to the local desk was lost; the request outcome is unknown.", 0, { retryPolicy: "inspect-status" })
      : new ApiError("The local desk server is unreachable.", 0, { retryPolicy: "retry-read-only" });
  }
  if (!response.ok) {
    const shape = payload as ApiErrorShape | null;
    const error = new ApiError(errorMessage(shape), response.status, {
      ...errorEnvelope(shape),
      retryAfterSeconds: shape?.retry_after_seconds ?? retryAfterHeader(response),
    });
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
  if (!payload || typeof payload !== "object" || Array.isArray(payload) || !("detail" in payload)) return "Request failed.";
  if (typeof payload.detail === "string") return payload.detail;
  if (Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => item?.message)
      .filter((message): message is string => typeof message === "string" && message.length > 0)
      .join(" ") || "Request validation failed.";
  }
  return "Request failed.";
}
