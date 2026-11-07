import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  readPendingOperations, readSavedOperationIdentities, rememberPendingOperation, saveOperationIdentity,
  type PendingOperation,
} from "@/lib/pending-operations";
import { usePendingOperations } from "@/lib/use-pending-operations";

const request: PendingOperation = { requestId: "a".repeat(32), action: "backtest", subjectId: "synthetic-fund" };
let locks: PropertyDescriptor | undefined;

beforeEach(() => {
  window.localStorage.clear();
  locks = Object.getOwnPropertyDescriptor(navigator, "locks");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.useRealTimers();
  if (locks) Object.defineProperty(navigator, "locks", locks);
  else Reflect.deleteProperty(navigator, "locks");
  window.localStorage.clear();
});

function surfaceLock(item: PendingOperation): string {
  return item.action === "backtest" ? 'aihf.operation-admission.["backtest"]'
    : `aihf.operation-admission.["paper",${JSON.stringify(item.subjectId)}]`;
}

async function holdSurface(item: PendingOperation) {
  let release!: () => void;
  let acquired!: () => void;
  const ready = new Promise<void>((resolve) => { acquired = resolve; });
  const held = navigator.locks.request(surfaceLock(item), async () => {
    acquired();
    await new Promise<void>((resolve) => { release = resolve; });
  });
  await ready;
  return async () => { release(); await held; };
}

it.each(["backtest", "paper-tick", "paper-runner-start"] as const)("refuses %s without cross-tab lock coordination", async (action) => {
  Object.defineProperty(navigator, "locks", { configurable: true, value: undefined });
  const { result } = renderHook(() => usePendingOperations(action === "backtest" ? "backtest" : "paper", request.subjectId));
  let admitted = true;

  await act(async () => { admitted = await result.current.remember({ ...request, action }); });

  expect(admitted).toBe(false);
  expect(readPendingOperations()).toEqual([]);
  expect(result.current.error).toMatch(/cross-tab.*coordination.*unavailable/i);
  expect(result.current.blocked).toBe(true);
});

it.each([
  ["backtest", "backtest"],
  ["paper-tick", "paper-tick"],
  ["paper-runner-start", "paper-runner-start"],
  ["paper-tick", "paper-runner-start"],
] as const)("admits only one simultaneous %s / %s request without relying on storage events", async (firstAction, secondAction) => {
  const kind = firstAction === "backtest" ? "backtest" : "paper";
  const first = renderHook(() => usePendingOperations(kind, request.subjectId));
  const second = renderHook(() => usePendingOperations(kind, request.subjectId));
  let results: boolean[] = [];

  await act(async () => {
    results = await Promise.all([
      first.result.current.remember({ ...request, action: firstAction }),
      second.result.current.remember({ ...request, requestId: "b".repeat(32), action: secondAction }),
    ]);
  });

  expect(results).toEqual([true, false]);
  expect(readPendingOperations()).toEqual([{ ...request, action: firstAction }]);
});

it("keeps different paper funds independent but shares the backtest surface across mandates", async () => {
  const first = renderHook(() => usePendingOperations("paper", "first-fund"));
  const second = renderHook(() => usePendingOperations("paper", "second-fund"));
  await act(async () => {
    expect(await first.result.current.remember({ ...request, action: "paper-tick", subjectId: "first-fund" })).toBe(true);
    expect(await second.result.current.remember({ ...request, requestId: "b".repeat(32), action: "paper-runner-start", subjectId: "second-fund" })).toBe(true);
  });
  const research = renderHook(() => usePendingOperations("backtest"));
  await act(async () => {
    expect(await research.result.current.remember({ ...request, requestId: "c".repeat(32), subjectId: "first-mandate" })).toBe(true);
    expect(await research.result.current.remember({ ...request, requestId: "d".repeat(32), subjectId: "second-mandate" })).toBe(false);
  });
  expect(readPendingOperations()).toHaveLength(3);
});

