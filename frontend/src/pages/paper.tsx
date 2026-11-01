import {
  ArrowLeft,
  ArrowRight,
  BadgeDollarSign,
  CalendarClock,
  CirclePause,
  CirclePlay,
  FileCheck2,
  FileText,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ConfirmDialog } from "@/components/confirm-dialog";
import { DataTable, type TableColumn } from "@/components/data-table";
import { EquityChart } from "@/components/equity-chart";
import { MetricCard } from "@/components/metric-card";
import { EmptyState, ErrorState, PageHeader, SectionTitle } from "@/components/page";
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
import { apiPost } from "@/lib/api";
import { useDesk, useResource } from "@/lib/hooks";
import type {
  Approval,
  HaltState,
  LiveValuation,
  PaperCollection,
  PaperOperationPreview,
  PaperSnapshot,
  PaperSummary,
  PendingDecision,
  Operation,
  Position,
  RunnerState,
  ScoreMetrics,
  SessionReport,
  SessionSummary,
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
            <Badge variant="warning">Runner unverified</Badge>
          ) : item.runner.available ? (
            <Badge variant="positive">Runner {item.runner.status}</Badge>
          ) : (
            <Badge variant="muted">Runner {item.runner.status}</Badge>
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
      {resource.error ? <ErrorState message={resource.error} /> : null}
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
    </>
  );
}

type PendingAction = "approve" | "reject" | "resume";

