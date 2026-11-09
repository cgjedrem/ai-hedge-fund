import { act, cleanup, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { subscribeApiEvents, type ApiEvent } from "@/lib/api";
import { DeskProvider, useDesk, useOperation, useResource } from "@/lib/hooks";
import type { Operation } from "@/lib/types";

const operationId = "a".repeat(32);

function operation(overrides: Partial<Operation> = {}): Operation {
  return {
    operation_id: operationId,
    id: operationId,
    request_id: "synthetic-request",
    action: "backtest",
    subject_id: "synthetic-fund",
    fund: "synthetic-fund",
    capture_id: "b".repeat(32),
    capture_digest: "c".repeat(64),
    status: "running",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:01Z",
    payload: {},
    result: null,
    progress: 10,
    provider: null,
    model: null,
    report_id: null,
    error: null,
    cancel_requested: false,
    status_url: `/api/operations/${operationId}`,
    ...overrides,
  };
}

function response(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

it("polls a selected durable operation read-only and stops at a terminal state", async () => {
  vi.useFakeTimers();
  const fake = vi.fn()
    .mockResolvedValueOnce(response(operation()))
    .mockResolvedValueOnce(response(operation({
      status: "completed",
      progress: 100,
      updated_at: "2026-01-01T00:00:02Z",
    })));
  vi.stubGlobal("fetch", fake);

  const { result } = renderHook(() => useOperation(operationId));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(result.current.data?.status).toBe("running");
  expect(fake).toHaveBeenCalledTimes(1);

  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.status).toBe("completed");
  expect(fake).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
  expect(fake).toHaveBeenCalledTimes(2);
  expect(fake.mock.calls.every(([, init]) => init.method === "GET")).toBe(true);
});

it("ignores an older microsecond cursor and rejects a different captured identity", async () => {
  vi.useFakeTimers();
  const current = operation({ progress: 40, updated_at: "2026-01-01T00:00:02.000002Z" });
  const older = operation({ progress: 20, updated_at: "2026-01-01T00:00:02.000001Z" });
  const wrongSubject = operation({
    subject_id: "another-fund",
    fund: "another-fund",
    progress: 90,
    updated_at: "2026-01-01T00:00:03Z",
  });
  const fake = vi.fn()
    .mockResolvedValueOnce(response(current))
    .mockResolvedValueOnce(response(older))
    .mockResolvedValueOnce(response(wrongSubject));
  vi.stubGlobal("fetch", fake);

  const { result } = renderHook(() => useOperation(operationId, "synthetic-fund"));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(result.current.data?.progress).toBe(40);
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.progress).toBe(40);
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.subject_id).toBe("synthetic-fund");
  expect(result.current.data?.progress).toBe(40);
  expect(result.current.apiError?.message).toMatch(/identity/i);
  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
  expect(fake).toHaveBeenCalledTimes(3);
});

it("observes an interrupted operation even if the server clock moves backwards", async () => {
  vi.useFakeTimers();
  const fake = vi.fn()
    .mockResolvedValueOnce(response(operation({
      progress: 40,
      updated_at: "2026-01-01T00:00:03Z",
    })))
    .mockResolvedValueOnce(response(operation({
      status: "interrupted",
      progress: 40,
      updated_at: "2026-01-01T00:00:02Z",
    })));
  vi.stubGlobal("fetch", fake);

  const { result } = renderHook(() => useOperation(operationId));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(result.current.data?.status).toBe("running");
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.status).toBe("interrupted");
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
  expect(fake).toHaveBeenCalledTimes(2);
});

it("keeps increasing progress when the clock moves backwards but rejects an older state", async () => {
  vi.useFakeTimers();
  const fake = vi.fn()
    .mockResolvedValueOnce(response(operation({ progress: 10, updated_at: "2026-01-01T00:00:03Z" })))
    .mockResolvedValueOnce(response(operation({ progress: 40, updated_at: "2026-01-01T00:00:02Z" })))
    .mockResolvedValueOnce(response(operation({ progress: 10, updated_at: "2026-01-01T00:00:03Z" })));
  vi.stubGlobal("fetch", fake);

  const { result } = renderHook(() => useOperation(operationId));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.progress).toBe(40);
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.progress).toBe(40);
});

it("rejects a malformed first receipt instead of treating it as a durable identity", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response(operation({ capture_digest: "not-a-digest" }))));
  const { result } = renderHook(() => useOperation(operationId, "synthetic-fund"));
  await act(async () => { await Promise.resolve(); });

  expect(result.current.data).toBeNull();
  expect(result.current.apiError?.message).toMatch(/identity/i);
});

