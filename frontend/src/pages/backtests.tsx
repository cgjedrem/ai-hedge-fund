import { AlertCircle, ArrowRight, CircleStop, Clock3, FlaskConical, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type TableColumn } from "@/components/data-table";
import { ErrorState, PageHeader, SectionTitle } from "@/components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiPost } from "@/lib/api";
import { useDesk, useResource } from "@/lib/hooks";
import type { Job, MandateCollection, Settings } from "@/lib/types";
import { dateLabel } from "@/lib/utils";

interface BacktestSubmission {
  fund: string;
  universe: string[];
  start: string;
  end: string;
  provider: string;
  model: string;
  mandate_hash: string;
  agent_count: number;
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function BacktestsPage() {
  const { capabilities } = useDesk();
  const mandates = useResource<MandateCollection>("/api/mandates");
  const settings = useResource<Settings>("/api/settings");
  const jobs = useResource<{ items: Job[] }>("/api/jobs");
  const [jobId, setJobId] = useState<string | null>(null);
  const currentJob = useResource<Job>(jobId ? `/api/jobs/${encodeURIComponent(jobId)}` : null);
  const [fund, setFund] = useState("");
  const [universeText, setUniverseText] = useState("");
  const [start, setStart] = useState(() => {
    const date = new Date();
    date.setUTCFullYear(date.getUTCFullYear() - 1);
    return isoDate(date);
  });
  const [end, setEnd] = useState(() => isoDate(new Date()));
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [confirmation, setConfirmation] = useState<BacktestSubmission | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canWrite = capabilities?.writes === true;
  const canRun = canWrite && capabilities?.network === true;
  const activeJob = currentJob.data;
  const selectedMandate = mandates.data?.items.find((item) => item.name === fund) ?? null;
  const selectedModel = settings.data?.models.find((item) => item.id === settings.data?.model) ?? null;
  const running = Boolean(activeJob && ["queued", "running"].includes(activeJob.status));

  useEffect(() => {
    if (!activeJob || !["queued", "running"].includes(activeJob.status)) return;
    const timer = window.setTimeout(currentJob.refresh, 1200);
    return () => window.clearTimeout(timer);
  }, [activeJob?.status, activeJob?.progress, currentJob.refresh]);

  useEffect(() => {
    if (!fund && mandates.data?.items.length) setFund(mandates.data.items[0].name);
  }, [fund, mandates.data]);

  const jobColumns = useMemo<TableColumn<Job>[]>(
    () => [
      { key: "fund", label: "Mandate", render: (item) => <span className="mono text-foreground">{item.fund}</span> },
      { key: "provider", label: "Provider / model", render: (item) => <span className="text-xs">{item.provider} · {item.model}</span> },
      { key: "submitted", label: "Submitted", render: (item) => <span className="mono text-[10px]">{dateLabel(item.submitted_at)}</span> },
      { key: "status", label: "Status", render: (item) => <JobStatus status={item.status} /> },
      { key: "progress", label: "Progress", align: "right", render: (item) => <span className="mono">{Math.min(100, Math.max(0, item.progress))}%</span> },
    ],
    [],
  );

  function requestConfirmation(): void {
    setError(null);
    if (!canRun) {
      setError("Backtests require startup write capability and explicit network consent.");
      return;
    }
    const universe = universeText
      .split(/[,\s]+/)
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean);
    if (!fund || universe.length === 0) {
      setError("Choose a mandate and enter at least one ticker.");
      return;
    }
    if (universe.length > 20 || universe.some((ticker) => !/^[A-Z0-9.^-]{1,16}$/.test(ticker)) || new Set(universe).size !== universe.length) {
      setError("Use 1–20 unique tickers with up to 16 ASCII letters, digits, dots, carets, or hyphens.");
      return;
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(start) || !/^\d{4}-\d{2}-\d{2}$/.test(end) || end < start || (Date.parse(end) - Date.parse(start)) / 86_400_000 > 730) {
      setError("Choose valid dates in chronological order within a 730-day maximum range.");
      return;
    }
    if (!selectedMandate || !settings.data || !selectedModel) {
      setError("Mandate and provider settings must finish loading before confirmation.");
      return;
    }
    setConfirmation({
      fund,
      universe,
      start,
      end,
      provider: settings.data.data_provider,
      model: settings.data.model,
      mandate_hash: selectedMandate.mandate_hash,
      agent_count: selectedMandate.agent_count,
    });
  }