export function PaperDetailPage() {
  const { name = "" } = useParams();
  const { capabilities } = useDesk();
  const resource = useResource<PaperSnapshot>(name ? `/api/paper/${encodeURIComponent(name)}` : null);
  const runnerResource = useResource<RunnerState>(
    name ? `/api/paper/${encodeURIComponent(name)}/runner` : null,
  );
  const [operationId, setOperationId] = useState<string | null>(null);
  const operationResource = useResource<Operation>(
    operationId ? `/api/operations/${encodeURIComponent(operationId)}` : null,
  );
  const [confirmAction, setConfirmAction] = useState<PendingAction | null>(null);
  const [haltDialogOpen, setHaltDialogOpen] = useState(false);
  const [haltReason, setHaltReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [paperActionBusy, setPaperActionBusy] = useState(false);
  const [paperPreview, setPaperPreview] = useState<PaperOperationPreview | null>(null);
  const [paperPreviewKind, setPaperPreviewKind] = useState<"tick" | "runner" | null>(null);
  const [stopRunnerDialogOpen, setStopRunnerDialogOpen] = useState(false);
  const [maxSessions, setMaxSessions] = useState("1");
  const [maxRuntimeMinutes, setMaxRuntimeMinutes] = useState("60");
  const [valuationBusy, setValuationBusy] = useState(false);
  const [valuationResult, setValuationResult] = useState<LiveValuation | null>(null);
  const [feedback, setFeedback] = useState<{ tone: "danger" | "neutral"; message: string } | null>(null);
  const valuationRequest = useRef(0);
  const paperActionInFlight = useRef(false);
  const refreshedOperation = useRef<string | null>(null);
  const protectedName = capabilities?.protected_names.some((entry) => entry.toLowerCase() === name.toLowerCase()) ?? false;
  const canWrite = capabilities?.writes === true && !protectedName;
  const data = resource.data;
  const writeUnavailable = capabilities?.write_unavailable_reason != null;
  const enrollmentState = capabilities?.enrollment_state ?? "unenrolled";
  const runner = runnerResource.data ?? data?.runner;
  const operation = operationResource.data?.id === operationId ? operationResource.data : null;
  const approvalRequired = data?.spec.approval_required === true;
  const canApprove = canWrite && approvalRequired && data?.halt_state === "clear" && data?.ledger.ok === true;
  const canRefreshValuation = canWrite && capabilities?.network === true && data?.ledger.ok === true;
  const liveValue = valuationResult ?? data?.live_value;
  const paperOperationActive = Boolean(
    operation && ["accepted", "running", "cancel-requested"].includes(operation.status),
  );
  const runnerInactive = Boolean(
    runner
    && !runner.available
    && ["stopped", "completed", "failed"].includes(runner.status),
  );
  const canOperatePaper = Boolean(
    canWrite
    && capabilities?.network === true
    && data?.broker === "paper"
    && data.ledger.ok
    && data.halt_state === "clear"
    && runnerInactive
    && !paperOperationActive,
  );
  const canStopRunner = Boolean(
    canWrite
    && runner?.available
    && runner.status === "running",
  );

  useEffect(() => {
    valuationRequest.current += 1;
    setValuationResult(null);
    setValuationBusy(false);
  }, [name, data?.last_record_hash]);

  useEffect(() => {
    setOperationId(readPaperOperationId(name));
    setPaperPreview(null);
    setPaperPreviewKind(null);
  }, [name]);

  useEffect(() => {
    if (!operation || !["accepted", "running", "cancel-requested"].includes(operation.status)) return;
    const timer = window.setTimeout(operationResource.refresh, 900);
    return () => window.clearTimeout(timer);
  }, [operation?.status, operation?.progress, operationResource.refresh]);

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
        await submitVerdict(name, confirmAction, pending);
        setFeedback({ tone: "neutral", message: `Verdict ${confirmAction} was saved to the local approval mailbox. It does not execute immediately.` });
      } else {
        await apiPost(`/api/paper/${encodeURIComponent(name)}/resume`);
        setFeedback({ tone: "neutral", message: "Resume request recorded. The web desk does not start or control the runner." });
      }
      setConfirmAction(null);
      resource.refresh();
    } catch (cause) {
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Action failed." });
    } finally {
      setBusy(false);
    }
  }

  async function submitHalt(): Promise<void> {
    const reason = haltReason.trim();
    if (!reason) {
      setFeedback({ tone: "danger", message: "Enter a reason before halting this fund." });
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      await apiPost(`/api/paper/${encodeURIComponent(name)}/halt`, { reason });
      setHaltDialogOpen(false);
      setHaltReason("");
      setFeedback({ tone: "neutral", message: "Halt state recorded in the ledger. Runner process control is not available here." });
      resource.refresh();
    } catch (cause) {
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Halt request failed." });
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
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Valuation refresh failed." });
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
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Paper preview failed." });
    } finally {
      paperActionInFlight.current = false;
      setPaperActionBusy(false);
    }
  }

  async function acceptPaperPreview(): Promise<void> {
    if (!paperPreview || !paperPreviewKind || !canOperatePaper || paperActionInFlight.current) return;
    const request: Record<string, unknown> = {
      request_id: newRequestId(),
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
    setPaperActionBusy(true);
    setFeedback(null);
    try {
      const operation = await apiPost<Operation>(
        `/api/paper/${encodeURIComponent(name)}/${paperPreviewKind === "tick" ? "tick" : "runner"}`,
        request,
      );
      setOperationId(operation.id);
      persistPaperOperationId(name, operation.id);
      setPaperPreview(null);
      setPaperPreviewKind(null);
      setFeedback({
        tone: "neutral",
        message: paperPreviewKind === "tick"
          ? "Reviewed one-session paper tick accepted. Progress is durable and will reload with this page."
          : "Reviewed finite runner start accepted. Process control remains limited to this server-owned child.",
      });
      runnerResource.refresh();
    } catch (cause) {
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Paper operation was not accepted." });
      setPaperPreview(null);
      setPaperPreviewKind(null);
    } finally {
      paperActionInFlight.current = false;
      setPaperActionBusy(false);
    }
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
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Runner stop request failed." });
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
          </>
        }
      />
      {resource.loading ? <div className="h-52 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} /> : null}
      {data ? (
        <>
          {!data.ledger.ok ? <Alert tone="danger" className="mb-5"><strong>Ledger verification failed.</strong> <span>{data.ledger.error}</span></Alert> : null}
          {writeUnavailable ? (
            <Alert tone="warning" className="mb-5">
              Root enrollment: <span className="mono">{enrollmentState}</span>. Writes unavailable: <span className="mono">{capabilities?.write_unavailable_reason}</span>.
            </Alert>
          ) : null}
          {data.halt_state === "unreadable" ? (
            <Alert tone="warning" className="mb-5">Halt state is unreadable. Paper controls and approval writes are disabled.</Alert>
          ) : null}
          {protectedName ? <Alert tone="warning" className="mb-5">This protected fund can be inspected but not modified through the web desk.</Alert> : null}
          {feedback ? <Alert tone={feedback.tone} className="mb-5">{feedback.message}</Alert> : null}

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
                  <SectionTitle title="Session ledger" note={`${data.sessions.length} most recent records`} />
                </CardHeader>
                <CardContent>
                  <SessionsTable name={name} sessions={data.sessions} />
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
                          : runner?.status === "unknown"
                            ? "Runner unverified"
                            : `Runner ${runner?.status ?? "unavailable"}`}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    Enrollment: <span className="mono">{enrollmentState}</span>.{" "}
                    {writeUnavailable
                      ? `Writes unavailable: ${capabilities?.write_unavailable_reason}.`
                      : runner?.reason ?? "Runner ownership verified by this server."}
                  </p>
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="danger" onClick={() => { setFeedback(null); setHaltDialogOpen(true); }} disabled={!canWrite || data.halt_state !== "clear"}>
                      <CirclePause className="h-3.5 w-3.5" /> Halt
                    </Button>
                    <Button
                      variant="secondary"
                      onClick={() => setConfirmAction("resume")}
                      disabled={!canWrite || data.halt_state !== "halted" || !data.ledger.ok}
                      title={!data.ledger.ok ? "Resume requires a valid, replayable ledger." : undefined}
                    >
                      <CirclePlay className="h-3.5 w-3.5" /> Resume
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
                    {operation ? (
                      <div className="mt-4 rounded-lg border border-border bg-black/10 p-3" aria-live="polite">
                        <div className="flex items-center justify-between gap-3">
                          <span className="mono text-[10px] text-foreground">
                            {operation.action === "paper-tick" ? "Manual tick" : "Runner start"} · {operation.status}
                          </span>
                          <span className="mono text-[10px] text-muted-foreground">{Math.min(100, Math.max(0, operation.progress))}%</span>
                        </div>
                        <div
                          className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"
                          role="progressbar"
                          aria-label="Paper operation progress"
                          aria-valuenow={Math.min(100, Math.max(0, operation.progress))}
                          aria-valuemin={0}
                          aria-valuemax={100}
                        >
                          <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${Math.min(100, Math.max(0, operation.progress))}%` }} />
                        </div>
                        <p className="mono mt-2 break-all text-[9px] text-muted-foreground">{operation.id}</p>
                        {operation.error ? <p className="mt-2 text-[10px] text-rose-300">{operation.error}</p> : null}
                      </div>
                    ) : null}
                    {operationResource.error ? <Alert tone="warning" className="mt-3">{operationResource.error}</Alert> : null}
                    {runnerResource.error ? <Alert tone="warning" className="mt-3">{runnerResource.error}</Alert> : null}
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
        title={confirmTitle(confirmAction)}
        description={confirmDescription(confirmAction, data?.pending)}
        confirmLabel={confirmAction === "approve" ? "Approve displayed decision" : confirmAction === "reject" ? "Reject displayed decision" : "Record resume"}
        destructive={confirmAction === "reject"}
        busy={busy}
        onConfirm={() => void submitAction()}
      />
      <Dialog
        open={paperPreview !== null}
        onOpenChange={(open) => {
          if (!open && !paperActionBusy) {
            setPaperPreview(null);
            setPaperPreviewKind(null);
          }
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
                  {paperPreview.due_set.length > 0
                    ? paperPreview.due_set.map(dateLabel).join(" · ")
                    : "No session due now; runner waits for the next eligible session."}
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
              onClick={() => { setPaperPreview(null); setPaperPreviewKind(null); }}
              disabled={paperActionBusy}
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
                  ? "Accept one-session tick"
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
            <Button variant="danger" onClick={() => void submitHalt()} disabled={busy || !canWrite}>{busy ? "Recording…" : "Record halt"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

async function submitVerdict(name: string, verdict: "approve" | "reject", pending: PendingDecision): Promise<void> {
  await apiPost(`/api/paper/${encodeURIComponent(name)}/approval`, {
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

function persistPaperOperationId(name: string, operationId: string): void {
  try {
    window.localStorage.setItem(paperOperationStorageKey(name), operationId);
  } catch {
    return;
  }
}

function newRequestId(): string {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function confirmTitle(action: PendingAction | null): string {
  if (action === "approve") return "Approve pending decision";
  if (action === "reject") return "Reject pending decision";
  return "Resume paper fund";
}

function confirmDescription(action: PendingAction | null, pending: PendingDecision | null | undefined): string {
  if (action === "approve" || action === "reject") {
    return pending
      ? `This verdict is bound to ${pending.decision_as_of} and source ${shortHash(pending.source_record_hash)}. A changed decision will be rejected by the server.`
      : "No pending decision is currently displayed.";
  }
  return "This only records the ledger resume state. It does not start or control a runner.";
}

function PendingDecisionCard({
  pending,
  approval,
  approvalRequired,
  haltState,
  enabled,
  onVerdict,
}: {
  pending: PendingDecision | null;
  approval: Approval | null;
  approvalRequired: boolean;
  haltState: HaltState;
  enabled: boolean;
  onVerdict: (verdict: "approve" | "reject") => void;
}) {
  if (!pending) {
    return (
      <Card>
        <CardHeader><CardTitle>Pending decision</CardTitle></CardHeader>
        <CardContent>
          <EmptyState
            title={approvalRequired ? "No decision awaiting approval" : "No approval gate"}
            description={approvalRequired
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
  const status = !approvalRequired ? "Approval not required" : haltUnreadable ? "Halt state unknown" : halted ? "Halted" : approval ? approval.verdict : "Awaiting verdict";
  const statusVariant = !approvalRequired || halted || haltUnreadable ? "muted" : approval ? (approval.verdict === "approve" ? "positive" : "negative") : "warning";
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
        {!enabled && approvalRequired && haltState === "clear" ? <p className="text-[10px] leading-relaxed text-muted-foreground">Verdict writes require startup write capability and a non-protected fund name.</p> : null}
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

function SessionsTable({ name, sessions }: { name: string; sessions: SessionSummary[] }) {
  const columns: TableColumn<SessionSummary>[] = [
    {
      key: "session",
      label: "Session",
      render: (item) => <Link className="mono text-foreground hover:text-accent hover:underline" to={`/paper/${encodeURIComponent(name)}/sessions/${encodeURIComponent(item.session)}`}>{dateLabel(item.session)}</Link>,
    },
    { key: "nav", label: "NAV", align: "right", render: (item) => <span className="mono text-foreground">{money(item.nav)}</span> },
    { key: "cash", label: "Cash", align: "right", render: (item) => <span className="mono">{money(item.cash)}</span> },
    { key: "orders", label: "Orders / fills", align: "right", render: (item) => <span className="mono">{item.orders} / {item.fills}</span> },
    { key: "hash", label: "Record hash", render: (item) => <span className="mono" title={item.hash}>{shortHash(item.hash)}</span> },
  ];
  return <DataTable columns={columns} rows={[...sessions].reverse()} rowKey={(item) => item.session} emptyTitle="No verified sessions" emptyDescription="The ledger has no session records to display." />;
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
      {resource.error ? <ErrorState message={resource.error} /> : null}
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
  const weightColumns: TableColumn<[string, number]>[] = [
    { key: "ticker", label: "Ticker", render: ([ticker]) => <span className="mono text-foreground">{ticker}</span> },
    { key: "weight", label: "Target weight", align: "right", render: ([, weight]) => <span className="mono">{pct(weight)}</span> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Portfolio / session report"
        title={report ? dateLabel(report.session) : dateLabel(session)}
        description={`${name} · immutable ledger session · executed and proposed records stay separate`}
        actions={<Button asChild variant="secondary"><Link to={`/paper/${encodeURIComponent(name)}`}><ArrowLeft className="h-3.5 w-3.5" /> Paper fund</Link></Button>}
      />
      {resource.loading ? <div className="h-48 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} /> : null}
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
                    <DataTable columns={weightColumns} rows={Object.entries(report.proposed.final_weights).sort(([a], [b]) => a.localeCompare(b))} rowKey={([ticker]) => ticker} emptyTitle="No targets" emptyDescription="The decision contained no target weights." />
                    <p className="text-[10px] text-muted-foreground">Target universe: {report.proposed.universe.join(" · ")}</p>
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
        </>
      ) : null}
    </>
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
