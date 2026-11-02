import { ApiError } from "@/lib/api";
import type { ApiErrorCode, ApiRetryPolicy } from "@/lib/types";

export type RecoveryAction = "review-again" | "reconnect" | "inspect-status" | "retry" | null;

export interface ActionableError {
  message: string;
  guidance: string;
  action: RecoveryAction;
  retryPolicy: ApiRetryPolicy;
  code: ApiErrorCode | null;
  reference: string | null;
  offline: boolean;
}

const GUIDANCE: Record<ApiRetryPolicy, string> = {
  "review-again": "The reviewed state changed or expired. Nothing was submitted; request a fresh review before confirming.",
  reload: "The operator session was renewed. Nothing was submitted; review and submit again.",
  "inspect-status": "The outcome must be checked from durable status. Do not resubmit until status is inspected.",
  "retry-later": "Another writer is active and nothing changed. Try again later.",
  "retry-read-only": "No change was made. Retry the read.",
  none: "This request cannot succeed as submitted. Correct it or check readiness first.",
};

// Session renewal is only proven by a 403 reload denial; other reload conflicts may follow partial work.
const CONFLICT_GUIDANCE = "The request conflicts with current durable state or could not be completed. Reload and check current status before submitting again.";

const CODE_GUIDANCE: Partial<Record<ApiErrorCode, string>> = {
  halted: "The fund is halted. Resume it from Paper before running operations.",
  "replay-corrupt": "The ledger failed replay. Inspect its integrity before any further operation.",
  "reconciliation-required": "Reconciliation is required. Inspect the fund status before continuing.",
  "readiness-denied": "Readiness checks denied this request. Review provider, model or budget settings.",
  "protected-root": "This storage location is protected and cannot be changed from the web desk.",
  "broker-not-web-supported": "Only local paper operations are supported from the web desk.",
  "budget-exhausted": "The configured budget is exhausted. Nothing was submitted.",
  "capacity-denied": "Operation capacity is full. Nothing was accepted or started. Wait for running operations to finish, then review and submit again.",
};

const ACTIONS: Record<ApiRetryPolicy, RecoveryAction> = {
  "review-again": "review-again",
  reload: "review-again",
  "inspect-status": "inspect-status",
  "retry-later": "retry",
  "retry-read-only": "retry",
  none: null,
};

export function toActionableError(cause: unknown, fallback = "Request failed."): ActionableError {
  if (!(cause instanceof ApiError)) {
    return {
      message: cause instanceof Error && cause.message ? cause.message : fallback,
      guidance: "",
      action: null,
      retryPolicy: "none",
      code: null,
      reference: null,
      offline: false,
    };
  }
  const offline = cause.offline;
  const reference = [cause.subjectId, cause.requestId && `request ${cause.requestId}`].filter(Boolean).join(" · ") || null;
  const guidance = offline
    ? cause.retryPolicy === "inspect-status"
      ? "Reconnect, then inspect durable status before resubmitting."
      : "Reconnect to the local desk server, then retry."
    : (cause.code && CODE_GUIDANCE[cause.code])
      || (cause.retryPolicy === "reload" && cause.status !== 403 ? CONFLICT_GUIDANCE : GUIDANCE[cause.retryPolicy]);
  return {
    message: cause.message || fallback,
    guidance: !offline && cause.retryAfterSeconds !== null
      ? `${guidance} Suggested wait: about ${cause.retryAfterSeconds} s.`
      : guidance,
    action: offline ? "reconnect" : ACTIONS[cause.retryPolicy],
    retryPolicy: cause.retryPolicy,
    code: cause.code,
    reference,
    offline,
  };
}