  async function submitConfirmed(): Promise<void> {
    if (!confirmation) return;
    if (!canRun) {
      setError("Backtests require both startup write capability and explicit network consent.");
      setConfirmation(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const job = await apiPost<Job>("/api/backtests", {
        fund: confirmation.fund,
        universe: confirmation.universe,
        start: confirmation.start,
        end: confirmation.end,
        provider: confirmation.provider,
        model: confirmation.model,
        mandate_hash: confirmation.mandate_hash,
      });
      setJobId(job.id);
      setConfirmation(null);
      jobs.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Backtest could not be submitted.");
    } finally {
      setBusy(false);
    }
  }

  async function cancelActiveJob(): Promise<void> {
    if (!activeJob || !running || !canWrite || cancelling) return;
    setCancelling(true);
    setError(null);
    try {
      await apiPost(`/api/jobs/${encodeURIComponent(activeJob.id)}/cancel`);
      currentJob.refresh();
      jobs.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Cancellation request failed.");
    } finally {
      setCancelling(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Research / backtests"
        title="Backtest jobs"
        description="Submit one bounded historical research job. External data access requires both startup writes and explicit network consent."
        actions={<Button asChild variant="secondary"><Link to="/research">Saved reports <ArrowRight className="h-3.5 w-3.5" /></Link></Button>}
      />
      {error ? <Alert tone="danger" className="mb-5"><AlertCircle className="mr-2 inline h-4 w-4" />{error}</Alert> : null}
      {!canRun && capabilities ? (
        <Alert tone="warning" className="mb-5">
          Backtests are disabled. Start a separate local server with explicit <span className="mono">--allow-writes --enable-network</span> only when you intend to use historical data providers.
        </Alert>
      ) : null}
      {mandates.error ? <div className="mb-5"><ErrorState message={mandates.error} /></div> : null}
      {mandates.data?.errors.length ? (
        <Alert tone="warning" className="mb-5">
          {mandates.data.errors.map((item) => `${item.name}: ${item.error}`).join(" · ")}
        </Alert>
      ) : null}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">New research job</p>
                <p className="mt-1 text-xs text-muted-foreground">No automatic retries · single worker · maximum 730 calendar days</p>
              </div>
              <FlaskConical className="h-4 w-4 text-accent" />
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="backtest-fund">Mandate</Label>
                <Select value={fund} onValueChange={setFund} disabled={mandates.loading || !mandates.data?.items.length || running}>
                  <SelectTrigger id="backtest-fund"><SelectValue placeholder="Choose a saved mandate" /></SelectTrigger>
                  <SelectContent>
                    {(mandates.data?.items ?? []).map((item) => <SelectItem key={item.name} value={item.name}>{item.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="backtest-universe">Ticker universe</Label>
                <Input id="backtest-universe" value={universeText} onChange={(event) => setUniverseText(event.target.value)} placeholder="AAPL, MSFT, SPY" disabled={!canRun || running} />
                <p className="text-[10px] text-muted-foreground">Up to 20 unique symbols · the fund benchmark is included by canonical valuation.</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-start">Start date</Label>
                <Input id="backtest-start" type="date" value={start} onChange={(event) => setStart(event.target.value)} disabled={!canRun || running} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="backtest-end">End date</Label>
                <Input id="backtest-end" type="date" value={end} onChange={(event) => setEnd(event.target.value)} disabled={!canRun || running} />
              </div>
            </div>
            <Button className="w-full" onClick={requestConfirmation} disabled={!canRun || busy || mandates.loading || settings.loading || !selectedMandate || !selectedModel || running}>
              <FlaskConical className="h-3.5 w-3.5" /> Review backtest
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Job monitor</p>
                <p className="mt-1 text-xs text-muted-foreground">Progress is reported by the canonical backtest run.</p>
              </div>
              <Clock3 className="h-4 w-4 text-accent" />
            </div>
          </CardHeader>
          <CardContent>
            {currentJob.loading ? <div className="h-28 animate-pulse rounded-lg border border-border bg-white/[0.025]" /> : null}
            {currentJob.error ? <Alert tone="danger">{currentJob.error}</Alert> : null}
            {activeJob ? (
              <div className="rounded-lg border border-border bg-black/10 p-4" aria-live="polite">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="mono text-sm text-foreground">{activeJob.fund}</p>
                    <p className="mono mt-1 text-[9px] text-muted-foreground">{activeJob.id}</p>
                  </div>
                  <JobStatus status={activeJob.status} />
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
                  <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${Math.min(100, Math.max(0, activeJob.progress))}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className="mono text-[10px] text-muted-foreground">{Math.min(100, Math.max(0, activeJob.progress))}%</span>
                  {activeJob.completed_at ? <span className="mono text-[10px] text-muted-foreground">{dateLabel(activeJob.completed_at)}</span> : <RefreshCw className="h-3 w-3 animate-spin text-accent" />}
                </div>
                {activeJob.error ? <Alert tone="danger" className="mt-4">{activeJob.error}</Alert> : null}
                {activeJob.report_id ? (
                  <Button asChild className="mt-4 w-full">
                    <Link to={`/research/${encodeURIComponent(activeJob.report_id)}`}>Open saved report <ArrowRight className="h-3.5 w-3.5" /></Link>
                  </Button>
                ) : null}
                {running ? (
                  <div className="mt-4 space-y-2">
                    <Button
                      className="w-full"
                      variant="danger"
                      onClick={() => void cancelActiveJob()}
                      disabled={!canWrite || cancelling || activeJob.cancel_requested}
                    >
                      <CircleStop className="h-3.5 w-3.5" />
                      {cancelling || activeJob.cancel_requested ? "Cancellation requested…" : "Request cancellation"}
                    </Button>
                    <p className="text-[10px] leading-relaxed text-muted-foreground">
                      Cancellation is cooperative at valuation boundaries. An in-flight provider/session step cannot be interrupted, so cancel and shutdown latency depends on that step. Closing this page does not cancel the job; shutdown waits for active work.
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex min-h-32 flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 text-center">
                <p className="text-xs font-medium text-foreground">No selected job</p>
                <p className="mt-1 text-[10px] text-muted-foreground">Submit a research run to see state and progress here.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader>
          <SectionTitle title="Recent jobs" note={jobs.data ? `${jobs.data.items.length} local job receipts` : "Local job receipts"} />
        </CardHeader>
        <CardContent>
          {jobs.loading ? <div className="h-24 animate-pulse rounded-lg border border-border bg-white/[0.025]" /> : null}
          {jobs.error ? <ErrorState message={jobs.error} /> : null}
          {jobs.data ? (
            <DataTable
              columns={jobColumns}
              rows={jobs.data.items}
              rowKey={(item) => item.id}
              emptyTitle="No jobs submitted"
              emptyDescription="A new job will appear after explicit submission."
            />
          ) : null}
        </CardContent>
      </Card>
      <Dialog open={confirmation !== null} onOpenChange={(open) => { if (!open && !busy) setConfirmation(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm historical backtest</DialogTitle>
            <DialogDescription>
              One research job will use these inputs. No automatic retry runs if it fails.
            </DialogDescription>
          </DialogHeader>
          {confirmation ? (
            <div className="space-y-4">
              <dl className="grid gap-3 rounded-lg border border-border bg-black/10 p-4 text-xs sm:grid-cols-2">
                <ConfirmationValue label="Mandate" value={confirmation.fund} />
                <ConfirmationValue label="Agents" value={String(confirmation.agent_count)} />
                <ConfirmationValue label="Mandate hash" value={confirmation.mandate_hash} />
                <ConfirmationValue label="Market-data provider" value={confirmation.provider} />
                <ConfirmationValue
                  label="LLM model"
                  value={selectedModel ? `${selectedModel.label} · ${selectedModel.provider}` : confirmation.model}
                />
                <ConfirmationValue label="Tickers" value={confirmation.universe.join(", ")} />
                <ConfirmationValue label="Date range" value={`${confirmation.start} → ${confirmation.end}`} />
              </dl>
              <div className="grid gap-2 sm:grid-cols-2" aria-label="Required startup capabilities">
                <CapabilityBadge label="Write capability" enabled={capabilities?.writes === true} />
                <CapabilityBadge label="Network capability" enabled={capabilities?.network === true} />
              </div>
              <p className="text-[10px] leading-relaxed text-muted-foreground">
                Confirm only if both capabilities are enabled and this provider/model/range is intended. A report write already underway is not interrupted by cancellation.
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmation(null)} disabled={busy}>Review later</Button>
            <Button onClick={() => void submitConfirmed()} disabled={busy || !canRun}>
              {busy ? "Submitting…" : "Confirm and submit"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function JobStatus({ status }: { status: Job["status"] }) {
  const variant = status === "succeeded" ? "positive" : status === "failed" ? "negative" : status === "running" ? "warning" : "muted";
  return <Badge variant={variant}>{status}</Badge>;
}

function ConfirmationValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">{label}</dt>
      <dd className="mt-1 break-words text-foreground">{value}</dd>
    </div>
  );
}

function CapabilityBadge({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant={enabled ? "positive" : "negative"}>{enabled ? "Enabled" : "Off"}</Badge>
    </div>
  );
}