it.each(["pending", "saved"] as const)("re-reads a newly stored %s identity only after acquiring the lock", async (storage) => {
  const { result } = renderHook(() => usePendingOperations("backtest"));
  const release = await holdSurface(request);
  let submission!: Promise<boolean>;
  act(() => { submission = result.current.remember(request); });
  const competing = { ...request, requestId: "b".repeat(32) };
  if (storage === "pending") rememberPendingOperation(competing);
  else saveOperationIdentity(competing, "c".repeat(32));

  await act(async () => { await release(); expect(await submission).toBe(false); });

  expect(readPendingOperations()).toEqual(storage === "pending" ? [competing] : []);
  expect(readSavedOperationIdentities()).toEqual(storage === "saved" ? [{ ...competing, operationId: "c".repeat(32) }] : []);
});

it.each(["unknown", "active", "terminal"] as const)("requires exact terminal verification before admitting past a %s saved monitor", async (status) => {
  const pending = { ...request, requestId: "b".repeat(32) };
  const saved = { ...pending, operationId: "c".repeat(32) };
  saveOperationIdentity(pending, saved.operationId);
  const { result } = renderHook(() => usePendingOperations("backtest"));
  act(() => result.current.observe(saved, status));

  await act(async () => { expect(await result.current.remember(request)).toBe(status === "terminal"); });

  expect(readPendingOperations()).toEqual(status === "terminal" ? [request] : []);
});

it("releases the surface lock when preserving the request throws", async () => {
  const { result } = renderHook(() => usePendingOperations("backtest"));
  vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(() => { throw new DOMException("Storage denied"); });

  await act(async () => { expect(await result.current.remember(request)).toBe(false); });
  expect(result.current.error).toMatch(/storage/i);
  expect(readPendingOperations()).toEqual([]);
  act(() => result.current.refresh());
  await act(async () => { expect(await result.current.remember(request)).toBe(true); });
  expect(readPendingOperations()).toEqual([request]);
});

it("surfaces lock manager failures without persisting an identity", async () => {
  const { result } = renderHook(() => usePendingOperations("backtest"));
  vi.spyOn(navigator.locks, "request").mockRejectedValueOnce(new DOMException("Lock access denied", "SecurityError"));

  await act(async () => { expect(await result.current.remember(request)).toBe(false); });

  expect(result.current.error).toBe("Lock access denied");
  expect(readPendingOperations()).toEqual([]);
});

it.each(["cancel", "unmount", "scope-change"] as const)("does not preserve a queued paper identity after %s", async (reason) => {
  const item: PendingOperation = { ...request, action: "paper-tick" };
  const view = renderHook(({ subjectId }) => usePendingOperations("paper", subjectId), { initialProps: { subjectId: item.subjectId } });
  const release = await holdSurface(item);
  const controller = new AbortController();
  let submission!: Promise<boolean>;
  act(() => { submission = view.result.current.remember(item, controller.signal); });
  if (reason === "cancel") controller.abort();
  else if (reason === "unmount") view.unmount();
  else view.rerender({ subjectId: "second-fund" });

  await act(async () => { await release(); expect(await submission).toBe(false); });

  expect(readPendingOperations()).toEqual([]);
});

it("removes an unsubmitted identity if cancellation races with preserving it", async () => {
  const { result } = renderHook(() => usePendingOperations("backtest"));
  const controller = new AbortController();
  const setItem = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementationOnce(function (this: Storage, key, value) {
    setItem.call(this, key, value);
    controller.abort();
  });

  await act(async () => { expect(await result.current.remember(request, controller.signal)).toBe(false); });

  expect(readPendingOperations()).toEqual([]);
  expect(result.current.error).toBeNull();
});

it("bounds lock waiting and permits a fresh reviewed attempt after timeout", async () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => usePendingOperations("backtest"));
  const release = await holdSurface(request);
  let submission!: Promise<boolean>;
  act(() => { submission = result.current.remember(request); });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
    await release();
    expect(await submission).toBe(false);
  });
  expect(result.current.error).toMatch(/coordination timed out/i);
  expect(readPendingOperations()).toEqual([]);
  act(() => result.current.refresh());
  await act(async () => { expect(await result.current.remember(request)).toBe(true); });
});
