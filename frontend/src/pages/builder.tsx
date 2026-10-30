import { AlertCircle, ArrowRight, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import type { Catalog, StrategyModelOption, StrategyOption } from "@/lib/types";

interface StrategyDraft {
  id: number;
  name: string;
  models: StrategyModelOption[];
  weight: string;
}

function copyModels(models: StrategyModelOption[]): StrategyModelOption[] {
  return models.map((model) => ({ ...model, params: { ...model.params } }));
}

interface SaveResult {
  name: string;
  strategies: { name: string; title: string; mode: string; weight: number }[];
  cadence: string;
  capital: number;
  benchmark: string;
  approval_required: boolean;
  broker: string;
  spec: Record<string, unknown>;
}

export function BuilderPage() {
  const { capabilities } = useDesk();
  const catalogResource = useResource<Catalog>("/api/catalog");
  const [name, setName] = useState("");
  const [strategyDrafts, setStrategyDrafts] = useState<StrategyDraft[]>([
    { id: 1, name: "", models: [], weight: "1" },
  ]);
  const [nextStrategyId, setNextStrategyId] = useState(2);
  const [capital, setCapital] = useState("100000");
  const [maxPosition, setMaxPosition] = useState("0.25");
  const [maxGross, setMaxGross] = useState("1");
  const [cadence, setCadence] = useState("weekly");
  const [benchmark, setBenchmark] = useState("SPY");
  const [approvalRequired, setApprovalRequired] = useState(true);
  const [broker, setBroker] = useState("paper");
  const [interval, setInterval] = useState("5");
  const [windowStart, setWindowStart] = useState("09:30");
  const [windowEnd, setWindowEnd] = useState("16:00");
  const [universeText, setUniverseText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<SaveResult | null>(null);
  const [deployed, setDeployed] = useState(false);
  const [deploymentMessage, setDeploymentMessage] = useState<string | null>(null);
  const catalog = catalogResource.data;
  const canWrite = capabilities?.writes === true;

  useEffect(() => {
    if (!catalog?.strategies.length) return;
    setStrategyDrafts((drafts) =>
      drafts.map((draft) =>
        draft.name
          ? draft
          : {
              ...draft,
              name: catalog.strategies[0].name,
              models: copyModels(catalog.strategies[0].models),
            },
      ),
    );
  }, [catalog]);

  const strategyLookup = useMemo(
    () => new Map((catalog?.strategies ?? []).map((strategy) => [strategy.name, strategy])),
    [catalog],
  );

  function changeStrategy(id: number, strategyName: string): void {
    const option = strategyLookup.get(strategyName);
    setStrategyDrafts((drafts) =>
      drafts.map((draft) =>
        draft.id === id
          ? { ...draft, name: strategyName, models: option ? copyModels(option.models) : [] }
          : draft,
      ),
    );
  }

  function addStrategy(): void {
    const next = catalog?.strategies.find((strategy) => !strategyDrafts.some((draft) => draft.name === strategy.name));
    if (!next) return;
    setStrategyDrafts((drafts) => [...drafts, { id: nextStrategyId, name: next.name, models: copyModels(next.models), weight: "1" }]);
    setNextStrategyId((value) => value + 1);
  }

  function toggleModel(id: number, model: StrategyModelOption): void {
    setStrategyDrafts((drafts) =>
      drafts.map((draft) =>
        draft.id !== id
          ? draft
          : {
              ...draft,
              models: draft.models.some((entry) => entry.name === model.name)
                ? draft.models.filter((entry) => entry.name !== model.name)
                : [...draft.models, { ...model, params: { ...model.params } }],
            },
      ),
    );
  }

  async function createMandate(): Promise<void> {
    setError(null);
    setDeploymentMessage(null);
    if (!canWrite) {
      setError("This server started without write capability.");
      return;
    }
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name.trim())) {
      setError("Name must start with a letter or digit and use at most 64 letters, digits, hyphens, or underscores.");
      return;
    }
    if (capabilities?.protected_names.some((entry) => entry.toLowerCase() === name.trim().toLowerCase())) {
      setError("Protected fund names cannot be modified by the web UI.");
      return;
    }
    const configuredStrategies = strategyDrafts.map((draft) => ({
      draft,
      option: strategyLookup.get(draft.name),
      weight: Number(draft.weight),
    }));
    if (configuredStrategies.some(({ option }) => !option)) {
      setError("Choose a strategy library entry for every strategy.");
      return;
    }
    if (new Set(configuredStrategies.map(({ option }) => option?.name.toLowerCase())).size !== configuredStrategies.length) {
      setError("A strategy can be added only once to a mandate.");
      return;
    }
    if (configuredStrategies.some(({ draft, option, weight }) => !draft.models.length || draft.models.some((model) => !option?.models.some((entry) => entry.name === model.name)) || !Number.isFinite(weight) || weight <= 0)) {
      setError("Each strategy needs at least one supported analyst and a positive weight.");
      return;
    }
    const capitalValue = Number(capital);
    const positionValue = Number(maxPosition);
    const grossValue = Number(maxGross);
    if (!Number.isFinite(capitalValue) || capitalValue <= 0 || !Number.isFinite(positionValue) || positionValue <= 0 || positionValue > 1 || !Number.isFinite(grossValue) || grossValue <= 0) {
      setError("Capital and risk limits must be positive; max position cannot exceed 100%.");
      return;
    }
    if (broker === "saxo" && cadence !== "minute") {
      setError("Saxo mandates require minute cadence.");
      return;
    }
    if (cadence === "minute" && (!Number.isFinite(Number(interval)) || Number(interval) <= 0 || windowStart >= windowEnd)) {
      setError("Minute cadence needs a positive interval and an opening time before its close.");
      return;
    }
    if (broker === "saxo" && (windowStart < "09:30" || windowEnd > "15:59")) {
      setError("Saxo minute windows must stay between 09:30 and 15:59 New York time.");
      return;
    }

    const spec = {
      schema_version: 2,
      name: name.trim(),
      strategies: configuredStrategies.map(({ draft, option, weight }) => ({
        name: (option as StrategyOption).name,
        display_name: (option as StrategyOption).title,
        weight,
        models: copyModels(draft.models),
        blend: { ...(option as StrategyOption).blend },
      })),
      risk: {
        max_position_pct: positionValue,
        max_gross_exposure: grossValue,
      },
      capital: capitalValue,
      rebalance: cadence,
      benchmark: benchmark.trim().toUpperCase(),
      approval_required: approvalRequired,
      broker,
      ...(cadence === "minute"
        ? { interval: Number(interval), window: { start: windowStart, end: windowEnd } }
        : {}),
    };

    setBusy(true);
    try {
      const result = await apiPost<SaveResult>("/api/mandates", { spec });
      setSaved(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Mandate could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function deployMandate(): Promise<void> {
    if (!saved) return;
    const universe = universeText
      .split(/[,\s]+/)
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean);
    if (universe.length === 0) {
      setDeploymentMessage("Enter one or more tickers before creating a paper book.");
      return;
    }
    if (universe.some((ticker) => !/^[A-Z0-9.^-]{1,16}$/.test(ticker)) || new Set(universe).size !== universe.length) {
      setDeploymentMessage("Use unique tickers with up to 16 ASCII letters, digits, dots, carets, or hyphens.");
      return;
    }
    setBusy(true);
    setDeploymentMessage(null);
    try {
      await apiPost(`/api/mandates/${encodeURIComponent(saved.name)}/deploy`, { universe });
      setDeployed(true);
    } catch (cause) {
      setDeploymentMessage(cause instanceof Error ? cause.message : "Paper book could not be created.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspace / mandate builder"
        title="Compose a mandate"
        description="Build a canonical FundSpec from the strategy library. Save and deploy are separate actions; neither starts a runner."
      />
      {catalogResource.loading ? <div className="mb-5 h-20 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {catalogResource.error ? <Alert tone="danger" className="mb-5">{catalogResource.error}</Alert> : null}
      {!canWrite && capabilities ? <Alert tone="warning" className="mb-5">This server is read-only. Fields remain inspectable; saving and deployment are disabled.</Alert> : null}
      {error ? <Alert tone="danger" className="mb-5"><AlertCircle className="mr-2 inline h-4 w-4" />{error}</Alert> : null}

      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(300px,0.75fr)]">
        <div className="space-y-5">
          <Card>
            <CardHeader>
              <CardTitle>Mandate identity</CardTitle>
              <p className="text-xs text-muted-foreground">New names only. Existing files are never replaced.</p>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Mandate name" htmlFor="mandate-name">
                <Input id="mandate-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="quality-drift" maxLength={64} disabled={Boolean(saved)} />
              </Field>
              <Field label="Starting capital (USD)" htmlFor="capital">
                <Input id="capital" type="number" min="1" step="1000" value={capital} onChange={(event) => setCapital(event.target.value)} disabled={Boolean(saved)} />
              </Field>
              <Field label="Benchmark" htmlFor="benchmark">
                <Input id="benchmark" value={benchmark} onChange={(event) => setBenchmark(event.target.value)} maxLength={16} disabled={Boolean(saved)} />
              </Field>
              <Field label="Broker book" htmlFor="broker">
                <Select
                  value={broker}
                  onValueChange={(value) => {
                    setBroker(value);
                    if (value === "saxo") {
                      setCadence("minute");
                      setWindowStart("09:30");
                      setWindowEnd("15:59");
                    }
                  }}
                  disabled={Boolean(saved)}
                >
                  <SelectTrigger id="broker"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="paper">Paper</SelectItem>
                    <SelectItem value="saxo">Saxo · minute only</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <Field label="Decision cadence" htmlFor="cadence">
                <Select value={cadence} onValueChange={setCadence} disabled={Boolean(saved)}>
                  <SelectTrigger id="cadence"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="daily">Daily</SelectItem>
                    <SelectItem value="weekly">Weekly</SelectItem>
                    <SelectItem value="monthly">Monthly</SelectItem>
                    <SelectItem value="minute">Minute cadence</SelectItem>
                  </SelectContent>
                </Select>
              </Field>
              <div className="flex items-center justify-between gap-4 rounded-lg border border-border bg-black/10 px-4 py-3 sm:col-span-2">
                <div>
                  <p className="text-xs font-medium text-foreground">Require approval before next execution</p>
                  <p className="mt-1 text-[10px] text-muted-foreground">Verdicts use the existing hash-bound ledger mailbox.</p>
                </div>
                <input
                  type="checkbox"
                  aria-label="Require approval"
                  checked={approvalRequired}
                  onChange={(event) => setApprovalRequired(event.target.checked)}
                  disabled={Boolean(saved)}
                  className="h-4 w-4 accent-cyan-400"
                />
              </div>
              {cadence === "minute" ? (
                <div className="grid gap-4 rounded-lg border border-accent/20 bg-accent/[0.04] p-4 sm:col-span-2 sm:grid-cols-3">
                  <Field label="Interval (minutes)" htmlFor="interval">
                    <Input id="interval" type="number" min="0.0167" step="0.0167" value={interval} onChange={(event) => setInterval(event.target.value)} disabled={Boolean(saved)} />
                  </Field>
                  <Field label="Window open · New York time" htmlFor="window-start">
                    <Input id="window-start" type="time" value={windowStart} onChange={(event) => setWindowStart(event.target.value)} disabled={Boolean(saved)} />
                  </Field>
                  <Field label="Window close · New York time" htmlFor="window-end">
                    <Input id="window-end" type="time" value={windowEnd} onChange={(event) => setWindowEnd(event.target.value)} disabled={Boolean(saved)} />
                  </Field>
                  <p className="text-[10px] leading-relaxed text-muted-foreground sm:col-span-3">Minute-only fields are omitted from non-minute specifications. Canonical validation still enforces the supported trading window and broker restrictions.</p>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-start justify-between gap-4">
              <div>
                <CardTitle>Strategy sleeves</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">Start from validated library strategies, then select their registered analysts.</p>
              </div>
              <Button variant="outline" size="sm" onClick={addStrategy} disabled={Boolean(saved) || !catalog || strategyDrafts.length >= catalog.strategies.length}>
                <Plus className="h-3.5 w-3.5" /> Add sleeve
              </Button>
            </CardHeader>
            <CardContent className="space-y-4">
              {strategyDrafts.map((draft, index) => {
                const strategy = strategyLookup.get(draft.name);
                const otherNames = new Set(strategyDrafts.filter((item) => item.id !== draft.id).map((item) => item.name));
                return (
                  <div key={draft.id} className="rounded-xl border border-border bg-black/10 p-4 sm:p-5">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="mono text-[10px] text-accent">0{index + 1}</span>
                        <span className="text-xs font-semibold text-foreground">Strategy sleeve</span>
                        {strategy ? <Badge variant="muted">{strategy.mode.replaceAll("_", " ")}</Badge> : null}
                      </div>
                      {strategyDrafts.length > 1 ? (
                        <Button variant="ghost" size="sm" onClick={() => setStrategyDrafts((drafts) => drafts.filter((item) => item.id !== draft.id))} disabled={Boolean(saved)}>
                          <Trash2 className="h-3.5 w-3.5" /> Remove
                        </Button>
                      ) : null}
                    </div>
                    <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_160px]">
                      <Field label="Library strategy" htmlFor={`strategy-${draft.id}`}>
                        <Select value={draft.name} onValueChange={(value) => changeStrategy(draft.id, value)} disabled={Boolean(saved) || !catalog}>
                          <SelectTrigger id={`strategy-${draft.id}`}><SelectValue placeholder="Choose a strategy" /></SelectTrigger>
                          <SelectContent>
                            {(catalog?.strategies ?? []).map((option) => (
                              <SelectItem key={option.name} value={option.name} disabled={otherNames.has(option.name)}>
                                {option.title}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field label="Sleeve weight" htmlFor={`weight-${draft.id}`}>
                        <Input id={`weight-${draft.id}`} type="number" min="0.001" step="0.1" value={draft.weight} onChange={(event) => setStrategyDrafts((drafts) => drafts.map((item) => item.id === draft.id ? { ...item, weight: event.target.value } : item))} disabled={Boolean(saved)} />
                      </Field>
                    </div>
                    <div className="mt-4">
                      <p className="mb-2 text-[10px] uppercase tracking-[0.13em] text-muted-foreground">Registered analysts</p>
                      {strategy?.models.length ? (
                        <div className="grid gap-2 sm:grid-cols-2">
                          {strategy.models.map((model) => (
                            <label key={model.name} className="flex cursor-pointer items-center gap-3 rounded-lg border border-border/80 bg-white/[0.02] px-3 py-2.5 text-xs text-foreground has-[:disabled]:cursor-not-allowed has-[:disabled]:opacity-60">
                              <input type="checkbox" checked={draft.models.some((entry) => entry.name === model.name)} onChange={() => toggleModel(draft.id, model)} disabled={Boolean(saved)} className="h-3.5 w-3.5 accent-cyan-400" />
                              <span className="mono">{model.name} <span className="text-muted-foreground">· blend weight {model.weight}</span></span>
                            </label>
                          ))}
                        </div>
                      ) : <p className="text-xs text-muted-foreground">Choose a strategy to view its registered analysts.</p>}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Portfolio risk limits</CardTitle>
              <p className="text-xs text-muted-foreground">Deterministic portfolio construction clamps target weights against these limits.</p>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Maximum position weight (0–1)" htmlFor="max-position">
                <Input id="max-position" type="number" min="0.001" max="1" step="0.01" value={maxPosition} onChange={(event) => setMaxPosition(event.target.value)} disabled={Boolean(saved)} />
              </Field>
              <Field label="Maximum gross exposure" htmlFor="max-gross">
                <Input id="max-gross" type="number" min="0.001" step="0.1" value={maxGross} onChange={(event) => setMaxGross(event.target.value)} disabled={Boolean(saved)} />
              </Field>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-5 xl:sticky xl:top-24">
          <Card>
            <CardHeader>
              <CardTitle>Deliberate build</CardTitle>
              <p className="text-xs text-muted-foreground">A saved mandate is not a deployed book.</p>
            </CardHeader>
            <CardContent className="space-y-4">
              {saved ? (
                <div className="rounded-lg border border-positive/25 bg-positive/10 p-4">
                  <Badge variant="positive">Mandate saved</Badge>
                  <p className="mono mt-3 text-sm text-foreground">{saved.name}</p>
                  <Link to={`/mandates/${encodeURIComponent(saved.name)}`} className="mt-2 inline-flex items-center gap-1 text-xs text-accent hover:underline">
                    Inspect canonical spec <ArrowRight className="h-3 w-3" />
                  </Link>
                </div>
              ) : (
                <div className="rounded-lg border border-border bg-black/10 p-4">
                  <p className="text-xs leading-relaxed text-muted-foreground">Review name conflicts, strategy selection, and canonical validation before writing.</p>
                  <Button className="mt-4 w-full" onClick={() => void createMandate()} disabled={busy || !canWrite || !catalog || catalogResource.loading}>
                    <Save className="h-3.5 w-3.5" /> {busy ? "Saving…" : "Save new mandate"}
                  </Button>
                </div>
              )}
              {saved && !deployed ? (
                <div className="space-y-3 rounded-lg border border-border bg-black/10 p-4">
                  <div>
                    <p className="text-xs font-semibold text-foreground">Optional paper deployment</p>
                    <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">Creates a new book under the local paper root. Runner stays untouched.</p>
                  </div>
                  <Field label="Ticker universe" htmlFor="universe">
                    <Input id="universe" value={universeText} onChange={(event) => setUniverseText(event.target.value)} placeholder="AAPL, MSFT, SPY" disabled={!canWrite} />
                  </Field>
                  <Button className="w-full" variant="secondary" onClick={() => void deployMandate()} disabled={busy || !canWrite}>
                    {busy ? "Creating…" : "Create paper book"}
                  </Button>
                  {deploymentMessage ? <Alert tone="danger">{deploymentMessage}</Alert> : null}
                </div>
              ) : null}
              {deployed ? (
                <Alert tone="neutral">
                  Paper book created. No process started.
                  <Link to={`/paper/${encodeURIComponent(saved?.name ?? "")}`} className="ml-1 inline-flex items-center gap-1 text-accent hover:underline">Open fund <ArrowRight className="h-3 w-3" /></Link>
                </Alert>
              ) : null}
              <div className="space-y-2 border-t border-border pt-3">
                <SafetyRow label="Writes" value={canWrite ? "Enabled" : "Disabled"} positive={!canWrite} />
                <SafetyRow label="External network" value={capabilities?.network ? "Enabled at startup" : "Off"} positive={!capabilities?.network} />
                <SafetyRow label="Runner start" value="Unavailable" positive />
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Deployment universe</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs leading-relaxed text-muted-foreground">
                Universe is supplied when deploying, not stored in FundSpec. It is required for a paper book or backtest.
              </p>
              <p className="mono text-[10px] text-muted-foreground">1–25 unique ASCII tickers · protected names denied</p>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  );
}

function SafetyRow({ label, value, positive = false }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Badge variant={positive ? "positive" : "warning"}>{value}</Badge>
    </div>
  );
}
