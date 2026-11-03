import type { Operation, OperationStatus, RunnerState } from "@/lib/types";

const RUNNER_LABELS: Record<string, string> = {
  starting: "Runner starting",
  running: "Runner running",
  stopping: "Runner stopping",
  stopped: "Runner stopped",
  completed: "Runner completed",
  failed: "Runner error",
  unknown: "Runner unverified",
};

const OPERATION_LABELS: Record<OperationStatus, string> = {
  accepted: "accepted",
  running: "running",
  "cancel-requested": "stopping",
  completed: "completed",
  failed: "error",
  interrupted: "interrupted",
  cancelled: "cancelled",
};

// Unrecognised runner states are never presented as a verified process state.
export function runnerStatusLabel(runner: Pick<RunnerState, "status"> | null | undefined): string {
  if (!runner) return "Runner unavailable";
  return Object.hasOwn(RUNNER_LABELS, runner.status) ? RUNNER_LABELS[runner.status] : "Runner unverified";
}

export function operationStatusLabel(status: OperationStatus): string {
  return Object.hasOwn(OPERATION_LABELS, status) ? OPERATION_LABELS[status] : "unverified";
}

export function nothingDueLabel(dueSet: readonly string[]): string | null {
  return dueSet.length === 0 ? "Nothing due now; the runner waits for the next eligible session." : null;
}

export function PaperOperationStatus({ operation }: { operation: Operation }) {
  const progress = Math.min(100, Math.max(0, operation.progress));
  return (
    <div className="mt-4 rounded-lg border border-border bg-black/10 p-3" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <span className="mono text-[10px] text-foreground">
          {operation.action === "paper-tick" ? "Manual tick" : "Runner start"} · {operationStatusLabel(operation.status)}
        </span>
        <span className="mono text-[10px] text-muted-foreground">{progress}%</span>
      </div>
      <div
        className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"
        role="progressbar"
        aria-label="Paper operation progress"
        aria-valuenow={progress}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${progress}%` }} />
      </div>
      <p className="mono mt-2 break-all text-[9px] text-muted-foreground">{operation.id}</p>
      {operation.error ? <p className="mt-2 text-[10px] text-rose-300">{operation.error}</p> : null}
    </div>
  );
}
