import type { ApiErrorShape } from "@/lib/types";

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
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
    throw new ApiError(errorMessage(payload as ApiErrorShape | null), response.status);
  }
  return payload as T;
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
