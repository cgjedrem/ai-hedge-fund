import { ApiError, apiGet, type ApiGetOptions } from "@/lib/api";
import { matchesOperationIdentity } from "@/lib/operation-identity";
import type { Operation } from "@/lib/types";

const PREFIX = "aihf.pending-operation.";
const SAVED_PREFIX = "aihf.operation-identity.";
const ACTIONS = new Set(["backtest", "paper-tick", "paper-runner-start"]);

export interface PendingOperation {
  requestId: string;
  action: "backtest" | "paper-tick" | "paper-runner-start";
  subjectId: string;
}

export interface SavedOperationIdentity extends PendingOperation {
  operationId: string;
}

export type SavedOperationObservation = "unknown" | "active" | "terminal";

function isPendingOperation(value: unknown): value is PendingOperation {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const item = value as Partial<PendingOperation>;
  return Object.keys(value).sort().join(",") === "action,requestId,subjectId"
    && typeof item.requestId === "string" && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(item.requestId)
    && typeof item.action === "string" && ACTIONS.has(item.action)
    && typeof item.subjectId === "string" && item.subjectId.length > 0 && item.subjectId.length <= 256
    && !/[\u0000-\u001f\u007f]/.test(item.subjectId);
}

function parsePending(value: string, key: string): PendingOperation {
  let item: unknown;
  try {
    item = JSON.parse(value);
  } catch {
    throw new Error("A pending operation identity is unreadable; inspect browser storage before continuing.");
  }
  if (!isPendingOperation(item) || key !== `${PREFIX}${item.requestId}`) {
    throw new Error("A pending operation identity is unreadable; inspect browser storage before continuing.");
  }
  return item;
}

function parseSaved(value: string, key: string): SavedOperationIdentity {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("A saved operation identity is unreadable; inspect browser storage before continuing.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("A saved operation identity is unreadable; inspect browser storage before continuing.");
  }
  const saved = parsed as Partial<SavedOperationIdentity>;
  const { operationId, ...pending } = saved;
  if (!isPendingOperation(pending) || typeof operationId !== "string" || !/^[a-f0-9]{32}$/.test(operationId)
      || key !== `${SAVED_PREFIX}${pending.requestId}`) {
    throw new Error("A saved operation identity is unreadable; inspect browser storage before continuing.");
  }
  return { ...pending, operationId };
}

export function readPendingOperations(): PendingOperation[] {
  const items: PendingOperation[] = [];
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(PREFIX)) continue;
      const value = window.localStorage.getItem(key);
      if (value === null) throw new Error("A pending operation identity is unreadable; inspect browser storage before continuing.");
      items.push(parsePending(value, key));
    }
  } catch (cause) {
    if (cause instanceof Error && cause.message.startsWith("A pending operation")) throw cause;
    throw new Error("Browser storage is unavailable; pending operation identities cannot be inspected.");
  }
  return items;
}

export function rememberPendingOperation(item: PendingOperation): void {
  if (!isPendingOperation(item)) throw new Error("The pending operation identity is invalid.");
  const key = `${PREFIX}${item.requestId}`;
  try {
    if (window.localStorage.getItem(key) !== null) throw new Error("This pending operation identity already exists.");
    const value = JSON.stringify(item);
    window.localStorage.setItem(key, value);
    if (window.localStorage.getItem(key) !== value) throw new Error("Browser storage did not preserve the request identity.");
  } catch (cause) {
    if (cause instanceof Error && cause.message.includes("already exists")) throw cause;
    throw new Error("Browser storage is unavailable; the operation was not submitted.");
  }
}

export function forgetPendingOperation(item: PendingOperation): void {
  if (!isPendingOperation(item)) throw new Error("The pending operation identity is invalid.");
  const key = `${PREFIX}${item.requestId}`;
  try {
    const value = window.localStorage.getItem(key);
    if (value === null) return;
    const saved = parsePending(value, key);
    if (saved.action !== item.action || saved.subjectId !== item.subjectId) {
      throw new Error("The stored pending operation identity changed.");
    }
    window.localStorage.removeItem(key);
  } catch (cause) {
    if (cause instanceof Error && (
      cause.message.startsWith("A pending operation") || cause.message.startsWith("The stored pending")
    )) throw cause;
    throw new Error("Browser storage is unavailable; the pending operation identity was retained.");
  }
}

export function readSavedOperationIdentities(): SavedOperationIdentity[] {
  const items: SavedOperationIdentity[] = [];
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (!key?.startsWith(SAVED_PREFIX)) continue;
      const value = window.localStorage.getItem(key);
      if (value === null) throw new Error("A saved operation identity is unreadable; inspect browser storage before continuing.");
      items.push(parseSaved(value, key));
    }
  } catch (cause) {
    if (cause instanceof Error && cause.message.startsWith("A saved operation")) throw cause;
    throw new Error("Browser storage is unavailable; saved operation identities cannot be inspected.");
  }
  return items;
}

export function saveOperationIdentity(item: PendingOperation, operationId: string): void {
  if (!isPendingOperation(item) || !/^[a-f0-9]{32}$/.test(operationId)) {
    throw new Error("The operation identity is invalid.");
  }
  const key = `${SAVED_PREFIX}${item.requestId}`;
  const value = JSON.stringify({ ...item, operationId });
  try {
    const existing = window.localStorage.getItem(key);
    if (existing !== null) {
      const saved = parseSaved(existing, key);
      if (saved.action !== item.action || saved.subjectId !== item.subjectId || saved.operationId !== operationId) {
        throw new Error("The saved operation identity conflicts with the recovered request.");
      }
      return;
    }
    window.localStorage.setItem(key, value);
    if (window.localStorage.getItem(key) !== value) throw new Error("Browser storage did not preserve the operation identity.");
  } catch (cause) {
    if (cause instanceof Error && (cause.message.startsWith("A saved operation") || cause.message.startsWith("The saved operation"))) throw cause;
    throw new Error("Browser storage is unavailable; the pending request identity was retained.");
  }
}

export function forgetSavedOperationIdentity(item: SavedOperationIdentity): void {
  const key = `${SAVED_PREFIX}${item.requestId}`;
  try {
    const value = window.localStorage.getItem(key);
    if (value === null) return;
    const saved = parseSaved(value, key);
    if (saved.action !== item.action || saved.subjectId !== item.subjectId || saved.operationId !== item.operationId) {
      throw new Error("The saved operation identity changed.");
    }
    window.localStorage.removeItem(key);
  } catch (cause) {
    if (cause instanceof Error && (cause.message.startsWith("A saved operation") || cause.message.startsWith("The saved operation"))) throw cause;
    throw new Error("Browser storage is unavailable; the saved operation identity was retained.");
  }
}

export async function recoverPendingOperation(item: PendingOperation, options: ApiGetOptions = {}): Promise<Operation> {
  if (!isPendingOperation(item)) throw new Error("The pending operation identity is invalid.");
  const value = await apiGet<unknown>(`/api/operations/by-request/${encodeURIComponent(item.requestId)}`, options);
  if (!matchesOperationIdentity(value, item)) {
    throw new ApiError("Operation status identity is inconsistent; the request outcome is unknown.", 200, {
      retryPolicy: "retry-read-only",
      requestId: item.requestId,
    });
  }
  return value;
}
