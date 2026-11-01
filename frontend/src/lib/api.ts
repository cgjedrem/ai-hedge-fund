import type { ApiErrorCode, ApiErrorShape, ApiRetryPolicy } from "@/lib/types";

const API_ERROR_CODES: ReadonlySet<string> = new Set<ApiErrorCode>([
  "invalid-request",
  "capability-denied",
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
  "expired-confirmation",
  "capacity-denied",
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

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode | null;
  readonly refreshRequired: boolean;
  readonly retryPolicy: ApiRetryPolicy;

  constructor(
    message: string,
    status: number,
    options: { code?: ApiErrorCode | null; refreshRequired?: boolean; retryPolicy?: ApiRetryPolicy } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = options.code ?? null;
    this.refreshRequired = options.refreshRequired ?? false;
    this.retryPolicy = options.retryPolicy ?? "none";
  }
}

let mutationToken: string | null = null;

export function setMutationToken(token: string | null): void {
  mutationToken = token;
}

export async function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
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
  const response = await fetch(path, {
    ...init,
    mode: "same-origin",
    credentials: "same-origin",
    cache: "no-store",
    headers: {
      Accept: "application/json",
      ...Object.fromEntries(new Headers(init.headers).entries()),
    },
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const shape = payload as ApiErrorShape | null;
    throw new ApiError(errorMessage(shape), response.status, errorEnvelope(shape));
  }
  return payload as T;
}

function errorEnvelope(payload: ApiErrorShape | null) {
  if (!payload || typeof payload !== "object") return {};
  const code = typeof payload.code === "string" && API_ERROR_CODES.has(payload.code) ? payload.code : null;
  const retryPolicy = typeof payload.retry_policy === "string" && RETRY_POLICIES.has(payload.retry_policy)
    ? payload.retry_policy
    : "none";
  return { code, refreshRequired: payload.refresh_required === true, retryPolicy };
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
