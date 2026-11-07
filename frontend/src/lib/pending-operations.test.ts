import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  forgetPendingOperation,
  forgetSavedOperationIdentity,
  readPendingOperations,
  readSavedOperationIdentities,
  recoverPendingOperation,
  rememberPendingOperation,
  saveOperationIdentity,
  type PendingOperation,
} from "@/lib/pending-operations";

const pending: PendingOperation = {
  requestId: "a".repeat(32),
  action: "backtest",
  subjectId: "synthetic-fund",
};

const operation = {
  id: "b".repeat(32),
  operation_id: "b".repeat(32),
  request_id: pending.requestId,
  action: pending.action,
  subject_id: pending.subjectId,
  fund: pending.subjectId,
  capture_id: "c".repeat(32),
  capture_digest: "d".repeat(64),
  status: "running",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:01Z",
  progress: 5,
};

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

it("retains distinct request identities without storing a confirmation or overwriting another tab", () => {
  const second: PendingOperation = { requestId: "e".repeat(32), action: "paper-tick", subjectId: "second-fund" };
  rememberPendingOperation(pending);
  rememberPendingOperation(second);

  expect(readPendingOperations()).toEqual([pending, second]);
  expect(() => rememberPendingOperation(pending)).toThrow(/already exists/i);
  expect(JSON.stringify(window.localStorage)).not.toMatch(/confirmation|csrf|token|payload/i);
  forgetPendingOperation(pending);
  expect(readPendingOperations()).toEqual([second]);
});

it("preserves each recovered operation independently and refuses a conflicting replacement", () => {
  const second: PendingOperation = { requestId: "e".repeat(32), action: "backtest", subjectId: pending.subjectId };
  rememberPendingOperation(pending);
  rememberPendingOperation(second);
  saveOperationIdentity(pending, "b".repeat(32));
  saveOperationIdentity(second, "f".repeat(32));
  forgetPendingOperation(pending);
  forgetPendingOperation(second);

  const saved = readSavedOperationIdentities();
  expect(saved).toEqual([
    { ...pending, operationId: "b".repeat(32) },
    { ...second, operationId: "f".repeat(32) },
  ]);
  expect(() => saveOperationIdentity(pending, "a".repeat(32))).toThrow(/conflict/i);
  expect(readSavedOperationIdentities()).toEqual(saved);
  expect(JSON.stringify(window.localStorage)).not.toMatch(/confirmation|csrf|token|payload/i);
  forgetSavedOperationIdentity(saved[0]);
  expect(readSavedOperationIdentities()).toEqual([saved[1]]);
});

it("retains the unresolved request if saving its recovered operation fails", () => {
  rememberPendingOperation(pending);
  const setItem = Storage.prototype.setItem;
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key, value) {
    if (key.startsWith("aihf.operation-identity.")) throw new DOMException("Storage denied");
    setItem.call(this, key, value);
  });
  expect(() => saveOperationIdentity(pending, "b".repeat(32))).toThrow(/storage/i);
  expect(readPendingOperations()).toEqual([pending]);
  expect(readSavedOperationIdentities()).toEqual([]);
});

it("surfaces malformed saved operation identities instead of discarding them", () => {
  const key = `aihf.operation-identity.${pending.requestId}`;
  window.localStorage.setItem(key, JSON.stringify({ ...pending, operationId: "../other", token: "bad" }));
  expect(() => readSavedOperationIdentities()).toThrow(/saved operation.*unreadable/i);
  expect(window.localStorage.getItem(key)).not.toBeNull();
});

it("refuses admission if browser storage cannot preserve a request identity", () => {
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new DOMException("Storage denied"); });
  expect(() => rememberPendingOperation(pending)).toThrow(/browser storage/i);
  expect(readPendingOperations()).toEqual([]);
});

it("surfaces malformed stored identities instead of silently forgetting an unknown request", () => {
  window.localStorage.setItem(`aihf.pending-operation.${pending.requestId}`, "{");
  expect(() => readPendingOperations()).toThrow(/pending.*unreadable/i);
  expect(window.localStorage.length).toBe(1);
});

it("recovers only the exact durable identity via a read, without resubmitting", async () => {
  rememberPendingOperation(pending);
  const fake = vi.fn(async () => new Response(JSON.stringify(operation), { status: 200 }));
  vi.stubGlobal("fetch", fake);

  expect(await recoverPendingOperation(pending)).toMatchObject(operation);
  expect(fake).toHaveBeenCalledTimes(1);
  expect(fake).toHaveBeenCalledWith(
    `/api/operations/by-request/${pending.requestId}`,
    expect.objectContaining({ method: "GET", credentials: "same-origin", mode: "same-origin" }),
  );
  expect(readPendingOperations()).toEqual([pending]);
});

it.each([
  { ...operation, request_id: "f".repeat(32) },
  { ...operation, subject_id: "other-fund", fund: "other-fund" },
  { ...operation, action: "paper-tick" },
  { ...operation, id: "f".repeat(32) },
  null,
])("retains the request when a lookup returns a mismatched or incomplete receipt", async (receipt) => {
  rememberPendingOperation(pending);
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(receipt), { status: 200 })));
  await expect(recoverPendingOperation(pending)).rejects.toMatchObject({ retryPolicy: "retry-read-only" });
  expect(readPendingOperations()).toEqual([pending]);
});

it("keeps a request after a 404 because absence does not prove that effects did not occur", async () => {
  rememberPendingOperation(pending);
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({
    detail: "No operation was found for this request; the outcome is still unknown.",
    code: "not-found",
  }), { status: 404 })));
  await expect(recoverPendingOperation(pending)).rejects.toMatchObject({ status: 404, code: "not-found" });
  expect(readPendingOperations()).toEqual([pending]);
});
