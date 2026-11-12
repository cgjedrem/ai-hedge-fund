import {
  ArrowLeft,
  ArrowRight,
  BadgeDollarSign,
  CalendarClock,
  CirclePause,
  CirclePlay,
  Download,
  FileCheck2,
  FileText,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { ArchivePanel } from "@/components/archive-panel";
import { LifecycleActions } from "@/components/lifecycle-actions";
import { DataTable, type TableColumn } from "@/components/data-table";
import { EquityChart } from "@/components/equity-chart";
import { MetricCard } from "@/components/metric-card";
import { nothingDueLabel, PaperOperationStatus, runnerStatusLabel } from "@/components/operation-status";
import { PaperSessionDays } from "@/components/paper-session-days";
import { PendingOperationRecovery } from "@/components/pending-operation-recovery";
import { EmptyState, ErrorNotice, ErrorState, LoadingState, PageHeader, SectionTitle } from "@/components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiPost, isPreAdmissionDenial, requireMutationOperationReceipt } from "@/lib/api";
import { toActionableError, type ActionableError } from "@/lib/errors";
import { useDesk, useOperation, useResource } from "@/lib/hooks";
import type { PendingOperation } from "@/lib/pending-operations";
import { usePendingOperations } from "@/lib/use-pending-operations";
import type {
  Approval,
  ClampEventDto,
  HaltState,
  LiveValuation,
  PaperCollection,
  PaperOperationPreview,
  PaperReconciliation,
  PaperSessionsCollection,
  PaperSnapshot,
  PaperSummary,
  PendingDecision,
  Position,
  RunnerState,
  RiskLimitsDto,
  ScoreMetrics,
  SessionReport,
} from "@/lib/types";
import { dateLabel, money, pct, shortHash } from "@/lib/utils";

export function PaperPage() {
  const resource = useResource<PaperCollection>("/api/paper");
  const columns: TableColumn<PaperSummary>[] = [
    {
      key: "fund",
      label: "Paper fund",
      render: (item) => (
        <div>
          <Link to={`/paper/${encodeURIComponent(item.name)}`} className="font-medium text-foreground hover:text-accent hover:underline">
            {item.name}
          </Link>
          <p className="mt-1 text-[10px] text-muted-foreground">{item.universe.join(" · ")}</p>
        </div>
      ),
    },
    { key: "cadence", label: "Cadence", render: (item) => <span className="mono">{item.cadence}</span> },
    { key: "nav", label: "Recorded NAV", align: "right", render: (item) => <span className="mono text-foreground">{money(item.nav)}</span> },
    { key: "cash", label: "Cash", align: "right", render: (item) => <span className="mono">{money(item.cash)}</span> },
    { key: "session", label: "Last record", render: (item) => <span className="mono text-[11px]">{dateLabel(item.last_session)}</span> },
    {
      key: "status",
      label: "Ledger / control",
      render: (item) => (
        <div className="flex flex-wrap gap-1.5">
          <Badge variant={item.ledger_ok ? "positive" : "negative"}>{item.ledger_ok ? "Verified" : "Error"}</Badge>
          {item.halt_state === "unreadable" ? (
            <Badge variant="warning">Halt state unknown</Badge>
          ) : item.halt_state === "halted" ? (
            <Badge variant="warning">Halted</Badge>
          ) : item.runner.status === "unknown" ? (
            <Badge variant="warning">{runnerStatusLabel(item.runner)}</Badge>
          ) : item.runner.available ? (
            <Badge variant="positive">{runnerStatusLabel(item.runner)}</Badge>
          ) : (
            <Badge variant="muted">{runnerStatusLabel(item.runner)}</Badge>
          )}
        </div>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Portfolio / paper books"
        title="Paper funds"
        description="Ledger-backed snapshots and explicit action boundaries. Runner status is not inferred from process probes."
        actions={<Button asChild variant="secondary"><Link to="/mandates"><FileCheck2 className="h-3.5 w-3.5" /> Browse mandates</Link></Button>}
      />
      {resource.loading ? <div className="h-56 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /> : null}
      {resource.data ? (
        <div className="min-w-0 space-y-5">
          {resource.data.errors.length > 0 ? (
            <Alert tone="warning">
              <p className="font-medium">Some books could not be verified.</p>
              <ul className="mt-2 space-y-1 text-xs">
                {resource.data.errors.map((item, index) => <li key={`${item.name}-${index}`}><span className="mono">{item.name}</span><span className="px-2 opacity-50">/</span>{item.error}</li>)}
              </ul>
            </Alert>
          ) : null}
          <Card>
            <CardHeader>
              <SectionTitle title="Local ledger snapshots" note={`${resource.data.items.length} paper book${resource.data.items.length === 1 ? "" : "s"}`} />
            </CardHeader>
            <CardContent>
              <DataTable
                columns={columns}
                rows={resource.data.items}
                rowKey={(item) => item.name}
                emptyTitle="No deployed paper funds"
                emptyDescription="Create a paper book from a saved mandate. Deployment writes only under the configured local data root."
              />
            </CardContent>
          </Card>
        </div>
      ) : null}
      <ArchivePanel kind="deployment" onChange={resource.refresh} />
    </>
  );
}

type PendingAction = "approve" | "reject" | "resume";

export function PaperDetailPage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const { capabilities, reconnect } = useDesk();
  const resource = useResource<PaperSnapshot>(name ? `/api/paper/${encodeURIComponent(name)}` : null);
  const [selectedIntent, setSelectedIntent] = useState<{ fund: string; digest: string } | null>(null);
  const selectedIntentDigest = selectedIntent?.fund === name ? selectedIntent.digest : null;
  useEffect(() => setSelectedIntent(null), [name]);
  const reconciliationPath = name && resource.data?.broker === "paper" && (resource.data.ledger.ok || resource.data.recovery_state === "reconciliation_required")
    ? `/api/paper/${encodeURIComponent(name)}/reconciliation${selectedIntentDigest ? `?intent_digest=${encodeURIComponent(selectedIntentDigest)}` : ""}`
    : null;
  const reconciliationResource = useResource<PaperReconciliation>(
    reconciliationPath,
  );
  const [sessionSearchText, setSessionSearchText] = useState("");
  const [sessionSearch, setSessionSearch] = useState("");
  const [sessionCursorStack, setSessionCursorStack] = useState<(string | null)[]>([null]);
  const sessionCursor = sessionCursorStack[sessionCursorStack.length - 1];
  const sessionQuery = new URLSearchParams({ limit: "50" });
  if (sessionCursor) sessionQuery.set("cursor", sessionCursor);
  if (sessionSearch) sessionQuery.set("search", sessionSearch);
  const sessionResource = useResource<PaperSessionsCollection>(
    name ? `/api/paper/${encodeURIComponent(name)}/sessions?${sessionQuery.toString()}` : null,
  );
  const runnerResource = useResource<RunnerState>(
    name ? `/api/paper/${encodeURIComponent(name)}/runner` : null,
  );
  const [operationId, setOperationId] = useState<string | null>(null);
  const operationResource = useOperation(operationId, name);
  const pendingOperations = usePendingOperations("paper", name);
  const [confirmAction, setConfirmAction] = useState<PendingAction | null>(null);
  const [intentRecoveryOpen, setIntentRecoveryOpen] = useState(false);
  const [haltDialogOpen, setHaltDialogOpen] = useState(false);
  const [haltReason, setHaltReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [paperActionBusy, setPaperActionBusy] = useState(false);
  const [paperAdmissionWaiting, setPaperAdmissionWaiting] = useState(false);
  const [paperPreview, setPaperPreview] = useState<PaperOperationPreview | null>(null);
  const [paperPreviewKind, setPaperPreviewKind] = useState<"tick" | "runner" | null>(null);
  const [stopRunnerDialogOpen, setStopRunnerDialogOpen] = useState(false);
  const [maxSessions, setMaxSessions] = useState("1");
  const [maxRuntimeMinutes, setMaxRuntimeMinutes] = useState("60");
  const [valuationBusy, setValuationBusy] = useState(false);
  const [valuationResult, setValuationResult] = useState<LiveValuation | null>(null);
  const [feedback, setFeedback] = useState<{ tone: "danger" | "neutral"; message: string; error?: ActionableError } | null>(null);
  const valuationRequest = useRef(0);
  const paperActionInFlight = useRef(false);
  const paperAdmissionController = useRef<AbortController | null>(null);
  const refreshedOperation = useRef<string | null>(null);
  const activeFundName = useRef(name);
  const recoveryRequest = useRef<{ failureId: string; previewDigest: string; requestId: string } | null>(null);
  const intentRecoveryRequest = useRef<{ key: string; requestId: string } | null>(null);
  const verdictRequest = useRef<{ key: string; requestId: string } | null>(null);
  const manualResumeRequest = useRef<{ key: string; requestId: string } | null>(null);
  const haltRequest = useRef<{ key: string; requestId: string } | null>(null);
  activeFundName.current = name;
  useEffect(() => () => paperAdmissionController.current?.abort(), [name]);
  const protectedName = capabilities?.protected_names.some((entry) => entry.toLowerCase() === name.toLowerCase()) ?? false;
  const canWrite = capabilities?.writes === true && !protectedName;
  const data = resource.data;
  const recovery = reconciliationResource.data?.name === name ? reconciliationResource.data : null;
  const writeUnavailable = capabilities?.write_unavailable_reason != null;
  const enrollmentState = capabilities?.enrollment_state ?? "unenrolled";
  const runner = runnerResource.data ?? data?.runner;
  const observedOperation = operationResource.data?.id === operationId ? operationResource.data : null;
  const unexpectedOperation = observedOperation
    && !["paper-tick", "paper-runner-start"].includes(observedOperation.action)
    ? observedOperation
    : null;
  const operation = unexpectedOperation ? null : observedOperation;
  const approvalRequired = data?.spec.approval_required === true;
  const canWritePaper = canWrite && data?.broker === "paper";
  const canApprove = canWritePaper && approvalRequired && data?.halt_state === "clear" && data?.ledger.ok === true;
  const canResumePaper = Boolean(
    canWritePaper
    && (data?.halt_state === "halted" || (data?.halt_state === "clear" && recovery?.resume_completion_required === true))
    && data.recovery_state !== "corrupt"
    && (data.ledger.ok || data.recovery_state === "reconciliation_required")
    && recovery?.resume_allowed === true,
  );
  const intentPreview = recovery?.intent_preview;
  const approvalConsumptionOnly = Boolean(intentPreview?.required && intentPreview.intent_digest === null && intentPreview.approval_journal_event_digests.length > 0);
  const intentTargets = recovery?.intent_targets ?? [];
  const canReconcileTickIntent = Boolean(
    canWritePaper
    && intentPreview?.required
    && intentPreview.recoverable,
  );
  const canRefreshValuation = canWritePaper && capabilities?.network === true && data?.ledger.ok === true;
  const liveValue = valuationResult ?? data?.live_value;
  const paperOperationActive = Boolean(
    operation && ["accepted", "running", "cancel-requested"].includes(operation.status),
  );
  const runnerInactive = Boolean(
    runner
    && !runner.available
    && ["stopped", "completed", "failed", "blocked"].includes(runner.status),
  );
  const canOperatePaper = Boolean(
    canWritePaper
    && capabilities?.network === true
    && data.ledger.ok
    && data.halt_state === "clear"
    && runnerInactive
    && !paperOperationActive
    && !pendingOperations.blocked,
  );
  const canStopRunner = Boolean(
    canWritePaper
    && runner?.available
    && runner.status === "running",
  );
  const fail = (cause: unknown, fallback: string) => {
    const error = toActionableError(cause, fallback);
    setFeedback({ tone: "danger", message: error.message, error });
  };
  // Recovery never resubmits: it refreshes durable state so the operator reviews again.
  const recover = (error: ActionableError) => {
    if (error.action === "reconnect") {
      void reconnect();
      return;
    }
    setPaperPreview(null);
    setPaperPreviewKind(null);
    setConfirmAction(null);
    setFeedback(null);
    resource.refresh();
    reconciliationResource.refresh();
    runnerResource.refresh();
    if (operationId) operationResource.refresh();
  };
  const staleOperation = Boolean(operationId && operationResource.apiError?.code === "not-found");
  const forgetPaperOperation = () => {
    clearPaperOperationId(name);
    setOperationId(null);
  };
  const submitSessionSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSessionCursorStack([null]);
    setSessionSearch(sessionSearchText);
  };

  useEffect(() => {
    valuationRequest.current += 1;
    setValuationResult(null);
    setValuationBusy(false);
  }, [name, data?.last_record_hash]);

  useEffect(() => {
    setOperationId(readPaperOperationId(name));
    setPaperPreview(null);
    setPaperPreviewKind(null);
    recoveryRequest.current = null;
    intentRecoveryRequest.current = null;
  }, [name]);

  useEffect(() => {
    if (!runner?.available) return;
    const timer = window.setTimeout(() => {
      runnerResource.refresh();
      if (operation?.status === "completed") resource.refresh();
    }, 900);
    return () => window.clearTimeout(timer);
  }, [
    runner?.available,
    runner?.status,
    operation?.status,
    runnerResource.refresh,
    resource.refresh,
  ]);

  useEffect(() => {
    if (
      operation?.status === "completed"
      && refreshedOperation.current !== operation.id
    ) {
      refreshedOperation.current = operation.id;
      resource.refresh();
      runnerResource.refresh();
    }
  }, [operation?.id, operation?.status, resource.refresh, runnerResource.refresh]);

  async function submitAction(): Promise<void> {
    if (!confirmAction) return;
    if (
      confirmAction === "approve" || confirmAction === "reject"
        ? !canApprove
        : !canResumePaper
    ) return;
    setBusy(true);
    setFeedback(null);
    try {
      if (confirmAction === "approve" || confirmAction === "reject") {
        const pending = data?.pending;
        if (!pending) {
          setFeedback({ tone: "danger", message: "No pending decision is available. Reload the page before trying again." });
          resource.refresh();
          return;
        }
        const key = `${name}:${confirmAction}:${pending.decision_as_of}:${pending.source_record_hash}`;
        const current = verdictRequest.current;
        const request = current?.key === key ? current : { key, requestId: newRequestId() };
        verdictRequest.current = request;
        await submitVerdict(name, confirmAction, pending, request.requestId);
        verdictRequest.current = null;
        setFeedback({ tone: "neutral", message: `Verdict ${confirmAction} was saved to the local approval mailbox. It does not execute immediately.` });
      } else {
        const preview = recovery?.preview;
        if (!recovery?.resume_allowed || !preview) {
          setFeedback({ tone: "danger", message: "Recovery state is unavailable. Reload the current paper state before resuming." });
          reconciliationResource.refresh();
          return;
        }
        if (preview.required) {
          if (!preview.recoverable || !preview.failure_id || !preview.preview_digest) {
            setFeedback({ tone: "danger", message: "The current recovery preview is incomplete or not recoverable. Halt remains active." });
            reconciliationResource.refresh();
            return;
          }
          const current = recoveryRequest.current;
          const requestId = current?.failureId === preview.failure_id && current.previewDigest === preview.preview_digest
            ? current.requestId
            : newRequestId();
          recoveryRequest.current = {
            failureId: preview.failure_id,
            previewDigest: preview.preview_digest,
            requestId,
          };
          await apiPost(`/api/paper/${encodeURIComponent(name)}/resume`, {
            request_id: requestId,
            failure_id: preview.failure_id,
            preview_digest: preview.preview_digest,
            decision: preview.decision,
          });
          recoveryRequest.current = null;
          setFeedback({ tone: "neutral", message: "Reconciliation receipt recorded. Halt cleared. Failed tick was not retried; no runner was started." });
        } else {
          const key = `${name}:${data?.last_record_hash ?? ""}`;
          const current = manualResumeRequest.current;
          const journalRequestId = recovery.resume_completion_required ? recovery.resume_request_id : null;
          const request = journalRequestId
            ? { key, requestId: journalRequestId }
            : current?.key === key
              ? current
              : { key, requestId: newRequestId() };
          manualResumeRequest.current = request;
          await apiPost(`/api/paper/${encodeURIComponent(name)}/resume`, { request_id: request.requestId });
          manualResumeRequest.current = null;
          setFeedback({
            tone: "neutral",
            message: recovery.resume_completion_required
              ? "Resume completion recorded. No control write or paper operation was repeated."
              : "Halt cleared. No paper operation ran and no runner was started.",
          });
        }
      }
      setConfirmAction(null);
      resource.refresh();
    } catch (cause) {
      fail(cause, "Action failed.");
      if (confirmAction === "resume") {
        resource.refresh();
        reconciliationResource.refresh();
      }
      // The reviewed confirmation is spent; close it so the recovery notice is reachable.
      setConfirmAction(null);
    } finally {
      setBusy(false);
    }
  }

  async function submitIntentRecovery(): Promise<void> {
    const preview = recovery?.intent_preview;
    if (!preview || !canReconcileTickIntent || !preview.preview_digest) {
      setFeedback({ tone: "danger", message: "Tick-intent recovery preview is unavailable or not recoverable. Paper admission remains fenced." });
      reconciliationResource.refresh();
      return;
    }
    const key = `${name}:${preview.intent_request_id ?? ""}:${preview.intent_digest ?? ""}:${preview.preview_digest}`;
    const current = intentRecoveryRequest.current;
    const request = current?.key === key ? current : { key, requestId: newRequestId() };
    intentRecoveryRequest.current = request;
    setBusy(true);
    setFeedback(null);
    try {
      await apiPost(`/api/paper/${encodeURIComponent(name)}/reconcile-tick-request`, {
        request_id: request.requestId,
        intent_request_id: preview.intent_request_id,
        intent_digest: preview.intent_digest,
        preview_digest: preview.preview_digest,
        decision: preview.decision,
      });
      intentRecoveryRequest.current = null;
      setIntentRecoveryOpen(false);
      setSelectedIntent(null);
      setFeedback({ tone: "neutral", message: "Audited tick-intent reconciliation recorded. No tick was retried and no broker effect was created." });
      await Promise.all([resource.refresh(), reconciliationResource.refresh()]);
    } catch (cause) {
      fail(cause, "Tick-intent reconciliation failed.");
      resource.refresh();
      reconciliationResource.refresh();
    } finally {
      setBusy(false);
    }
  }

  async function submitHalt(): Promise<void> {
    if (!canWritePaper) return;
    const reason = haltReason.trim();
    if (!reason) {
      setFeedback({ tone: "danger", message: "Enter a reason before halting this fund." });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      const key = `${name}:${reason}`;
      const current = haltRequest.current;
      const request = current?.key === key ? current : { key, requestId: newRequestId() };
      haltRequest.current = request;
      await apiPost(`/api/paper/${encodeURIComponent(name)}/halt`, { request_id: request.requestId, reason });
      haltRequest.current = null;
      setHaltDialogOpen(false);
      setHaltReason("");
      setFeedback({ tone: "neutral", message: "Halt state recorded in the ledger. Runner process control is not available here." });
      resource.refresh();
    } catch (cause) {
      fail(cause, "Halt request failed.");
      setHaltDialogOpen(false);
    } finally {
      setBusy(false);
    }
  }

  async function refreshValuation(): Promise<void> {
    if (!data || !canRefreshValuation) return;
    const request = ++valuationRequest.current;
    setValuationBusy(true);
    setFeedback(null);
    try {
      const estimate = await apiPost<LiveValuation>(
        `/api/paper/${encodeURIComponent(name)}/valuation`,
        { expected_head: data.last_record_hash },
      );
      if (request !== valuationRequest.current) return;
      setValuationResult(estimate);
    } catch (cause) {
      if (request !== valuationRequest.current) return;
      fail(cause, "Valuation refresh failed.");
    } finally {
      if (request === valuationRequest.current) setValuationBusy(false);
    }
  }

  async function requestPaperPreview(kind: "tick" | "runner"): Promise<void> {
    if (!data || !canOperatePaper || paperActionInFlight.current) return;
    let bounds: { max_sessions: number; max_runtime_minutes: number } | null = null;
    if (kind === "runner") {
      const sessions = Number(maxSessions);
      const runtime = Number(maxRuntimeMinutes);
      if (!Number.isInteger(sessions) || sessions < 1 || sessions > 100) {
        setFeedback({ tone: "danger", message: "Runner session bound must be an integer from 1 to 100." });
        return;
      }
      if (!Number.isInteger(runtime) || runtime < 1 || runtime > 1440) {
        setFeedback({ tone: "danger", message: "Runner deadline must be an integer from 1 to 1440 minutes." });
        return;
      }
      bounds = { max_sessions: sessions, max_runtime_minutes: runtime };
    }

    paperActionInFlight.current = true;
    setPaperActionBusy(true);
    setFeedback(null);
    try {
      const preview = await apiPost<PaperOperationPreview>(
        `/api/paper/${encodeURIComponent(name)}/${kind === "tick" ? "tick" : "runner"}/preview`,
        {
          expected_head: data.last_record_hash,
          ...(bounds ?? {}),
        },
      );
      setPaperPreview(preview);
      setPaperPreviewKind(kind);
    } catch (cause) {
      fail(cause, "Paper preview failed.");
    } finally {
      paperActionInFlight.current = false;
      setPaperActionBusy(false);
    }
  }

  async function acceptPaperPreview(): Promise<void> {
    if (!paperPreview || !paperPreviewKind || !canOperatePaper || paperActionInFlight.current) return;
    const expectedAction = paperPreviewKind === "tick" ? "paper-tick" : "paper-runner-start";
    if (paperPreview.action !== expectedAction || paperPreview.subject_id !== name) {
      setFeedback({ tone: "danger", message: "Paper preview identity is inconsistent; review the operation again." });
      setPaperPreview(null);
      setPaperPreviewKind(null);
      return;
    }
    const pendingRequest: PendingOperation = {
      requestId: newRequestId(),
      action: expectedAction,
      subjectId: name,
    };
    const request: Record<string, unknown> = {
      request_id: pendingRequest.requestId,
      preview_id: paperPreview.preview_id,
      preview_digest: paperPreview.preview_digest,
      confirmation_token: paperPreview.confirmation_token,
      expected_head: paperPreview.expected_head,
      due_set: paperPreview.due_set,
    };
    if (paperPreviewKind === "runner") {
      request.max_sessions = paperPreview.payload.max_sessions;
      request.max_runtime_minutes = paperPreview.payload.max_runtime_minutes;
    }

    paperActionInFlight.current = true;
    const controller = new AbortController();
    paperAdmissionController.current = controller;
    setPaperActionBusy(true);
    setPaperAdmissionWaiting(true);
    setFeedback(null);
    try {
      const remembered = await pendingOperations.remember(pendingRequest, controller.signal);
      setPaperAdmissionWaiting(false);
      if (controller.signal.aborted || activeFundName.current !== name) {
        if (remembered) pendingOperations.forget(pendingRequest);
        return;
      }
      if (!remembered) {
        setFeedback({ tone: "danger", message: "The request identity could not be preserved or another request is unresolved. No operation was submitted." });
        setPaperPreview(null);
        setPaperPreviewKind(null);
        return;
      }
      const receipt = await apiPost<unknown>(
        `/api/paper/${encodeURIComponent(name)}/${paperPreviewKind === "tick" ? "tick" : "runner"}`,
        request,
      );
      const operation = requireMutationOperationReceipt(receipt, pendingRequest, pendingRequest.requestId);
      const saved = pendingOperations.save(pendingRequest, operation.id) && persistPaperOperationId(name, operation.id);
      if (saved) pendingOperations.forget(pendingRequest);
      if (activeFundName.current !== name) return;
      setOperationId(operation.id);
      setPaperPreview(null);
      setPaperPreviewKind(null);
      setFeedback({
        tone: saved ? "neutral" : "danger",
        message: !saved
          ? "Browser storage could not preserve the operation monitor. The request identity remains saved."
          : paperPreviewKind === "tick" && paperPreview.outcome === "nothing-due"
            ? "Reviewed no-work result accepted. Completion status will confirm that nothing was due; no session will run."
          : paperPreviewKind === "tick"
            ? "Reviewed one-session paper tick accepted. Progress is durable and will reload with this page."
            : "Reviewed finite runner start accepted. Process control remains limited to this server-owned child.",
      });
      runnerResource.refresh();
    } catch (cause) {
      if (isPreAdmissionDenial(cause, pendingRequest.requestId)) pendingOperations.forget(pendingRequest);
      if (activeFundName.current === name) {
        fail(cause, "Paper operation outcome could not be confirmed.");
        setPaperPreview(null);
        setPaperPreviewKind(null);
      }
    } finally {
      if (paperAdmissionController.current === controller) paperAdmissionController.current = null;
      paperActionInFlight.current = false;
      setPaperAdmissionWaiting(false);
      setPaperActionBusy(false);
    }
  }

  function dismissPaperPreview(): void {
    if (paperActionBusy && !paperAdmissionWaiting) return;
    paperAdmissionController.current?.abort();
    setPaperPreview(null);
    setPaperPreviewKind(null);
  }

  async function stopOwnedRunner(): Promise<void> {
    if (!canStopRunner || paperActionInFlight.current) return;
    paperActionInFlight.current = true;
    setPaperActionBusy(true);
    setFeedback(null);
    try {
      await apiPost(`/api/paper/${encodeURIComponent(name)}/runner/stop`);
      setStopRunnerDialogOpen(false);
      setFeedback({ tone: "neutral", message: "Owned runner stop requested. An in-flight session may finish before it exits." });
      runnerResource.refresh();
    } catch (cause) {
      fail(cause, "Runner stop request failed.");
      setStopRunnerDialogOpen(false);
    } finally {
      paperActionInFlight.current = false;
      setPaperActionBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Portfolio / paper fund"
        title={name || "Paper fund"}
        description={data ? `${data.universe.join(" · ")} · ${data.cadence} · ${data.broker} book` : "Local ledger inspection and safe paper controls."}
        actions={
          <>
            <Button asChild variant="secondary"><Link to="/paper"><ArrowLeft className="h-3.5 w-3.5" /> All paper funds</Link></Button>
            <Button asChild variant="outline"><Link to={`/paper/${encodeURIComponent(name)}/scorecard`}>Scorecard <ArrowRight className="h-3.5 w-3.5" /></Link></Button>
            <LifecycleActions kind="deployment" identity={name} onComplete={() => navigate("/paper")} />
          </>
        }
      />
      <PendingOperationRecovery
        items={pendingOperations.items}
        saved={pendingOperations.saved}
        error={pendingOperations.error}
        onRefresh={pendingOperations.refresh}
        onForget={pendingOperations.forget}
        onMonitor={(item) => {
          if (!persistPaperOperationId(name, item.operationId)) {
            setFeedback({ tone: "danger", message: "Browser storage could not preserve the operation monitor." });
            return;
          }
          setOperationId(item.operationId);
        }}
        onForgetSaved={pendingOperations.forgetSaved}
        onObserve={pendingOperations.observe}
        onRecovered={(item, operation) => {
          if (item.subjectId !== name || !pendingOperations.save(item, operation.id)) return false;
          setOperationId(operation.id);
          if (!persistPaperOperationId(name, operation.id)) return false;
          runnerResource.refresh();
          return pendingOperations.forget(item);
        }}
      />
      {resource.loading ? <div className="h-52 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /> : null}
      {data ? (
        <>
          {!data.ledger.ok ? (
            <Alert tone="danger" className="mb-5">
              <strong>{data.recovery_state === "reconciliation_required" ? "Reconciliation required." : "Paper state unavailable."}</strong>{" "}
              <span>{data.ledger.error}</span>
            </Alert>
          ) : null}
          {writeUnavailable ? (
            <Alert tone="warning" className="mb-5">
              Root enrollment: <span className="mono">{enrollmentState}</span>. Writes unavailable: <span className="mono">{capabilities?.write_unavailable_reason}</span>.
            </Alert>
          ) : null}
          {capabilities?.operator_trust_warning ? (
            <Alert tone="warning" className="mb-5" data-testid="operator-trust-warning">
              <strong>Trusted single-writer mode.</strong> {capabilities.operator_trust_warning}
            </Alert>
          ) : null}
          {data.halt_state === "unreadable" ? (
            <Alert tone="warning" className="mb-5">Halt state is unreadable. Paper controls and approval writes are disabled.</Alert>
          ) : null}
          {data.broker === "paper" && (data.ledger.ok || data.recovery_state === "reconciliation_required") && (
            data.halt_state === "halted" || data.recovery_state === "reconciliation_required" || intentPreview?.required
          ) ? (
            <Card className="mb-5" data-testid="paper-reconciliation">
              <CardHeader><CardTitle>Paper recovery review</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                {reconciliationResource.loading ? <LoadingState label="Checking local paper recovery state" /> : null}
                {reconciliationResource.apiError ? (
                  <ErrorNotice error={reconciliationResource.apiError} onAction={() => recover(reconciliationResource.apiError as ActionableError)} />
                ) : null}
                {recovery ? (
                  <>
                    {data.halt_state === "halted" && recovery.preview.required ? (
                      <>
                        <p className="font-medium">Ambiguous tick failure</p>
                        <p className="text-xs leading-relaxed text-muted-foreground">
                          Failed request <span className="mono">{recovery.preview.failed_request_id ?? "unavailable"}</span>
                          {" · "}operation <span className="mono">{shortHash(recovery.preview.operation_id)}</span>
                        </p>
                        <div className="grid gap-2 text-xs sm:grid-cols-2">
                          <p>Expected ledger head: <span className="mono">{shortHash(recovery.preview.expected_head)}</span></p>
                          <p>Current ledger head: <span className="mono">{shortHash(recovery.preview.current_head)}</span></p>
                          <p>Local paper book digest: <span className="mono">{shortHash(recovery.preview.broker_book_sha256)}</span></p>
                          <p>Recorded fill digest: <span className="mono">{shortHash(recovery.preview.fill_identity_sha256)}</span></p>
                          <p>Capture identity: <span className="mono">{shortHash(recovery.preview.capture_id)}</span></p>
                          <p>Recovery preview: <span className="mono">{shortHash(recovery.preview.preview_digest)}</span></p>
                        </div>
                        {recovery.resume_allowed ? (
                          <Alert tone="warning">
                            The local paper book matches full ledger replay. Resume records a reconciliation receipt and clears Halt only. It never retries the failed tick or starts a runner.
                          </Alert>
                        ) : (
                          <Alert tone="danger">
                            Resume denied. Halt remains active. Current check: <span className="mono">{recovery.preview.reason}</span>.
                          </Alert>
                        )}
                      </>
                    ) : data.halt_state === "halted" ? (
                      <p className="text-xs leading-relaxed text-muted-foreground">
                        Manual Halt only. No ambiguous tick failure requires reconciliation. Resume clears Halt without running a paper operation or starting a runner.
                      </p>
                    ) : null}
                    {recovery.resume_completion_required ? (
                      <Alert tone="warning">
                        Resume control write already landed. Complete the journal record only; no control write or paper operation will run.
                      </Alert>
                    ) : null}
                    {intentPreview?.required ? (
                      <div className="space-y-3 border-t border-border pt-3" data-testid="tick-intent-reconciliation">
                        <p className="font-medium">{approvalConsumptionOnly ? "Unmatched approval consumption" : "Orphaned paper tick intent"}</p>
                        {intentPreview.reason === "multiple-unresolved-tick-intents" && !selectedIntentDigest ? (
                          <>
                            <Alert tone="danger">Multiple unresolved tick intents. Select an individual target by digest before reviewing recovery.</Alert>
                            <div className="space-y-2">
                              {intentTargets.map((target) => (
                                <div key={target.intent_digest} className="space-y-2 rounded-lg border border-border p-3" data-testid="tick-intent-target">
                                  <div className="grid gap-2 text-xs sm:grid-cols-2">
                                    <p>Request: <span className="mono">{target.intent_request_id ?? "unavailable"}</span></p>
                                    <p>Session: <span className="mono">{target.intent_session ?? "unavailable"}</span></p>
                                    <p className="break-all sm:col-span-2">Intent digest: <span className="mono">{target.intent_digest}</span></p>
                                  </div>
                                  <Button onClick={() => setSelectedIntent({ fund: name, digest: target.intent_digest })} disabled={busy}>
                                    Review intent target
                                  </Button>
                                </div>
                              ))}
                            </div>
                          </>
                        ) : (
                          <>
                            {selectedIntentDigest ? (
                              <Button variant="outline" onClick={() => setSelectedIntent(null)} disabled={busy}>
                                Back to intent targets
                              </Button>
                            ) : null}
                            <div className="grid gap-2 text-xs sm:grid-cols-2">
                              <p>Request: <span className="mono">{intentPreview.intent_request_id ?? "unavailable"}</span></p>
                              <p>Session: <span className="mono">{intentPreview.intent_session ?? "unavailable"}</span></p>
                              <p>Intent digest: <span className="mono">{shortHash(intentPreview.intent_digest)}</span></p>
                              <p>Current ledger head: <span className="mono">{shortHash(intentPreview.current_head)}</span></p>
                              <p>Local paper book digest: <span className="mono">{shortHash(intentPreview.broker_book_sha256)}</span></p>
                              <p>Recovery preview: <span className="mono">{shortHash(intentPreview.preview_digest)}</span></p>
                            </div>
                            {canReconcileTickIntent ? (
                              <>
                                <Alert tone="warning">
                                  <p>Full ledger replay matches the local paper book. Confirmation records an audited resolution only; it does not retry the tick or create broker effects.</p>
                                  {intentPreview.approval_journal_event_digests.length > 0 ? (
                                    <div className="mt-2 space-y-1 text-xs">
                                      <p>Approval journal events covered by this receipt:</p>
                                      <ul className="space-y-1">
                                        {intentPreview.approval_journal_event_digests.map((digest) => (
                                          <li key={digest} className="break-all mono">{digest}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  ) : null}
                                </Alert>
                                <Button onClick={() => setIntentRecoveryOpen(true)} disabled={busy}>
                                  {approvalConsumptionOnly ? "Review approval-consumption resolution" : "Review orphaned tick resolution"}
                                </Button>
                              </>
                            ) : (
                              <Alert tone="danger">
                                Tick admission remains fenced. Recovery check: <span className="mono">{intentPreview.reason}</span>.
                              </Alert>
                            )}
                          </>
                        )}
                      </div>
                    ) : null}
                  </>
                ) : null}
              </CardContent>
            </Card>
          ) : null}
          {protectedName ? <Alert tone="warning" className="mb-5">This protected fund can be inspected but not modified through the web desk.</Alert> : null}
          {feedback?.error ? (
            <ErrorNotice className="mb-5" error={feedback.error} onAction={() => recover(feedback.error as ActionableError)} />
          ) : feedback ? <Alert tone={feedback.tone} className="mb-5">{feedback.message}</Alert> : null}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Recorded NAV" value={money(data.nav)} note={data.last_session ? `As of ${dateLabel(data.last_session)}` : "No recorded session"} icon={BadgeDollarSign} />
            <MetricCard label="Available cash" value={money(data.cash)} note="Ledger replay · no live marks" />
            <MetricCard label="Next forecast" value={data.next_run ? dateLabel(data.next_run) : "Unavailable"} note="Schedule estimate only · no process signal" icon={CalendarClock} />
            <MetricCard
              label="Book state"
              value={!data.ledger.ok ? "Unverified" : writeUnavailable ? "Writes unavailable" : data.halt_state === "unreadable" ? "Halt state unknown" : data.halt_state === "halted" ? "Halted" : "Recorded"}
            note={writeUnavailable ? `${enrollmentState} · ${capabilities?.write_unavailable_reason}` : data.halt_state === "unreadable" ? "Halt state cannot be verified." : runner?.available ? "Owned runner active" : runner?.reason ?? "Runner state unavailable."}
              tone={!data.ledger.ok ? "negative" : writeUnavailable || data.halt_state === "unreadable" || data.halt_state === "halted" ? "warning" : "positive"}
              icon={data.halt_state === "halted" ? CirclePause : ShieldCheck}
            />
          </div>

          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1.55fr)_minmax(300px,0.75fr)]">
            <div className="min-w-0 space-y-5">
              <EquityChart data={data.curve} title="Recorded NAV vs benchmark" />
              <Card>
                <CardHeader>
                  <SectionTitle title="Holdings" note="Position marks recorded in the latest session only" />
                </CardHeader>
                <CardContent>
                  <PositionsTable positions={data.positions} />
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <SectionTitle
                    title="Session ledger"
                    note={`${sessionResource.data?.total ?? data.sessions.length} verified records`}
                  />
                </CardHeader>
                <CardContent>
                  <form
                    className="mb-4 flex max-w-xl gap-2"
                    onSubmit={submitSessionSearch}
                    role="search"
                    aria-label="Search session history"
                  >
                    <Input
                      aria-label="Search sessions or hashes"
                      maxLength={128}
                      onChange={(event) => setSessionSearchText(event.target.value)}
                      placeholder="Search sessions or hashes"
                      type="search"
                      value={sessionSearchText}
                    />
                    <Button type="submit" variant="secondary" disabled={sessionResource.loading}>Search</Button>
                  </form>
                  {sessionResource.error ? <ErrorState message={sessionResource.error} error={sessionResource.apiError} onRetry={sessionResource.refresh} /> : null}
                  {sessionResource.data?.errors.length ? (
                    <Alert tone="warning" className="mb-4">
                      {sessionResource.data.errors.map((item) => (
                        <p key={item.id}><span className="mono">{item.id}</span><span className="px-2 opacity-50">/</span>{item.error}</p>
                      ))}
                    </Alert>
                  ) : null}
                  {sessionResource.loading ? <LoadingState label="Loading session history" /> : null}
                  {sessionResource.data && !sessionResource.data.ledger.ok && sessionResource.data.errors.length === 0 ? (
                    <ErrorState message={sessionResource.data.ledger.error ?? "Session ledger verification failed."} />
                  ) : null}
                  {sessionResource.data?.ledger.ok && !sessionResource.loading && !sessionResource.error ? (
                    <PaperSessionDays name={name} sessions={sessionResource.data.items} search={sessionResource.data.search} />
                  ) : null}
                  <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
                    <p className="text-xs text-muted-foreground">Page {sessionCursorStack.length}</p>
                    <div className="flex gap-2">
                      <Button
                        disabled={sessionCursorStack.length <= 1 || sessionResource.loading}
                        onClick={() => setSessionCursorStack((current) => current.slice(0, -1))}
                        variant="secondary"
                      >
                        Previous
                      </Button>
                      <Button
                        disabled={!sessionResource.data?.next_cursor || sessionResource.loading}
                        onClick={() => {
                          const nextCursor = sessionResource.data?.next_cursor;
                          if (nextCursor) {
                            setSessionCursorStack((current) => [...current, nextCursor]);
                          }
                        }}
                        variant="secondary"
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
            <div className="space-y-5">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>Control panel</CardTitle>
                    <Badge
                      variant={
                        data.halt_state !== "clear" || runner?.status === "unknown"
                          ? "warning"
                          : runner?.available
                            ? "positive"
                            : "muted"
                      }
                    >
                      {data.halt_state === "unreadable"
                        ? "Halt state unknown"
                        : data.halt_state === "halted"
                          ? "Halted"
                          : runnerStatusLabel(runner)}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Enrollment: <span className="mono">{enrollmentState}</span>.{" "}
                    {pendingOperations.blocked
                      ? "Resolve or inspect the pending operation request before starting another paper operation."
                      : writeUnavailable
                      ? `Writes unavailable: ${capabilities?.write_unavailable_reason}.`
                      : runner?.reason ?? "Runner ownership verified by this server."}
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="danger" onClick={() => { setFeedback(null); setHaltDialogOpen(true); }} disabled={!canWritePaper || data.halt_state !== "clear"}>
                      <CirclePause className="h-3.5 w-3.5" /> Halt
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => setConfirmAction("resume")}
                      disabled={!canResumePaper}
                      title={!data.ledger.ok && data.recovery_state !== "reconciliation_required" ? "Resume requires a valid, replayable ledger." : recovery?.preview.required && !recovery.resume_allowed ? "Current paper state is not reconcilable." : undefined}
                    >
                      <CirclePlay className="h-3.5 w-3.5" /> {recovery?.resume_completion_required ? "Complete Resume" : recovery?.preview.required ? "Review recovery" : "Resume"}
                    </Button>
                  </div>
                  <div className="border-t border-border pt-3">
                    <p className="mono text-[9px] uppercase tracking-[0.16em] text-muted-foreground">Runner controls</p>
                    <p className="mt-2 text-[11px] leading-relaxed text-muted-foreground">
                      Paper mutations require explicit review, exact ledger head, free market data, and the captured local Ollama model. Stop requests never signal an unknown process.
                    </p>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <div className="space-y-1">
                        <Label htmlFor="runner-max-sessions" className="text-[10px] text-muted-foreground">Session cap</Label>
                        <Input
                          id="runner-max-sessions"
                          type="number"
                          min={1}
                          max={100}
                          step={1}
                          value={maxSessions}
                          onChange={(event) => setMaxSessions(event.target.value)}
                          disabled={!canOperatePaper || paperActionBusy}
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="runner-max-runtime" className="text-[10px] text-muted-foreground">Deadline · minutes</Label>
                        <Input
                          id="runner-max-runtime"
                          type="number"
                          min={1}
                          max={1440}
                          step={1}
                          value={maxRuntimeMinutes}
                          onChange={(event) => setMaxRuntimeMinutes(event.target.value)}
                          disabled={!canOperatePaper || paperActionBusy}
                        />
                      </div>
                      <Button
                        variant="outline"
                        onClick={() => void requestPaperPreview("runner")}
                        disabled={!canOperatePaper || paperActionBusy}
                        title={runner?.reason ?? "Review finite local-paper runner bounds."}
                      >
                        Start runner
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => setStopRunnerDialogOpen(true)}
                        disabled={!canStopRunner || paperActionBusy}
                        title={!canStopRunner ? (runner?.reason ?? "No owned active runner is available.") : "Request a cooperative stop."}
                      >
                        {runner?.status === "stopping" ? "Stop requested" : "Stop runner"}
                      </Button>
                      <Button
                        className="col-span-2"
                        onClick={() => void requestPaperPreview("tick")}
                        disabled={!canOperatePaper || paperActionBusy}
                        title={runner?.reason ?? "Review exactly one due paper session."}
                      >
                        Manual one-session tick
                      </Button>
                    </div>
                    {!canOperatePaper ? (
                      <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground">
                        {writeUnavailable
                          ? `Unavailable: ${capabilities?.write_unavailable_reason}.`
                          : capabilities?.network !== true
                            ? "Enable startup network capability for free market-data preflight."
                            : data.halt_state !== "clear"
                              ? "Paper operations require a verified clear halt state."
                              : !data.ledger.ok
                                ? "Paper operations require a replayable ledger."
                                : data.broker !== "paper"
                                  ? "Only local-paper deployments are supported."
                                  : runner?.status === "unknown"
                                    ? runner.reason
                                    : "An owned runner or manual session is already active."}
                      </p>
                    ) : null}
                    {runner ? (
                      <p className="mono mt-2 text-[10px] text-muted-foreground">
                        {runner.sessions_completed ?? 0}/{runner.max_sessions ?? "—"} sessions ·{" "}
                        {runner.last_session ? dateLabel(runner.last_session) : "no session recorded"}
                        {runner.expires_at ? ` · deadline ${dateLabel(runner.expires_at)}` : ""}
                      </p>
                    ) : null}
                    {operation ? <PaperOperationStatus operation={operation} /> : null}
                    {unexpectedOperation ? (
                      <Alert tone="warning" className="mt-3">
                        <p>The remembered operation is not a paper tick or runner start. Inspect its durable status before forgetting it.</p>
                        <p className="mono mt-1 break-all text-[9px]">{unexpectedOperation.id}</p>
                        <Button className="mt-2" size="sm" variant="secondary" onClick={forgetPaperOperation}>Forget operation</Button>
                      </Alert>
                    ) : staleOperation ? (
                      <Alert tone="warning" className="mt-3">
                        <p>The remembered operation {shortHash(operationId ?? "")} is no longer known to this server. Its outcome is recorded in the ledger and session history.</p>
                        <Button className="mt-2" size="sm" variant="secondary" onClick={forgetPaperOperation}>Forget operation</Button>
                      </Alert>
                    ) : operationResource.apiError ? (
                      <ErrorNotice className="mt-3" error={operationResource.apiError} onAction={operationResource.refresh} actionLabel="Inspect status" />
                    ) : null}
                    {runnerResource.apiError ? <ErrorNotice className="mt-3" error={runnerResource.apiError} onAction={runnerResource.refresh} /> : null}
                  </div>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>Estimated value</CardTitle>
                    <Badge variant={liveValue?.status === "estimated" ? "positive" : liveValue?.status === "unavailable" ? "muted" : "warning"}>
                      {liveValue?.status ?? "unavailable"}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <p className="mono text-xl text-muted-foreground">{estimateMoney(liveValue?.value ?? null)}</p>
                  {liveValue?.value ? <p className="mono break-all text-[10px] text-muted-foreground">Exact estimate · {liveValue.value}</p> : null}
                  {liveValue?.partial_estimate ? <p className="mono text-xs text-warning">Partial only · {liveValue.partial_estimate}</p> : null}
                  <p className="text-xs leading-relaxed text-muted-foreground">{liveValue?.reason ?? "No valuation estimate is available."}</p>
                  <p className="text-[10px] text-muted-foreground">
                    Recorded NAV {money(data.nav)} remains unchanged. Quote time is provider observation time; exchange print freshness is unverified.
                  </p>
                  {liveValue ? (
                    <>
                      <p className="mono text-[10px] text-muted-foreground">
                        {liveValue.provenance ?? "No source"} · {liveValue.coverage.usable}/{liveValue.coverage.total} within observation limit
                        {liveValue.as_of ? ` · ${liveValue.as_of}` : ""}
                      </p>
                      {liveValue.quotes.length > 0 ? (
                        <ul className="space-y-1 border-t border-border pt-2">
                          {liveValue.quotes.map((quote) => (
                            <li key={quote.ticker} className="flex flex-wrap justify-between gap-x-3 text-[10px]">
                              <span className="mono">{quote.ticker} · {quote.status} · freshness {quote.freshness}</span>
                              <span className="mono text-muted-foreground">
                                {quote.price ?? "No mark"}{quote.quote_time ? ` · ${quote.quote_time}` : ""}
                              </span>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </>
                  ) : null}
                  {capabilities?.network === true ? (
                    <Button
                      variant="outline"
                      onClick={() => void refreshValuation()}
                      disabled={!canRefreshValuation || valuationBusy}
                      aria-busy={valuationBusy}
                    >
                      {valuationBusy ? "Refreshing quotes…" : "Refresh estimate"}
                    </Button>
                  ) : (
                    <p className="text-[10px] text-muted-foreground">Refresh disabled; server network capability is off.</p>
                  )}
                  <p className="text-[10px] text-muted-foreground">
                    Explicit request only · free Yahoo provider · maximum 25 ticker calls · no ledger writes.
                  </p>
                </CardContent>
              </Card>

              <PendingDecisionCard
                pending={data.pending}
                approval={data.approval}
                approvalRequired={approvalRequired}
                haltState={data.halt_state}
                ledgerOk={data.ledger.ok}
                enabled={canApprove}
                onVerdict={(verdict) => setConfirmAction(verdict)}
              />
            </div>
          </div>
        </>
      ) : null}

      <ConfirmDialog
        open={confirmAction !== null}
        onOpenChange={(open) => { if (!open) setConfirmAction(null); }}
        title={confirmTitle(confirmAction, recovery)}
        description={confirmDescription(confirmAction, data?.pending, recovery)}
        confirmLabel={confirmAction === "approve" ? "Approve displayed decision" : confirmAction === "reject" ? "Reject displayed decision" : recovery?.resume_completion_required ? "Complete Resume" : recovery?.preview.required ? "Confirm recovery and resume" : "Record resume"}
        destructive={confirmAction === "reject"}
        busy={busy}
        onConfirm={() => void submitAction()}
      />
      <ConfirmDialog
        open={intentRecoveryOpen}
        onOpenChange={setIntentRecoveryOpen}
        title={approvalConsumptionOnly ? "Resolve unmatched approval consumption" : "Resolve orphaned paper tick"}
        description={approvalConsumptionOnly
          ? "Record an explicit, audited verdict that the local paper book matches the ledger. This resolves the listed approval journal entries only; it never retries a tick."
          : "Record an explicit, audited verdict that the local paper book matches the ledger. This clears the intent fence only; it never retries a tick."}
        confirmLabel={approvalConsumptionOnly ? "Record approval resolution" : "Record intent resolution"}
        busy={busy}
        onConfirm={() => void submitIntentRecovery()}
      />
      <Dialog
        open={paperPreview !== null}
        onOpenChange={(open) => {
          if (!open) dismissPaperPreview();
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {paperPreviewKind === "tick" ? "Confirm one-session paper tick" : "Confirm finite runner start"}
            </DialogTitle>
            <DialogDescription>
              No paper write occurs until you accept. The server rechecks the exact ledger head and due-set.
            </DialogDescription>
          </DialogHeader>
          {paperPreview ? (
            <div className="space-y-3 rounded-lg border border-border bg-black/10 p-3">
              <p className="text-xs">
                Ledger head: <span className="mono">{paperPreview.expected_head ? shortHash(paperPreview.expected_head) : "empty ledger"}</span>
              </p>
              <p className="text-xs">
                Reviewed due-set:{" "}
                <span className="mono">
                  {paperPreviewKind === "tick" && paperPreview.outcome === "nothing-due"
                    ? "No session is due. Accept records a completed no-work result; no session will be created."
                    : nothingDueLabel(paperPreview.due_set) ?? paperPreview.due_set.map(dateLabel).join(" · ")}
                </span>
              </p>
              <p className="text-xs">
                Data: <span className="mono">{paperPreview.estimate.market_data_provider}</span> · model calls/session{" "}
                <span className="mono">{paperPreview.estimate.maximum_model_calls_per_session}</span>
              </p>
              {paperPreviewKind === "runner" ? (
                <p className="text-xs">
                  Bound: <span className="mono">{String(paperPreview.payload.max_sessions)} sessions / {String(paperPreview.payload.max_runtime_minutes)} minutes</span>
                  {" · "}
                  <span className="mono">{paperPreview.estimate.maximum_calls} calls / {paperPreview.estimate.maximum_resources} resources max</span>
                </p>
              ) : null}
              <p className="mono text-[10px] text-muted-foreground">
                Maximum provider cost: ${paperPreview.estimate.maximum_cost_usd.toFixed(2)} · expires {dateLabel(paperPreview.expires_at)}
              </p>
              {paperPreview.warnings.map((warning) => (
                <p key={warning} className="text-[10px] leading-relaxed text-muted-foreground">{warning}</p>
              ))}
            </div>
          ) : null}
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={dismissPaperPreview}
              disabled={paperActionBusy && !paperAdmissionWaiting}
            >
              Cancel
            </Button>
            <Button
              onClick={() => void acceptPaperPreview()}
              disabled={!paperPreview || !canOperatePaper || paperActionBusy}
            >
              {paperActionBusy
                ? "Accepting…"
                : paperPreviewKind === "tick"
                  ? paperPreview?.outcome === "nothing-due" ? "Accept no-work result" : "Accept one-session tick"
                  : "Accept finite runner"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={stopRunnerDialogOpen}
        onOpenChange={setStopRunnerDialogOpen}
        title={`Stop owned runner for ${name}`}
        description="This writes a cooperative stop request to the exact server-owned runner. An in-flight session can finish; unknown PIDs are never signalled."
        confirmLabel="Request runner stop"
        busy={paperActionBusy}
        onConfirm={() => void stopOwnedRunner()}
      />
      <Dialog open={haltDialogOpen} onOpenChange={setHaltDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Halt {name}</DialogTitle>
            <DialogDescription>Records a halt reason in the canonical ledger. It does not stop or signal a runner process.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="halt-reason">Reason</Label>
            <Input id="halt-reason" value={haltReason} onChange={(event) => setHaltReason(event.target.value)} maxLength={240} placeholder="Describe the operator concern" />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setHaltDialogOpen(false)} disabled={busy}>Cancel</Button>
            <Button variant="danger" onClick={() => void submitHalt()} disabled={busy || !canWritePaper}>{busy ? "Recording…" : "Record halt"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

async function submitVerdict(name: string, verdict: "approve" | "reject", pending: PendingDecision, requestId: string): Promise<void> {
  await apiPost(`/api/paper/${encodeURIComponent(name)}/approval`, {
    request_id: requestId,
    verdict,
    decision_as_of: pending.decision_as_of,
    source_record_hash: pending.source_record_hash,
  });
}

function paperOperationStorageKey(name: string): string {
  return `aihf.paper.${encodeURIComponent(name)}.operation`;
}

function readPaperOperationId(name: string): string | null {
  try {
    const stored = window.localStorage.getItem(paperOperationStorageKey(name));
    return stored && /^[a-f0-9]{32}$/.test(stored) ? stored : null;
  } catch {
    return null;
  }
}

function persistPaperOperationId(name: string, operationId: string): boolean {
  try {
    if (/^[a-f0-9]{32}$/.test(operationId)) {
      window.localStorage.setItem(paperOperationStorageKey(name), operationId);
      return window.localStorage.getItem(paperOperationStorageKey(name)) === operationId;
    }
    return false;
  } catch {
    return false;
  }
}

function clearPaperOperationId(name: string): void {
  try {
    window.localStorage.removeItem(paperOperationStorageKey(name));
  } catch {
    return;
  }
}

function newRequestId(): string {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function confirmTitle(action: PendingAction | null, recovery?: PaperReconciliation | null): string {
  if (action === "approve") return "Approve pending decision";
  if (action === "reject") return "Reject pending decision";
  if (recovery?.resume_completion_required) return "Complete Resume";
  if (recovery?.preview.required) return "Reconcile and resume paper fund";
  return "Resume paper fund";
}

function confirmDescription(
  action: PendingAction | null,
  pending: PendingDecision | null | undefined,
  recovery?: PaperReconciliation | null,
): string {
  if (action === "approve" || action === "reject") {
    return pending
      ? `This verdict is bound to ${pending.decision_as_of} and source ${shortHash(pending.source_record_hash)}. A changed decision will be rejected by the server.`
      : "No pending decision is currently displayed.";
  }
  if (recovery?.preview.required) {
    return `Receipt binds failure ${shortHash(recovery.preview.failure_id)} to local book ${shortHash(recovery.preview.broker_book_sha256)} and preview ${shortHash(recovery.preview.preview_digest)}. Failed tick will not be retried. No runner will be started.`;
  }
  if (recovery?.resume_completion_required) {
    return "Resume control write already landed. This records completion only; it does not repeat the control write or run a paper operation.";
  }
  return "This clears Halt only. It does not run a paper operation or start a runner.";
}

function PendingDecisionCard({
  pending,
  approval,
  approvalRequired,
  haltState,
  ledgerOk,
  enabled,
  onVerdict,
}: {
  pending: PendingDecision | null;
  approval: Approval | null;
  approvalRequired: boolean;
  haltState: HaltState;
  ledgerOk: boolean;
  enabled: boolean;
  onVerdict: (verdict: "approve" | "reject") => void;
}) {
  if (!pending) {
    return (
      <Card>
        <CardHeader><CardTitle>Pending decision</CardTitle></CardHeader>
        <CardContent>
          <EmptyState
            title={!ledgerOk ? "Decision unavailable" : approvalRequired ? "No decision awaiting approval" : "No approval gate"}
            description={!ledgerOk
              ? "Paper state must be verified before a decision can be reviewed."
              : approvalRequired
              ? "A decision appears here only when it is recorded in the local ledger."
              : "This mandate does not require approval; execution can proceed without a verdict."}
          />
        </CardContent>
      </Card>
    );
  }
  const weights = Object.entries(pending.final_weights).sort(([left], [right]) => left.localeCompare(right));
  const halted = haltState === "halted";
  const haltUnreadable = haltState === "unreadable";
  const status = !ledgerOk ? "Decision unavailable" : !approvalRequired ? "Approval not required" : haltUnreadable ? "Halt state unknown" : halted ? "Halted" : approval ? approval.verdict : "Awaiting verdict";
  const statusVariant = !ledgerOk || !approvalRequired || halted || haltUnreadable ? "muted" : approval ? (approval.verdict === "approve" ? "positive" : "negative") : "warning";
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <CardTitle>Pending decision</CardTitle>
            <p className="mono mt-1 text-[10px] text-muted-foreground">{pending.decision_as_of}</p>
          </div>
          <Badge variant={statusVariant}>{status}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="rounded-lg border border-border bg-black/10 p-3">
          <p className="mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">Source record</p>
          <p className="mono mt-1 break-all text-[10px] text-foreground">{pending.source_record_hash}</p>
        </div>
        <div className="space-y-2">
          <p className="mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">Final target weights</p>
          {weights.length > 0 ? weights.map(([ticker, weight]) => (
            <div key={ticker} className="flex items-center justify-between border-b border-border/70 pb-2 text-xs">
              <span className="mono text-foreground">{ticker}</span>
              <span className={`mono ${weight < 0 ? "text-rose-300" : "text-emerald-300"}`}>{pct(weight)}</span>
            </div>
          )) : <p className="text-xs text-muted-foreground">No non-zero target positions.</p>}
        </div>
        <p className="text-[10px] text-muted-foreground">Strategies: {pending.strategies.join(" · ") || "—"}</p>
        {!approvalRequired ? <p className="text-[10px] leading-relaxed text-muted-foreground">This mandate does not require approval. Its recorded decision is not waiting for a verdict.</p> : null}
        {approvalRequired && halted ? <p className="text-[10px] leading-relaxed text-muted-foreground">Halted funds cannot accept a verdict.</p> : null}
        {approvalRequired && haltUnreadable ? <p className="text-[10px] leading-relaxed text-muted-foreground">Halt state cannot be verified. Verdicts are disabled.</p> : null}
        <div className="grid grid-cols-2 gap-2">
          <Button onClick={() => onVerdict("approve")} disabled={!enabled}>Approve</Button>
          <Button variant="danger" onClick={() => onVerdict("reject")} disabled={!enabled}>Reject</Button>
        </div>
        {!enabled && approvalRequired && haltState === "clear" ? <p className="text-[10px] leading-relaxed text-muted-foreground">{ledgerOk ? "Verdict writes require startup write capability and a non-protected fund name." : "Paper state must be verified before verdicts can be saved."}</p> : null}
      </CardContent>
    </Card>
  );
}

function PositionsTable({ positions }: { positions: Position[] }) {
  const columns: TableColumn<Position>[] = [
    { key: "ticker", label: "Ticker", render: (item) => <span className="mono font-medium text-foreground">{item.ticker}</span> },
    { key: "shares", label: "Shares", align: "right", render: (item) => <span className="mono">{item.shares.toLocaleString("en-US")}</span> },
    { key: "mark", label: "Last recorded mark", align: "right", render: (item) => <span className="mono">{money(item.mark, 2)}</span> },
    { key: "value", label: "Recorded value", align: "right", render: (item) => <span className="mono text-foreground">{money(item.market_value)}</span> },
  ];
  return <DataTable columns={columns} rows={positions} rowKey={(item) => item.ticker} emptyTitle="No recorded positions" emptyDescription="Positions appear after a session is persisted." />;
}

function estimateMoney(value: string | null): string {
  if (value === null) return "—";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? money(numeric) : value;
}

export function PaperScorecardPage() {
  const { name = "" } = useParams();
  const resource = useResource<ScoreMetrics>(name ? `/api/paper/${encodeURIComponent(name)}/scorecard` : null);
  const card = resource.data;
  const analystColumns: TableColumn<ScoreMetrics["analysts"][number]>[] = [
    { key: "name", label: "Analyst", render: (item) => <span className="mono text-foreground">{item.name}</span> },
    { key: "views", label: "Views", align: "right", render: (item) => <span className="mono">{item.n_views}</span> },
    { key: "directional", label: "Directional", align: "right", render: (item) => <span className="mono">{item.n_directional}</span> },
    { key: "hit", label: "Hit rate", align: "right", render: (item) => <span className="mono">{pct(item.hit_rate)}</span> },
    { key: "ic", label: "Mean IC", align: "right", render: (item) => <span className="mono">{item.ic_mean?.toFixed(3) ?? "—"}</span> },
  ];
  const strategyColumns: TableColumn<ScoreMetrics["strategies"][number]>[] = [
    { key: "name", label: "Strategy", render: (item) => <span className="mono text-foreground">{item.name}</span> },
    { key: "periods", label: "Periods", align: "right", render: (item) => <span className="mono">{item.n_periods}</span> },
    { key: "pnl", label: "P&L", align: "right", render: (item) => <span className="mono">{money(item.pnl)}</span> },
    { key: "return", label: "Return", align: "right", render: (item) => <span className="mono">{pct(item.return_pct)}</span> },
    { key: "share", label: "Share of P&L", align: "right", render: (item) => <span className="mono">{pct(item.share_of_pnl)}</span> },
    { key: "drawdown", label: "Max drawdown", align: "right", render: (item) => <span className="mono text-rose-300">{pct(item.max_drawdown_pct)}</span> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Portfolio / scorecard"
        title={`${name} scorecard`}
        description={card ? `Ledger attribution · ${dateLabel(card.first_session)} through ${dateLabel(card.last_session)}` : "Performance attribution from recorded local sessions."}
        actions={<Button asChild variant="secondary"><Link to={`/paper/${encodeURIComponent(name)}`}><ArrowLeft className="h-3.5 w-3.5" /> Paper fund</Link></Button>}
      />
      {resource.loading ? <div className="h-48 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /> : null}
      {card ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Fund P&L" value={money(card.fund_pnl)} note="Attributed over scored records" tone={card.fund_pnl >= 0 ? "positive" : "negative"} />
            <MetricCard label="Trading cost" value={money(card.trading_cost, 2)} note="Recorded commissions and slippage" />
            <MetricCard label="Unattributed" value={money(card.unattributed)} note="Residual not assigned to a strategy" />
            <MetricCard label="Score horizon" value={card.horizon ?? "Not enough data"} note={`${dateLabel(card.first_session)} → ${dateLabel(card.last_session)}`} />
          </div>
          <div className="mt-5 grid gap-5">
            <Card>
              <CardHeader><SectionTitle title="Analyst scorecard" note="Only observed analyst views are counted" /></CardHeader>
              <CardContent><DataTable columns={analystColumns} rows={card.analysts} rowKey={(item) => item.name} emptyTitle="No analyst attribution" emptyDescription="Analyst views were not present in the scored records." /></CardContent>
            </Card>
            <Card>
              <CardHeader><SectionTitle title="Strategy attribution" note="P&L and drawdown use the canonical scorecard" /></CardHeader>
              <CardContent><DataTable columns={strategyColumns} rows={card.strategies} rowKey={(item) => item.name} emptyTitle="No strategy attribution" emptyDescription="No strategy periods are available in the current ledger." /></CardContent>
            </Card>
          </div>
        </>
      ) : null}
    </>
  );
}

export function SessionReportPage() {
  const { name = "", session = "" } = useParams();
  const resource = useResource<SessionReport>(
    name && session ? `/api/paper/${encodeURIComponent(name)}/sessions/${encodeURIComponent(session)}` : null,
  );
  const report = resource.data;
  const orders = report?.executed?.orders ?? [];
  const fills = report?.executed?.fills ?? [];
  const orderColumns: TableColumn<(typeof orders)[number]>[] = [
    { key: "ticker", label: "Ticker", render: (item) => <span className="mono text-foreground">{item.ticker}</span> },
    { key: "side", label: "Side", render: (item) => <Badge variant={item.side === "buy" ? "positive" : "warning"}>{item.side}</Badge> },
    { key: "quantity", label: "Quantity", align: "right", render: (item) => <span className="mono">{item.quantity}</span> },
    { key: "price", label: "Price", align: "right", render: (item) => <span className="mono">{money(item.price, 2)}</span> },
  ];
  const proposed = report?.proposed;
  const weights = proposed
    ? [...new Set([...Object.keys(proposed.target_weights), ...Object.keys(proposed.final_weights)])]
      .sort()
      .map((ticker) => ({
        ticker,
        requested: proposed.target_weights[ticker],
        final: proposed.final_weights[ticker],
      }))
    : [];
  const weightColumns: TableColumn<(typeof weights)[number]>[] = [
    { key: "ticker", label: "Ticker", render: (item) => <span className="mono text-foreground">{item.ticker}</span> },
    { key: "requested", label: "Requested weight (pre-risk)", align: "right", render: (item) => <span className="mono">{pct(item.requested)}</span> },
    { key: "final", label: "Final weight (post-risk)", align: "right", render: (item) => <span className="mono">{pct(item.final)}</span> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Portfolio / session report"
        title={report ? dateLabel(report.session) : dateLabel(session)}
        description={`${name} · immutable ledger session · executed and proposed records stay separate`}
        actions={
          <>
            <Button asChild variant="secondary"><Link to={`/paper/${encodeURIComponent(name)}`}><ArrowLeft className="h-3.5 w-3.5" /> Paper fund</Link></Button>
            {report ? (
              <Button asChild variant="secondary">
                <a href={`/api/paper/${encodeURIComponent(name)}/sessions/${encodeURIComponent(session)}/download?expected_hash=${encodeURIComponent(report.hash)}`}>
                  <Download className="h-3.5 w-3.5" /> Download canonical JSON
                </a>
              </Button>
            ) : null}
          </>
        }
      />
      {resource.loading ? <div className="h-48 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /> : null}
      {report ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Session NAV" value={money(report.nav)} note="Persisted close value" />
            <MetricCard label="Cash" value={money(report.cash)} note="Ledger balance after session" />
            <MetricCard label="Benchmark" value={report.benchmark} note={money(report.benchmark_close, 2)} />
            <MetricCard label="Rebalance" value={report.rebalance ? "Yes" : "No"} note={`Record ${shortHash(report.hash)}`} icon={FileText} />
          </div>
          {report.executed ? (
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard label="Trading cost" value={money(report.executed.trading_cost, 2)} note="Recorded modeled execution cost" />
              <MetricCard label="Traded notional" value={money(report.executed.traded_notional, 2)} note="Executed quantity × price" />
              <MetricCard label="Commission" value={money(report.executed.commission, 2)} note="Recorded commission total" />
              <MetricCard label="Slippage" value={money(report.executed.slippage, 2)} note="Recorded spread and slippage cost" />
            </div>
          ) : null}
          <div className="mt-5 grid gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader><SectionTitle title="Executed orders" note="Orders persisted in this session's execution record" /></CardHeader>
              <CardContent><DataTable ariaLabel="Executed orders table" columns={orderColumns} rows={orders} rowKey={(item, index) => `${item.ticker}-${item.side}-${index}`} emptyTitle="No executed orders" emptyDescription="No order was recorded for this session." /></CardContent>
            </Card>
            <Card>
              <CardHeader><SectionTitle title="Executed fills" note="Only filled quantities and prices appear here" /></CardHeader>
              <CardContent><DataTable ariaLabel="Executed fills table" columns={orderColumns} rows={fills} rowKey={(item, index) => `${item.ticker}-${item.side}-${index}`} emptyTitle="No fills recorded" emptyDescription="No fill was recorded for this session." /></CardContent>
            </Card>
          </div>
          <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
            <Card>
              <CardHeader>
                <CardTitle>Proposed decision</CardTitle>
                <p className="text-xs text-muted-foreground">{report.proposed ? `Targets only · assessed ${dateLabel(report.proposed.as_of)}` : "No proposal stored in this session."}</p>
              </CardHeader>
              <CardContent>
                {report.proposed ? (
                  <div className="space-y-4">
                    <DataTable ariaLabel="Proposed weights table" columns={weightColumns} rows={weights} rowKey={(item) => item.ticker} emptyTitle="No targets" emptyDescription="The decision contained no target weights." />
                    <p className="text-[10px] text-muted-foreground">Target universe: {report.proposed.universe.join(" · ")}</p>
                    <RecordedRisk label="Proposed risk" limits={report.proposed.risk} clamps={report.proposed.clamps} scaleFactor={report.proposed.risk_scale_factor} />
                    <div className="space-y-3 border-t border-border pt-4">
                      <p className="mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">Analyst evidence</p>
                      {report.proposed.strategies.map((strategy) => (
                        <div key={strategy.name} className="rounded-lg border border-border bg-black/10 p-3">
                          <p className="mono text-[10px] font-medium text-foreground">{strategy.name}</p>
                          {strategy.signals.length ? (
                            <div className="mt-2 space-y-2">
                              {strategy.signals.map((signal, index) => (
                                <div key={`${signal.model_name}-${signal.ticker}-${index}`} className="border-t border-border/70 pt-2">
                                  <div className="flex items-center justify-between gap-3 text-[10px]">
                                    <span className="mono text-muted-foreground">{signal.model_name} · {signal.ticker}</span>
                                    <span className="mono text-foreground">{signal.value.toFixed(3)}</span>
                                  </div>
                                  {signal.reasoning ? <p className="mt-1 break-words text-xs leading-relaxed text-muted-foreground">{signal.reasoning}</p> : null}
                                </div>
                              ))}
                            </div>
                          ) : <p className="mt-2 text-[10px] text-muted-foreground">No signal text recorded.</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                ) : <EmptyState title="No proposed decision" description="This record contains no separate target proposal." />}
              </CardContent>
            </Card>
            <div className="min-w-0 space-y-5">
              <Card>
                <CardHeader><CardTitle>Executed risk</CardTitle></CardHeader>
                <CardContent>
                  {report.executed
                    ? <RecordedRisk label="Executed risk" limits={report.executed.spec.risk} clamps={report.executed.clamps} scaleFactor={report.executed.risk_scale_factor} />
                    : <EmptyState title="No executed decision" description="No execution risk record was stored in this session." />}
                </CardContent>
              </Card>
              <Card>
                <CardHeader><CardTitle>Audit identity</CardTitle></CardHeader>
                <CardContent className="space-y-3">
                  <HashRow label="Record hash" value={report.hash} />
                  <HashRow label="Previous hash" value={report.prev_hash} />
                  <HashRow label="Mandate hash" value={report.mandate_hash} />
                  <p className="border-t border-border pt-3 text-[10px] text-muted-foreground">Code version: <span className="mono">{report.code_version}</span></p>
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}

function RecordedRisk({ label, limits, clamps, scaleFactor }: {
  label: "Proposed risk" | "Executed risk";
  limits: RiskLimitsDto;
  clamps: ClampEventDto[];
  scaleFactor: number | null;
}) {
  const columns: TableColumn<ClampEventDto>[] = [
    { key: "limit", label: "Limit", render: (item) => item.limit === "max_position_pct" ? "Position limit" : "Gross exposure" },
    { key: "ticker", label: "Scope", render: (item) => <span className="mono">{item.ticker ?? "Portfolio"}</span> },
    { key: "before", label: "Before", align: "right", render: (item) => <span className="mono">{pct(item.before)}</span> },
    { key: "after", label: "After", align: "right", render: (item) => <span className="mono">{pct(item.after)}</span> },
  ];
  return (
    <section aria-label={label} className="space-y-3 border-t border-border pt-3">
      <h3 className="text-xs font-medium text-foreground">{label}</h3>
      <p className="text-[10px] text-muted-foreground">Recorded limits and events, not a new risk assessment.</p>
      <div className="mono space-y-1 text-[11px] text-muted-foreground">
        <p>Max position: {pct(limits.max_position_pct)}</p>
        <p>Max gross exposure: {pct(limits.max_gross_exposure)}</p>
        {scaleFactor !== null ? <p>Risk scale factor: {pct(scaleFactor)}</p> : <p>No common scale factor recorded.</p>}
      </div>
      <DataTable
        ariaLabel={`${label} clamps table`}
        columns={columns}
        rows={clamps}
        rowKey={(item, index) => `${item.limit}-${item.ticker}-${index}`}
        emptyTitle={label === "Proposed risk" ? "No proposed clamps" : "No executed clamps"}
        emptyDescription="The stored record contains no clamp events."
      />
    </section>
  );
}

function HashRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">{label}</p>
      <p className="mono mt-1 break-all text-[10px] text-foreground">{value ?? "—"}</p>
    </div>
  );
}