it("aborts an obsolete read on identity change without declaring the desk offline", async () => {
  vi.useFakeTimers();
  const secondId = "d".repeat(32);
  let firstSignal: AbortSignal | undefined;
  const fake = vi.fn()
    .mockImplementationOnce((_path: string, init: RequestInit) => {
      firstSignal = init.signal ?? undefined;
      return new Promise<Response>((_resolve, reject) => {
        firstSignal?.addEventListener("abort", () => reject(new DOMException("cancelled", "AbortError")));
      });
    })
    .mockResolvedValueOnce(response(operation({
      operation_id: secondId,
      id: secondId,
      status: "completed",
      status_url: `/api/operations/${secondId}`,
    })));
  vi.stubGlobal("fetch", fake);
  const events: ApiEvent[] = [];
  const unsubscribe = subscribeApiEvents((event) => events.push(event));
  try {
    const { result, rerender } = renderHook(({ id }) => useOperation(id), {
      initialProps: { id: operationId },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    rerender({ id: secondId });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(firstSignal?.aborted).toBe(true);
    expect(result.current.data?.operation_id).toBe(secondId);
    expect(events).not.toContain("connection-lost");
    expect(fake).toHaveBeenCalledTimes(2);
  } finally {
    unsubscribe();
  }
});

it("does not regress a cancellation request to running at the same cursor", async () => {
  vi.useFakeTimers();
  const requested = operation({ status: "cancel-requested", cancel_requested: true, progress: 40 });
  const lateRunning = operation({ status: "running", cancel_requested: false, progress: 40 });
  const fake = vi.fn()
    .mockResolvedValueOnce(response(requested))
    .mockResolvedValueOnce(response(lateRunning));
  vi.stubGlobal("fetch", fake);

  const { result } = renderHook(() => useOperation(operationId));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(result.current.data?.status).toBe("cancel-requested");
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200); });
  expect(result.current.data?.status).toBe("cancel-requested");
  expect(result.current.data?.cancel_requested).toBe(true);
});

it("bounds automatic retries to transient status reads and never retries permanent denials", async () => {
  vi.useFakeTimers();
  const busy = {
    detail: "Status storage is busy.",
    code: "observation-conflict",
    retry_policy: "retry-read-only",
  };
  const fake = vi.fn(async (_path: string, _init: RequestInit) => response(busy, 503));
  vi.stubGlobal("fetch", fake);
  const first = renderHook(() => useOperation(operationId));
  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  await act(async () => { await vi.advanceTimersByTimeAsync(1_200 + 2_400 + 4_800); });
  expect(fake).toHaveBeenCalledTimes(4);
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  expect(fake).toHaveBeenCalledTimes(4);
  expect(first.result.current.apiError?.code).toBe("observation-conflict");
  first.unmount();

  fake.mockImplementation(async () => response({
    detail: "Operation is unavailable.",
    code: "not-found",
    retry_policy: "none",
  }, 404));
  renderHook(() => useOperation(operationId));
  await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
  expect(fake).toHaveBeenCalledTimes(5);
  expect(fake.mock.calls.every(([, init]) => init.method === "GET")).toBe(true);
});

it("discards a delayed observation from the previous pagination cursor", async () => {
  let releaseOld: (value: Response) => void = () => undefined;
  const fake = vi.fn()
    .mockImplementationOnce(() => new Promise<Response>((resolve) => { releaseOld = resolve; }))
    .mockResolvedValueOnce(response({ items: ["new-page"], next_cursor: null }));
  vi.stubGlobal("fetch", fake);
  const { result, rerender } = renderHook(({ path }) => useResource<{ items: string[] }>(path), {
    initialProps: { path: "/api/research?cursor=old" },
  });
  rerender({ path: "/api/research?cursor=new" });
  await act(async () => { await Promise.resolve(); });
  expect(result.current.data?.items).toEqual(["new-page"]);
  await act(async () => { releaseOld(response({ items: ["old-page"], next_cursor: "old" })); });
  expect(result.current.data?.items).toEqual(["new-page"]);
});

it("reconnects and rereads the selected operation without resubmitting or persisting tokens", async () => {
  const fake = vi.fn(async (path: string, _init: RequestInit) => {
    if (path === "/api/capabilities") return response({ mutation_token: "synthetic-csrf" });
    if (path === `/api/operations/${operationId}`) return response(operation({ status: "completed" }));
    throw new Error("Unexpected request.");
  });
  vi.stubGlobal("fetch", fake);
  const wrapper = ({ children }: { children: ReactNode }) => <DeskProvider>{children}</DeskProvider>;
  const { result } = renderHook(() => ({ operation: useOperation(operationId), desk: useDesk() }), { wrapper });
  await act(async () => { await Promise.resolve(); });
  expect(result.current.operation.data?.operation_id).toBe(operationId);
  await act(async () => { expect(await result.current.desk.reconnect()).toBe(true); });
  await act(async () => { await Promise.resolve(); });

  expect(fake.mock.calls.filter(([path]) => path === `/api/operations/${operationId}`)).toHaveLength(2);
  expect(fake.mock.calls.every(([, init]) => init.method === "GET")).toBe(true);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});
