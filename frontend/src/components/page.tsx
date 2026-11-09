import { AlertCircle, LoaderCircle } from "lucide-react";
import type { ReactNode } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ActionableError, RecoveryAction } from "@/lib/errors";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-7 flex flex-col gap-5 border-b border-border/80 pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <p className="mono mb-2 text-[10px] font-medium uppercase tracking-[0.22em] text-accent">
          {eyebrow}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground sm:text-[2rem]">{title}</h1>
        {description ? <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
    </header>
  );
}

export function SectionTitle({
  title,
  note,
  right,
}: {
  title: string;
  note?: string;
  right?: ReactNode;
}) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {note ? <p className="mt-1 text-xs text-muted-foreground">{note}</p> : null}
      </div>
      {right}
    </div>
  );
}

export function LoadingState({ label = "Loading desk data" }: { label?: string }) {
  return (
    <div className="flex min-h-40 items-center justify-center gap-3 text-sm text-muted-foreground" role="status">
      <LoaderCircle className="h-4 w-4 animate-spin text-accent" />
      <span>{label}…</span>
    </div>
  );
}

export function ErrorState({
  message,
  error,
  onRetry,
}: {
  message: string;
  error?: ActionableError | null;
  onRetry?: () => void;
}) {
  const retryable = Boolean(onRetry) && (error?.action === "retry" || error?.action === "reconnect");
  return (
    <Alert tone="danger" className="flex items-start gap-3">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <p className="font-medium text-rose-100">Unable to load this view</p>
        <p className="mt-1 break-words text-rose-200/80">{message}</p>
        {error?.guidance ? <p className="mt-1 text-xs text-rose-200/70">{error.guidance}</p> : null}
        {retryable ? (
          <Button className="mt-2" size="sm" variant="secondary" onClick={onRetry}>
            Retry
          </Button>
        ) : null}
      </div>
    </Alert>
  );
}

const ACTION_LABELS: Record<Exclude<RecoveryAction, null>, string> = {
  "review-again": "Review again",
  reconnect: "Reconnect",
  "inspect-status": "Inspect status",
  retry: "Retry",
};

/** Mutation failure notice: message stays its own node; guidance, identity and one recovery action follow. */
export function ErrorNotice({
  error,
  onAction,
  actionLabel,
  className = "",
}: {
  error: ActionableError;
  onAction?: () => void;
  actionLabel?: string;
  className?: string;
}) {
  return (
    <div role="alert" className={`rounded-lg border border-rose-400/30 bg-rose-500/10 px-3 py-2 text-xs ${className}`}>
      <p className="break-words text-rose-100">{error.message}</p>
      {error.guidance ? <p className="mt-1 text-rose-200/80">{error.guidance}</p> : null}
      {error.reference ? <p className="mono mt-1 text-[10px] text-rose-200/60">Ref {error.reference}</p> : null}
      {onAction && error.action ? (
        <Button className="mt-2" size="sm" variant="secondary" onClick={onAction}>
          {actionLabel ?? ACTION_LABELS[error.action]}
        </Button>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  badge,
}: {
  title: string;
  description: string;
  badge?: string;
}) {
  return (
    <div className="rounded-xl border border-dashed border-border bg-white/[0.015] px-5 py-10 text-center">
      {badge ? <Badge variant="muted">{badge}</Badge> : null}
      <h3 className="mt-3 text-sm font-semibold text-foreground">{title}</h3>
      <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-muted-foreground">{description}</p>
    </div>
  );
}

export function NumericValue({
  value,
  positive = false,
  negative = false,
}: {
  value: string;
  positive?: boolean;
  negative?: boolean;
}) {
  return (
    <span
      className={`mono text-sm ${positive ? "text-emerald-300" : ""} ${negative ? "text-rose-300" : ""}`}
    >
      {value}
    </span>
  );
}
