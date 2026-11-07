import type { Operation, OperationStatus } from "@/lib/types";

const STATUSES: ReadonlySet<string> = new Set<OperationStatus>([
  "accepted", "running", "cancel-requested", "cancelled", "completed", "failed", "interrupted",
]);

export interface ExpectedOperationIdentity {
  operationId?: string;
  requestId?: string;
  action?: string;
  subjectId?: string;
}

export function matchesOperationIdentity(value: unknown, expected: ExpectedOperationIdentity): value is Operation {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const operation = value as Partial<Operation>;
  return typeof operation.id === "string"
    && /^[a-f0-9]{32}$/.test(operation.id)
    && operation.operation_id === operation.id
    && (expected.operationId === undefined || operation.id === expected.operationId)
    && typeof operation.request_id === "string"
    && /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(operation.request_id)
    && (expected.requestId === undefined || operation.request_id === expected.requestId)
    && typeof operation.action === "string" && operation.action.length > 0
    && (expected.action === undefined || operation.action === expected.action)
    && typeof operation.subject_id === "string" && operation.subject_id.length > 0
    && operation.fund === operation.subject_id
    && (expected.subjectId === undefined || operation.subject_id === expected.subjectId)
    && typeof operation.capture_id === "string" && /^[a-f0-9]{32}$/.test(operation.capture_id)
    && typeof operation.capture_digest === "string" && /^[a-f0-9]{64}$/.test(operation.capture_digest)
    && typeof operation.created_at === "string" && Number.isFinite(Date.parse(operation.created_at))
    && typeof operation.updated_at === "string" && Number.isFinite(Date.parse(operation.updated_at))
    && typeof operation.status === "string" && STATUSES.has(operation.status)
    && typeof operation.progress === "number" && Number.isInteger(operation.progress)
    && operation.progress >= 0 && operation.progress <= 100;
}
