import { AlertCircle, ArrowRight, CircleStop, Clock3, FlaskConical, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { DataTable, type TableColumn } from "@/components/data-table";
import { ErrorNotice, ErrorState, PageHeader, SectionTitle } from "@/components/page";
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
import { toActionableError, type ActionableError } from "@/lib/errors";
import { useDesk, useResource } from "@/lib/hooks";
import type { MandateCollection, Operation, OperationPreview, OperationStatus, Settings } from "@/lib/types";
import { dateLabel } from "@/lib/utils";

const SELECTED_OPERATION_STORAGE_KEY = "aihf.backtests.selected-operation";

function readSelectedOperationId(): string | null {
  try {
    const stored = window.localStorage.getItem(SELECTED_OPERATION_STORAGE_KEY);
    return stored && /^[a-f0-9]{32}$/.test(stored) ? stored : null;
  } catch {
    return null;
  }
}

function persistSelectedOperationId(operationId: string | null): void {
  try {
    if (operationId) window.localStorage.setItem(SELECTED_OPERATION_STORAGE_KEY, operationId);
    else window.localStorage.removeItem(SELECTED_OPERATION_STORAGE_KEY);
  } catch {
    return;
  }
}

function isoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

function newRequestId(): string {
  const bytes = new Uint8Array(16);
  window.crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function BacktestsPage() {
  const { capabilities, reconnect } = useDesk();
  const mandates = useResource<MandateCollection>("/api/mandates");
  const settings = useResource<Settings>("/api/settings");
  const operations = useResource<{ items: Operation[] }>("/api/operations");
  const [operationId, setOperationId] = useState<string | null>(readSelectedOperationId);
  const [operationSelectionRestored, setOperationSelectionRestored] = useState(false);
  const currentOperation = useResource<Operation>(
    operationId ? `/api/operations/${encodeURIComponent(operationId)}` : null,
  );
  const [fund, setFund] = useState("");
  const [universeText, setUniverseText] = useState("");
  const [start, setStart] = useState(() => {
    const date = new Date();
    date.setUTCFullYear(date.getUTCFullYear() - 1);
    return isoDate(date);
  });
  const [end, setEnd] = useState(() => isoDate(new Date()));
  const [authorizePaid, setAuthorizePaid] = useState(false);
  const [confirmFdSelfServicePricing, setConfirmFdSelfServicePricing] = useState(false);
  const [paidMaxCalls, setPaidMaxCalls] = useState("10");
  const [paidMaxCost, setPaidMaxCost] = useState("5.00");
  const [paidMaxAttemptCost, setPaidMaxAttemptCost] = useState("0.25");
  const [busy, setBusy] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [confirmation, setConfirmation] = useState<OperationPreview | null>(null);
  const [error, setError] = useState<string | ActionableError | null>(null);
  const selectOperation = useCallback((selectedId: string | null) => {
    setOperationId(selectedId);
    persistSelectedOperationId(selectedId);
  }, []);
  const canWrite = capabilities?.writes === true;
  const canRun = canWrite && capabilities?.network === true;
  const activeOperation = currentOperation.data?.id === operationId ? currentOperation.data : null;
  const selectedMandate = mandates.data?.items.find((item) => item.name === fund) ?? null;
  const selectedModel = settings.data?.models.find((item) => item.id === settings.data?.model) ?? null;
  const paidProviderNames = [
    ...(settings.data?.data_provider === "fd" ? ["Financial Datasets"] : []),
    ...(settings.data && settings.data.llm_provider !== "Ollama" ? [settings.data.llm_provider] : []),
  ];
  const paidOperation = paidProviderNames.length > 0;
  const minimumAttemptCost = settings.data?.data_provider === "fd"
    ? 0.16
    : selectedModel?.provider === "TypeSafe" && selectedModel.id === "jev-1.13.0"
      ? 0.002688
      : paidOperation ? Number.POSITIVE_INFINITY : 0;
  const costModelDescription = settings.data?.data_provider === "fd"
    ? "Financial Datasets public self-service maximum, including the 8× Credits premium multiplier; custom Enterprise pricing is unsupported."
    : selectedModel?.provider === "TypeSafe" && selectedModel.id === "jev-1.13.0"
      ? "Jev 1.13.0 published input-token rate with a 64K context ceiling; output tokens free; 1 MiB local request cap."
      : "No verified paid cost model; this provider is denied.";
  const paidBudgetValid =
    /^\d+$/.test(paidMaxCalls)
    && Number(paidMaxCalls) >= 1
    && Number(paidMaxCalls) <= 10000
    && /^(?:0|[1-9]\d{0,2})(?:\.\d{1,6})?$/.test(paidMaxCost)
    && Number(paidMaxCost) > 0
    && Number(paidMaxCost) <= 100
    && /^(?:0|[1-9]\d{0,1})(?:\.\d{1,6})?$/.test(paidMaxAttemptCost)
    && Number(paidMaxAttemptCost) > 0
    && Number(paidMaxAttemptCost) >= minimumAttemptCost
    && Number(paidMaxAttemptCost) <= 10
    && Number(paidMaxAttemptCost) <= Number(paidMaxCost);
  const running = Boolean(
    activeOperation
    && ["accepted", "running", "cancel-requested"].includes(activeOperation.status),
  );

  useEffect(() => {
    setAuthorizePaid(false);
    setConfirmFdSelfServicePricing(false);
  }, [settings.data?.data_provider, settings.data?.llm_provider, settings.data?.model, settings.data?.version]);

  useEffect(() => {
    if (!activeOperation || !["accepted", "running", "cancel-requested"].includes(activeOperation.status)) return;
    const timer = window.setTimeout(currentOperation.refresh, 1200);
    return () => window.clearTimeout(timer);
  }, [activeOperation?.status, activeOperation?.progress, currentOperation.refresh]);

  useEffect(() => {
    if (!operations.data || operationSelectionRestored) return;
    const items = operations.data.items;
    const selected = operationId && items.some((item) => item.id === operationId)
      ? operationId
      : items.find((item) => ["accepted", "running", "cancel-requested"].includes(item.status))?.id
        ?? items[0]?.id
        ?? null;
    if (selected !== operationId) selectOperation(selected);
    setOperationSelectionRestored(true);
  }, [operationId, operationSelectionRestored, operations.data, selectOperation]);

  useEffect(() => {
    if (!fund && mandates.data?.items.length) setFund(mandates.data.items[0].name);
  }, [fund, mandates.data]);

  const operationColumns = useMemo<TableColumn<Operation>[]>(
    () => [
      { key: "fund", label: "Mandate", render: (item) => <span className="mono text-foreground">{item.fund}</span> },
      { key: "provider", label: "Provider / model", render: (item) => <span className="text-xs">{item.provider} · {item.model}</span> },
      { key: "submitted", label: "Created", render: (item) => <span className="mono text-[10px]">{dateLabel(item.created_at)}</span> },
      { key: "status", label: "Status", render: (item) => <OperationStatusBadge status={item.status} /> },
      { key: "progress", label: "Progress", align: "right", render: (item) => <span className="mono">{Math.min(100, Math.max(0, item.progress))}%</span> },
      {
        key: "monitor",
        label: "Monitor",
        render: (item) => (
          <Button
            type="button"
            size="sm"
            variant={operationId === item.id ? "secondary" : "ghost"}
            aria-label={`Monitor operation ${item.id}`}
            aria-pressed={operationId === item.id}
            onClick={() => selectOperation(item.id)}
          >
            {operationId === item.id ? "Selected" : "Monitor"}
          </Button>
        ),
      },
    ],
    [operationId, selectOperation],
  );

  async function requestConfirmation(): Promise<void> {
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
    if (paidProviderNames.length > 1) {
      setError("This operation selects two paid providers. Choose a free data provider or local model.");
      return;
    }
    if (settings.data.data_provider === "fd" && !confirmFdSelfServicePricing) {
      setError("Confirm that the Financial Datasets account uses public self-service pricing.");
      return;
    }
    if (paidOperation && (!authorizePaid || !paidBudgetValid)) {
      setError("Explicitly authorize the paid provider with valid per-attempt and total bounds.");
      return;
    }
    const payload = {
      fund,
      universe,
      start,
      end,
      provider: settings.data.data_provider,
      model: settings.data.model,
      mandate_hash: selectedMandate.mandate_hash,
      authorize_paid_provider: paidOperation && authorizePaid,
      ...(settings.data.data_provider === "fd"
        ? { confirm_fd_self_service_pricing: confirmFdSelfServicePricing }
        : {}),
      ...(paidOperation
        ? {
            paid_max_calls: Number(paidMaxCalls),
            paid_max_cost_usd: paidMaxCost,
            paid_max_attempt_cost_usd: paidMaxAttemptCost,
          }
        : {}),
    };
    setBusy(true);
    try {
      const preview = await apiPost<OperationPreview>("/api/operations/preview", {
        action: "backtest",
        subject_id: fund,
        expected_head: selectedMandate.mandate_hash,
        payload,
      });
      setConfirmation(preview);
    } catch (cause) {
      setError(toActionableError(cause, "Backtest preview could not be created."));
    } finally {
      setBusy(false);
    }
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
      const operation = await apiPost<Operation>("/api/operations", {
        request_id: newRequestId(),
        action: confirmation.action,
        subject_id: confirmation.subject_id,
        preview_id: confirmation.preview_id,
        preview_digest: confirmation.preview_digest,
        confirmation_token: confirmation.confirmation_token,
        expected_head: confirmation.expected_head,
        due_set: confirmation.due_set,
        payload: confirmation.payload,
      });
      selectOperation(operation.id);
      setConfirmation(null);
      operations.refresh();
    } catch (cause) {
      setError(toActionableError(cause, "Backtest could not be submitted."));
      setConfirmation(null);
    } finally {
      setBusy(false);
    }
  }

  async function cancelActiveOperation(): Promise<void> {
    if (!activeOperation || !running || !canWrite || cancelling) return;
    setCancelling(true);
    setError(null);
    try {
      await apiPost(
        `/api/operations/${encodeURIComponent(activeOperation.id)}/cancel`,
        { request_id: newRequestId() },
      );
      currentOperation.refresh();
      operations.refresh();
    } catch (cause) {
      setError(toActionableError(cause, "Cancellation request failed."));
    } finally {
      setCancelling(false);
    }
  }

  // Recovery never resubmits; it refreshes reviewed inputs or durable operation status.
  function recover(failure: ActionableError): void {
    if (failure.action === "reconnect") {
      void reconnect();
      return;
    }
    setError(null);
    if (failure.action === "inspect-status") {
      operations.refresh();
      if (operationId) currentOperation.refresh();
      return;
    }
    setConfirmation(null);
    mandates.refresh();
    settings.refresh();
  }

  const staleOperation = Boolean(operationId && currentOperation.apiError?.code === "not-found");

  return (
    <>
      <PageHeader
        eyebrow="Research / backtests"
        title="Backtest operations"
        description="Review a bounded historical research operation. Paid providers require per-operation consent and a finite transport budget."
        actions={<Button asChild variant="secondary"><Link to="/research">Saved reports <ArrowRight className="h-3.5 w-3.5" /></Link></Button>}
      />
      {typeof error === "string" ? <Alert tone="danger" className="mb-5"><AlertCircle className="mr-2 inline h-4 w-4" />{error}</Alert> : null}
      {error && typeof error !== "string" ? <ErrorNotice className="mb-5" error={error} onAction={() => recover(error)} /> : null}
      {!canRun && capabilities ? (
        <Alert tone="warning" className="mb-5">
          Backtests are disabled. Start a separate local server with explicit <span className="mono">--allow-writes --enable-network</span> only when you intend to use historical data providers.
        </Alert>
      ) : null}
      {mandates.error ? <div className="mb-5"><ErrorState message={mandates.error} error={mandates.apiError} onRetry={mandates.refresh} /></div> : null}
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
                <p className="text-sm font-semibold text-foreground">New reviewed operation</p>
                <p className="mt-1 text-xs text-muted-foreground">Server-issued preview · durable request · maximum 730 calendar days</p>
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
                <p className="text-[10px] text-muted-foreground">Up to 20 unique symbols · model-call estimate is bounded before acceptance.</p>
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
            {paidOperation ? (
              <div className="space-y-3 rounded-lg border border-warning/40 bg-warning/5 p-4">
                <div>
                  <p className="text-xs font-semibold text-foreground">Paid provider authorization</p>
                  <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
                    Selected provider: <span className="mono">{paidProviderNames[0] ?? "unknown"}</span>.
                    {` ${costModelDescription} Each transport reserves the declared attempt cap before I/O.`}
                  </p>
                </div>
                <label className="flex items-start gap-2 text-xs text-foreground">
                  <input
                    type="checkbox"
                    checked={authorizePaid}
                    onChange={(event) => setAuthorizePaid(event.target.checked)}
                    disabled={!canRun || running}
                  />
                  I deliberately authorize this paid provider for this reviewed backtest.
                </label>
                {settings.data?.data_provider === "fd" ? (
                  <label className="flex items-start gap-2 text-xs text-foreground">
                    <input
                      type="checkbox"
                      checked={confirmFdSelfServicePricing}
                      onChange={(event) => setConfirmFdSelfServicePricing(event.target.checked)}
                      disabled={!canRun || running}
                    />
                    I confirm this account uses public Financial Datasets self-service pricing, not custom Enterprise rates.
                  </label>
                ) : null}
                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="space-y-1">
                    <Label htmlFor="paid-max-calls">Maximum paid calls</Label>
                    <Input id="paid-max-calls" type="number" min="1" max="10000" step="1" value={paidMaxCalls} onChange={(event) => setPaidMaxCalls(event.target.value)} disabled={!canRun || running} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="paid-max-attempt">Worst-case / attempt ($)</Label>
                    <Input id="paid-max-attempt" type="number" min="0.000001" max="10" step="0.01" value={paidMaxAttemptCost} onChange={(event) => setPaidMaxAttemptCost(event.target.value)} disabled={!canRun || running} />
                  </div>
                  <div className="space-y-1">
                    <Label htmlFor="paid-max-cost">Total operation cap ($)</Label>
                    <Input id="paid-max-cost" type="number" min="0.000001" max="100" step="0.01" value={paidMaxCost} onChange={(event) => setPaidMaxCost(event.target.value)} disabled={!canRun || running} />
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground">Bounds: at most 10,000 calls, $10 per attempt, and $100 total. Per-attempt minimum: ${minimumAttemptCost.toFixed(6)}. Paid automatic retries are denied.</p>
              </div>
            ) : null}
            <Button className="w-full" onClick={() => void requestConfirmation()} disabled={!canRun || busy || mandates.loading || settings.loading || !selectedMandate || !selectedModel || running || (paidOperation && (!authorizePaid || !paidBudgetValid)) || (settings.data?.data_provider === "fd" && !confirmFdSelfServicePricing) || paidProviderNames.length > 1}>
              <FlaskConical className="h-3.5 w-3.5" /> Review backtest
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-foreground">Operation monitor</p>
                <p className="mt-1 text-xs text-muted-foreground">Durable progress survives browser reload and server restart.</p>
              </div>
              <Clock3 className="h-4 w-4 text-accent" />
            </div>
          </CardHeader>
          <CardContent>
            {currentOperation.loading ? <div className="h-28 animate-pulse rounded-lg border border-border bg-white/[0.025]" /> : null}
            {staleOperation ? (
              <Alert tone="warning">
                <p>The remembered operation is no longer known to this server. Saved reports remain under Research.</p>
                <Button className="mt-2" size="sm" variant="secondary" onClick={() => selectOperation(null)}>Forget operation</Button>
              </Alert>
            ) : currentOperation.apiError ? (
              <ErrorNotice error={currentOperation.apiError} onAction={currentOperation.refresh} actionLabel="Inspect status" />
            ) : null}
            {activeOperation ? (
              <div className="rounded-lg border border-border bg-black/10 p-4" aria-live="polite">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="mono text-sm text-foreground">{activeOperation.fund}</p>
                    <p className="mono mt-1 text-[9px] text-muted-foreground">{activeOperation.id}</p>
                  </div>
                  <OperationStatusBadge status={activeOperation.status} />
                </div>
                <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
                  <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${Math.min(100, Math.max(0, activeOperation.progress))}%` }} />
                </div>
                <div className="mt-2 flex items-center justify-between">
                  <span className="mono text-[10px] text-muted-foreground">{Math.min(100, Math.max(0, activeOperation.progress))}%</span>
                  {["completed", "failed", "interrupted", "cancelled"].includes(activeOperation.status)
                    ? <span className="mono text-[10px] text-muted-foreground">{dateLabel(activeOperation.updated_at)}</span>
                    : <RefreshCw className="h-3 w-3 animate-spin text-accent" />}
                </div>
                {activeOperation.error ? <Alert tone="danger" className="mt-4">{activeOperation.error}</Alert> : null}
                {activeOperation.report_id ? (
                  <Button asChild className="mt-4 w-full">
                    <Link to={`/research/${encodeURIComponent(activeOperation.report_id)}`}>Open saved report <ArrowRight className="h-3.5 w-3.5" /></Link>
                  </Button>
                ) : null}
                {running ? (
                  <div className="mt-4 space-y-2">
                    <Button
                      className="w-full"
                      variant="danger"
                      onClick={() => void cancelActiveOperation()}
                      disabled={!canWrite || cancelling || activeOperation.cancel_requested}
                    >
                      <CircleStop className="h-3.5 w-3.5" />
                      {cancelling || activeOperation.cancel_requested ? "Cancellation requested…" : "Request cancellation"}
                    </Button>
                    <p className="text-[10px] leading-relaxed text-muted-foreground">
                      Cancellation is cooperative at valuation boundaries. An in-flight model or data step cannot be interrupted. Closing this page does not cancel the operation; shutdown fences unfinished work.
                    </p>
                  </div>
                ) : null}
              </div>
            ) : (
              <div className="flex min-h-32 flex-col items-center justify-center rounded-lg border border-dashed border-border px-4 text-center">
                <p className="text-xs font-medium text-foreground">No selected operation</p>
                <p className="mt-1 text-[10px] text-muted-foreground">Review and accept a backtest to see durable state and progress here.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-5">
        <CardHeader>
          <SectionTitle title="Recent operations" note={operations.data ? `${operations.data.items.length} durable receipts` : "Durable operation receipts"} />
        </CardHeader>
        <CardContent>
          {operations.loading ? <div className="h-24 animate-pulse rounded-lg border border-border bg-white/[0.025]" /> : null}
          {operations.error ? <ErrorState message={operations.error} error={operations.apiError} onRetry={operations.refresh} /> : null}
          {operations.data ? (
            <DataTable
              columns={operationColumns}
              rows={operations.data.items}
              rowKey={(item) => item.id}
              emptyTitle="No operations submitted"
              emptyDescription="A durable receipt appears after confirmation."
            />
          ) : null}
        </CardContent>
      </Card>
      <Dialog open={confirmation !== null} onOpenChange={(open) => { if (!open && !busy) setConfirmation(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm reviewed backtest</DialogTitle>
            <DialogDescription>
            Accept the exact captured configuration, source head, provider and finite transport budget.
            </DialogDescription>
          </DialogHeader>
          {confirmation ? (
            <div className="space-y-4">
              <dl className="grid gap-3 rounded-lg border border-border bg-black/10 p-4 text-xs sm:grid-cols-2">
                <ConfirmationValue label="Mandate" value={confirmation.payload.fund} />
                <ConfirmationValue label="Reviewed head" value={confirmation.expected_head ?? "none"} />
                <ConfirmationValue label="Preview digest" value={confirmation.preview_digest} />
                <ConfirmationValue label="Market-data provider" value={confirmation.payload.provider} />
                <ConfirmationValue
                  label="LLM model"
                  value={selectedModel ? `${selectedModel.label} · ${selectedModel.provider}` : confirmation.payload.model}
                />
                <ConfirmationValue label="Tickers" value={confirmation.payload.universe.join(", ")} />
                <ConfirmationValue label="Date range" value={`${confirmation.payload.start} → ${confirmation.payload.end}`} />
                <ConfirmationValue label="Max model calls" value={String(confirmation.estimate.maximum_model_calls)} />
                {confirmation.payload.confirm_fd_self_service_pricing ? (
                  <ConfirmationValue label="FD pricing tier" value="Self-service; custom Enterprise pricing unsupported" />
                ) : null}
                <ConfirmationValue label="Paid provider" value={confirmation.estimate.paid_provider ?? "None"} />
                <ConfirmationValue label="Max paid calls" value={String(confirmation.estimate.maximum_paid_calls ?? 0)} />
                <ConfirmationValue label="Max cost" value={`$${(confirmation.estimate.maximum_cost_usd ?? 0).toFixed(6)}`} />
                <ConfirmationValue label="Worst-case / attempt" value={`$${(confirmation.estimate.maximum_attempt_cost_usd ?? 0).toFixed(6)}`} />
                <ConfirmationValue label="Cost model" value={confirmation.estimate.cost_model ?? "None"} />
                <ConfirmationValue label="Expires" value={dateLabel(confirmation.expires_at)} />
              </dl>
              <div className="grid gap-2 sm:grid-cols-2" aria-label="Required startup capabilities">
                <CapabilityBadge label="Write capability" enabled={capabilities?.writes === true} />
                <CapabilityBadge label="Network capability" enabled={capabilities?.network === true} />
              </div>
              <p className="text-[10px] leading-relaxed text-muted-foreground">
                Preview token stays in page memory. Paid authorization binds to this capture, cost model and displayed deadline. Each attempt reserves its declared cap before dispatch.
              </p>
            </div>
          ) : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmation(null)} disabled={busy}>Review later</Button>
            <Button onClick={() => void submitConfirmed()} disabled={busy || !canRun}>
              {busy ? "Accepting…" : "Accept reviewed operation"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function OperationStatusBadge({ status }: { status: OperationStatus }) {
  const variant = status === "completed" ? "positive" : status === "failed" || status === "interrupted" ? "negative" : ["running", "cancel-requested"].includes(status) ? "warning" : "muted";
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
