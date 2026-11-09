import { AlertCircle, CheckCircle2, KeyRound, LockKeyhole, RadioTower, Settings2 } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ConfigurationProvenancePanel } from "@/components/configuration-provenance";
import { MetricCard } from "@/components/metric-card";
import { ErrorNotice, ErrorState, PageHeader, SectionTitle } from "@/components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { apiDelete, apiPost, apiPut } from "@/lib/api";
import { toActionableError, type ActionableError } from "@/lib/errors";
import { useDesk, useResource } from "@/lib/hooks";
import type { Settings, SaxoSimChoice, SaxoSimDiscovery, SaxoSimInspection, SaxoSimStatus } from "@/lib/types";

export function SettingsPage() {
  const { capabilities, reconnect } = useDesk();
  const resource = useResource<Settings>("/api/settings");
  const settings = resource.data;
  const [selectedModel, setSelectedModel] = useState("");
  const [dataProvider, setDataProvider] = useState("");
  const [endpoint, setEndpoint] = useState("");
  const [timeoutSeconds, setTimeoutSeconds] = useState("");
  const [maxTokens, setMaxTokens] = useState("");
  const [contextSize, setContextSize] = useState("");
  const [temperature, setTemperature] = useState("");
  const [topP, setTopP] = useState("");
  const [provider, setProvider] = useState("");
  const [credential, setCredential] = useState("");
  const [savingSettings, setSavingSettings] = useState(false);
  const [savingCredential, setSavingCredential] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "danger" | "neutral"; message: string; error?: ActionableError } | null>(null);
  const fail = (cause: unknown, fallback: string) => {
    const error = toActionableError(cause, fallback);
    setFeedback({ tone: "danger", message: error.message, error });
  };
  const canWrite = capabilities?.writes === true;
  const credentialProviders = settings?.providers.filter((item) => item.requires_key) ?? [];
  const selectedCredentialProvider = credentialProviders.find((item) => item.provider === provider);
  const configuration = settings?.configuration;
  // The form edits the stored record; overrides and captured work are shown separately.
  const baseline = settings
    ? configuration
      ? configuration.stored_values
      : {
          data_provider: settings.data_provider,
          model: settings.model,
          endpoint: settings.endpoint,
          timeout_seconds: settings.timeout_seconds,
          parameters: settings.parameters,
        }
    : null;
  const storedAhead = configuration?.restart_reasons.includes("stored-version-changed") === true;
  const hasOverrides = (configuration?.overrides.length ?? 0) > 0;

  useEffect(() => {
    if (!baseline || selectedModel) return;
    setSelectedModel(baseline.model);
    setDataProvider(baseline.data_provider);
    setEndpoint(baseline.endpoint ?? "");
    setTimeoutSeconds(String(baseline.timeout_seconds));
    setMaxTokens(baseline.parameters.max_tokens?.toString() ?? "");
    setContextSize(baseline.parameters.context_size?.toString() ?? "");
    setTemperature(baseline.parameters.temperature?.toString() ?? "");
    setTopP(baseline.parameters.top_p?.toString() ?? "");
  }, [baseline, selectedModel]);

  useEffect(() => {
    if (credentialProviders.length && !provider) setProvider(credentialProviders[0].provider);
  }, [credentialProviders, provider]);

  const timeoutValue = Number(timeoutSeconds);
  const maxTokensValue = maxTokens.trim() ? Number(maxTokens) : undefined;
  const contextSizeValue = contextSize.trim() ? Number(contextSize) : undefined;
  const temperatureValue = temperature.trim() ? Number(temperature) : undefined;
  const topPValue = topP.trim() ? Number(topP) : undefined;
  const endpointValue = endpoint.trim() || null;
  const selectedModelProvider = settings?.models.find((item) => item.id === selectedModel)?.provider;
  const supportsLocalContext =
    selectedModelProvider === "Ollama" && !selectedModel.toLowerCase().endsWith(":cloud");
  const parameters = {
    ...(maxTokensValue !== undefined ? { max_tokens: maxTokensValue } : {}),
    ...(supportsLocalContext && contextSizeValue !== undefined
      ? { context_size: contextSizeValue }
      : {}),
    ...(temperatureValue !== undefined ? { temperature: temperatureValue } : {}),
    ...(supportsLocalContext && topPValue !== undefined ? { top_p: topPValue } : {}),
  };
  const runtimeSettingsValid =
    Number.isFinite(timeoutValue) &&
    timeoutValue > 0 &&
    timeoutValue <= 300 &&
    (maxTokensValue === undefined || (Number.isInteger(maxTokensValue) && maxTokensValue >= 1 && maxTokensValue <= 131072)) &&
    (!supportsLocalContext ||
      contextSizeValue === undefined ||
      (Number.isInteger(contextSizeValue) && contextSizeValue >= 256 && contextSizeValue <= 131072)) &&
    (temperatureValue === undefined || (Number.isFinite(temperatureValue) && temperatureValue >= 0 && temperatureValue <= 2)) &&
    (!supportsLocalContext ||
      topPValue === undefined ||
      (Number.isFinite(topPValue) && topPValue >= 0 && topPValue <= 1));
  const runtimeSettingsChanged = baseline
    ? selectedModel !== baseline.model ||
      dataProvider !== baseline.data_provider ||
      endpointValue !== baseline.endpoint ||
      timeoutValue !== baseline.timeout_seconds ||
      Object.keys(parameters).length !== Object.keys(baseline.parameters).length ||
      Object.entries(parameters).some(([name, value]) => baseline.parameters[name] !== value)
    : false;
  const saveBlockedByRestart = Boolean(settings) && (storedAhead || !baseline);

  async function saveRuntimeSettings(): Promise<void> {
    if (!selectedModel || !dataProvider || !canWrite || !settings || !runtimeSettingsValid || saveBlockedByRestart) return;
    setSavingSettings(true);
    setFeedback(null);
    try {
      await apiPut("/api/settings", {
        data_provider: dataProvider,
        model: selectedModel,
        endpoint: endpointValue,
        timeout_seconds: timeoutValue,
        parameters,
        expected_version: settings.version,
      });
      setFeedback({
        tone: "neutral",
        message: hasOverrides
          ? "Runtime settings are saved in this root. New operations capture this version; active captures and the shared .env file are unchanged. Fields shadowed by a process environment override keep the override until restart without it."
          : "Runtime settings are saved in this root. New operations capture this version; active captures and the shared .env file are unchanged.",
      });
      resource.refresh();
    } catch (cause) {
      fail(cause, "Runtime settings could not be saved.");
    } finally {
      setSavingSettings(false);
    }
  }

  async function saveCredential(): Promise<void> {
    if (!provider || !credential || !canWrite || !selectedCredentialProvider) return;
    const secret = credential;
    setCredential("");
    setSavingCredential(true);
    setFeedback(null);
    try {
      await apiPost("/api/settings/credentials", {
        provider,
        value: secret,
        expected_version: selectedCredentialProvider?.version ?? 0,
      });
      setFeedback({ tone: "neutral", message: `Credential saved for ${provider}. The value is not returned or displayed.` });
      resource.refresh();
    } catch (cause) {
      fail(cause, "Credential could not be saved.");
    } finally {
      setSavingCredential(false);
    }
  }

  async function deleteCredential(): Promise<void> {
    if (!selectedCredentialProvider?.configured || !canWrite) return;
    setSavingCredential(true);
    setFeedback(null);
    try {
      await apiDelete(
        `/api/settings/credentials/${encodeURIComponent(provider)}?expected_version=${selectedCredentialProvider.version}`,
      );
      setFeedback({
        tone: "neutral",
        message: `Credential removed for ${provider}. New and not-yet-dispatched work cannot use it; running work keeps the version it already captured and is not stopped by this page.`,
      });
      resource.refresh();
    } catch (cause) {
      fail(cause, "Credential could not be deleted.");
    } finally {
      setSavingCredential(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="System / local settings"
        title="Settings"
        description="Inspect model and provider readiness without revealing key values. Network and write permissions are immutable for this server process."
      />
      {resource.loading ? <div className="mb-5 h-24 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <div className="mb-5"><ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /></div> : null}
      {!canWrite && capabilities ? <Alert tone="warning" className="mb-5">Settings are read only. Start a separate server with explicit write consent to save a model or credential.</Alert> : null}
      {capabilities?.local_operator_only ? <Alert tone="warning" className="mb-5">Local operator only. The CSRF token blocks cross-site requests; it is not authentication against local processes.</Alert> : null}
      {settings?.settings_error ? <Alert tone="danger" className="mb-5">Private settings or credential status is unavailable. Writes that depend on this state are blocked.</Alert> : null}
      {feedback?.error ? (
        <ErrorNotice
          className="mb-5"
          error={feedback.error}
          onAction={
            feedback.error.action === "reconnect"
              ? () => void reconnect()
              : feedback.error.action
                ? () => { setFeedback(null); resource.refresh(); }
                : undefined
          }
        />
      ) : feedback ? <Alert tone={feedback.tone} className="mb-5">{feedback.message}</Alert> : null}
      {settings ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricCard label="Selected data provider" value={settings.data_provider} note="Provider selection is not a network request" icon={RadioTower} />
            <MetricCard label="External network" value={settings.network_enabled ? "Enabled" : "Off"} note="Fixed at server startup" tone={settings.network_enabled ? "warning" : "positive"} icon={settings.network_enabled ? RadioTower : LockKeyhole} />
            <MetricCard label="Configured providers" value={`${settings.providers.filter((item) => item.configured).length} / ${settings.providers.length}`} note="Presence flags only · no values exposed" icon={KeyRound} />
          </div>
          <SaxoInspectionCard canWrite={canWrite} networkEnabled={settings.network_enabled} />
          <div className="mt-5 grid items-start gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Runtime configuration</p>
                    <p className="mt-1 text-xs text-muted-foreground">Effective values · saved to this root</p>
                  </div>
                  <Settings2 className="h-4 w-4 text-accent" />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="data-provider-choice">Data provider</Label>
                  <Select value={dataProvider || settings.data_provider} onValueChange={setDataProvider} disabled={!canWrite}>
                    <SelectTrigger id="data-provider-choice"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {settings.data_providers.map((item) => (
                        <SelectItem key={item.id} value={item.id}>{item.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="model-choice">LLM model</Label>
                  <Select value={selectedModel || settings.model} onValueChange={setSelectedModel} disabled={!canWrite || !settings.models.length}>
                    <SelectTrigger id="model-choice"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {settings.models.map((item) => (
                        <SelectItem key={item.id} value={item.id}>{item.label} · {item.provider}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground">Provider: {settings.llm_provider} · source: {settings.provenance.llm_provider}</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="llm-endpoint">LLM endpoint override</Label>
                  <Input
                    id="llm-endpoint"
                    type="url"
                    value={endpoint}
                    onChange={(event) => setEndpoint(event.target.value)}
                    maxLength={2048}
                    placeholder="Optional · local HTTP or HTTPS"
                    disabled={!canWrite || savingSettings}
                  />
                  <p className="text-[10px] text-muted-foreground">
                    {settings.endpoint_redacted
                      ? `Effective endpoint comes from ${settings.provenance.endpoint === "launch" ? "a launch-argument" : "a process-environment"} override and is hidden; this field edits the saved value only.`
                      : `Source: ${settings.provenance.endpoint}`}{" "}
                    · credentials must not appear in the URL.
                  </p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="llm-timeout">Request timeout (seconds)</Label>
                    <Input
                      id="llm-timeout"
                      type="number"
                      min={1}
                      max={300}
                      step={1}
                      value={timeoutSeconds}
                      onChange={(event) => setTimeoutSeconds(event.target.value)}
                      disabled={!canWrite || savingSettings}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="max-tokens">Maximum tokens</Label>
                    <Input
                      id="max-tokens"
                      type="number"
                      min={1}
                      max={131072}
                      step={1}
                      value={maxTokens}
                      onChange={(event) => setMaxTokens(event.target.value)}
                      placeholder="Provider default"
                      disabled={!canWrite || savingSettings}
                    />
                  </div>
                  {supportsLocalContext ? (
                    <div className="space-y-2">
                      <Label htmlFor="context-size">Local context size</Label>
                      <Input
                        id="context-size"
                        type="number"
                        min={256}
                        max={131072}
                        step={256}
                        value={contextSize}
                        onChange={(event) => setContextSize(event.target.value)}
                        placeholder="8192 · Ollama default"
                        disabled={!canWrite || savingSettings}
                      />
                    </div>
                  ) : null}
                  <div className="space-y-2">
                    <Label htmlFor="temperature">Temperature</Label>
                    <Input
                      id="temperature"
                      type="number"
                      min={0}
                      max={2}
                      step={0.1}
                      value={temperature}
                      onChange={(event) => setTemperature(event.target.value)}
                      placeholder="Provider default"
                      disabled={!canWrite || savingSettings}
                    />
                  </div>
                  {supportsLocalContext ? (
                    <div className="space-y-2">
                      <Label htmlFor="top-p">Top-p</Label>
                      <Input
                        id="top-p"
                        type="number"
                        min={0}
                        max={1}
                        step={0.05}
                        value={topP}
                        onChange={(event) => setTopP(event.target.value)}
                        placeholder="Provider default"
                        disabled={!canWrite || savingSettings}
                      />
                    </div>
                  ) : null}
                </div>
                <Button
                  className="w-full"
                  variant="secondary"
                  onClick={() => void saveRuntimeSettings()}
                  disabled={!canWrite || savingSettings || saveBlockedByRestart || !selectedModel || !dataProvider || !runtimeSettingsChanged || !runtimeSettingsValid}
                >
                  {savingSettings ? "Saving…" : "Save runtime settings for this root"}
                </Button>
                {saveBlockedByRestart ? (
                  <p className="text-[10px] leading-relaxed text-warning">
                    Saved settings changed outside this server or are unavailable. Saving is blocked to avoid overwriting them; restart the server manually to load the saved version.
                  </p>
                ) : null}
                <p className="text-[10px] leading-relaxed text-muted-foreground">
                  Save makes no provider call and does not edit the shared <span className="mono">.env</span>. New operations capture these values; active captures remain unchanged.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Provider credentials</p>
                    <p className="mt-1 text-xs text-muted-foreground">Write-only input · values are cleared after submission</p>
                  </div>
                  <KeyRound className="h-4 w-4 text-accent" />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {credentialProviders.length ? (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="credential-provider">Provider</Label>
                      <Select value={provider} onValueChange={setProvider} disabled={!canWrite}>
                        <SelectTrigger id="credential-provider"><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {credentialProviders.map((item) => (
                            <SelectItem key={item.provider} value={item.provider}>
                              {item.provider} · {item.configured ? "configured" : "missing"}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="credential-value">New credential</Label>
                      <Input
                        id="credential-value"
                        type="password"
                        value={credential}
                        onChange={(event) => setCredential(event.target.value)}
                        autoComplete="new-password"
                        spellCheck={false}
                        maxLength={4096}
                        placeholder="Value is never displayed after submission"
                        disabled={!canWrite || savingCredential}
                      />
                    </div>
                    <Button className="w-full" onClick={() => void saveCredential()} disabled={!canWrite || savingCredential || !credential || !selectedCredentialProvider}>
                      {savingCredential ? "Saving securely…" : "Save credential"}
                    </Button>
                    {selectedCredentialProvider?.configured ? (
                      <Button
                        className="w-full"
                        variant="secondary"
                        onClick={() => void deleteCredential()}
                        disabled={!canWrite || savingCredential}
                      >
                        Remove {provider} credential
                      </Button>
                    ) : null}
                    <div className="space-y-2 border-t border-border pt-3">
                      <SectionTitle title="Provider readiness" note="Only a configured/missing flag is shown" />
                      {credentialProviders.map((item) => (
                        <div key={item.provider} className="flex items-center justify-between gap-3 text-xs">
                          <span className="mono text-muted-foreground">{item.provider}</span>
                          <Badge variant={item.configured ? "positive" : "muted"}>
                            {item.configured ? <CheckCircle2 className="h-3 w-3" /> : <AlertCircle className="h-3 w-3" />}
                            {item.configured ? "Configured" : "Missing"}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p className="text-xs text-muted-foreground">No keyed providers are present in the supported catalog.</p>
                )}
              </CardContent>
            </Card>
          </div>
          {configuration ? <ConfigurationProvenancePanel configuration={configuration} /> : null}
          {!settings.active_captures_available ? (
            <Alert tone="warning" className="mt-5">Active capture status is unavailable. Runtime edits do not authorize hot-swapping running work.</Alert>
          ) : settings.active_captures.length ? (
            <Card className="mt-5">
              <CardHeader>
                <SectionTitle title="Active execution snapshots" note="Running work keeps captured settings and credential versions" />
              </CardHeader>
              <CardContent className="grid gap-3 md:grid-cols-2">
                {settings.active_captures.map((capture) => (
                  <div key={capture.capture_id} className="rounded-lg border border-border bg-black/10 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-foreground">{capture.subject_id}</p>
                        <p className="mt-1 text-[10px] uppercase tracking-[0.15em] text-muted-foreground">{capture.status}</p>
                      </div>
                      <Badge variant={capture.capture_details_available ? "positive" : "warning"}>
                        {capture.capture_details_available ? "Captured" : "Details unavailable"}
                      </Badge>
                    </div>
                    <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                      <div><p className="text-muted-foreground">Model</p><p className="mono mt-1 text-foreground">{capture.model ?? "Unknown"}</p></div>
                      <div><p className="text-muted-foreground">Data provider</p><p className="mono mt-1 text-foreground">{capture.data_provider ?? "Unknown"}</p></div>
                      <div><p className="text-muted-foreground">LLM provider</p><p className="mt-1 text-foreground">{capture.llm_provider ?? "Unknown"}</p></div>
                      <div><p className="text-muted-foreground">Settings version</p><p className="mono mt-1 text-foreground">{capture.settings_version ?? "Unknown"}</p></div>
                    </div>
                    {capture.restart_needed ? (
                      <p className="mt-3 text-[10px] text-warning">New settings apply to later operations; this snapshot remains unchanged.</p>
                    ) : null}
                  </div>
                ))}
              </CardContent>
            </Card>
          ) : null}
          <Card className="mt-5">
            <CardHeader>
              <SectionTitle title="Execution boundary" note="Settings do not change process capabilities after startup." />
            </CardHeader>
            <CardContent className="grid gap-4 text-xs sm:grid-cols-3">
              <div><p className="mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Writes</p><p className="mt-2 text-foreground">{capabilities?.writes ? "Enabled for this local process" : "Disabled · default mode"}</p></div>
              <div><p className="mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Network</p><p className="mt-2 text-foreground">{capabilities?.network ? "Enabled at startup" : "Off · no provider calls"}</p></div>
              <div><p className="mono text-[9px] uppercase tracking-[0.15em] text-muted-foreground">Credentials</p><p className="mt-2 text-foreground">Stored locally · presence only in browser</p></div>
            </CardContent>
          </Card>
        </>
      ) : null}
    </>
  );
}

function SaxoInspectionCard({ canWrite, networkEnabled }: { canWrite: boolean; networkEnabled: boolean }) {
  const { generation: connectionGeneration } = useDesk();
  const resource = useResource<SaxoSimStatus>("/api/saxo/sim/status");
  const [choices, setChoices] = useState<SaxoSimChoice[]>([]);
  const [selectionId, setSelectionId] = useState("");
  const [result, setResult] = useState<SaxoSimInspection | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ActionableError | null>(null);
  const previousGeneration = useRef<string | null>(null);
  const actionEpoch = useRef(0);
  const capability = resource.data?.capability;
  const statusGeneration = capability?.generation ?? null;

  const clearTransient = useCallback((): void => {
    actionEpoch.current += 1;
    setChoices([]);
    setSelectionId("");
    setResult(null);
    setConsent(false);
    setBusy(false);
  }, []);

  useEffect(() => {
    const identity = `${connectionGeneration}:${statusGeneration ?? "unknown"}:${capability?.state}:${canWrite}:${networkEnabled}:${Boolean(resource.error)}`;
    if (previousGeneration.current !== null && previousGeneration.current !== identity) clearTransient();
    previousGeneration.current = identity;
  }, [clearTransient, connectionGeneration, statusGeneration, capability?.state, canWrite, networkEnabled, resource.error]);

  useEffect(() => () => { actionEpoch.current += 1; }, []);

  async function discover(): Promise<void> {
    if (!capability || !consent || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const epoch = ++actionEpoch.current;
    try {
      const response = await apiPost<SaxoSimDiscovery>("/api/saxo/sim/accounts", {
        authorize_network: true,
        expected_generation: capability.generation,
      });
      if (epoch !== actionEpoch.current) return;
      setChoices(response.choices);
      setSelectionId("");
    } catch (cause) {
      if (epoch !== actionEpoch.current) return;
      clearTransient();
      setError(toActionableError(cause, "Saxo SIM accounts could not be discovered."));
      resource.refresh();
    } finally {
      if (epoch === actionEpoch.current) {
        setConsent(false);
        setBusy(false);
      }
    }
  }

  async function inspect(): Promise<void> {
    if (!capability || !selectionId || !consent || busy) return;
    setBusy(true);
    setError(null);
    setResult(null);
    const epoch = ++actionEpoch.current;
    try {
      const response = await apiPost<SaxoSimInspection>("/api/saxo/sim/inspect", {
        authorize_network: true,
        expected_generation: capability.generation,
        selection_id: selectionId,
      });
      if (epoch !== actionEpoch.current) return;
      setResult(response);
      setChoices([]);
      setSelectionId("");
    } catch (cause) {
      if (epoch !== actionEpoch.current) return;
      clearTransient();
      setError(toActionableError(cause, "Saxo SIM account inspection could not be completed."));
      resource.refresh();
    } finally {
      if (epoch === actionEpoch.current) {
        setConsent(false);
        setBusy(false);
      }
    }
  }

  async function revoke(): Promise<void> {
    if (!capability || !capability.actions.revoke) return;
    setError(null);
    clearTransient();
    setBusy(true);
    const epoch = actionEpoch.current;
    try {
      await apiDelete(`/api/credentials/runtime/saxo-demo-token?expected_generation=${capability.generation}`);
      if (epoch !== actionEpoch.current) return;
      resource.refresh();
    } catch (cause) {
      if (epoch !== actionEpoch.current) return;
      setError(toActionableError(cause, "Saxo SIM inspection access could not be revoked."));
    } finally {
      if (epoch === actionEpoch.current) setBusy(false);
    }
  }

  async function cancel(): Promise<void> {
    clearTransient();
    const epoch = actionEpoch.current;
    try {
      await apiPost("/api/saxo/sim/cancel", {});
    } catch (cause) {
      if (epoch !== actionEpoch.current) return;
      setError(toActionableError(cause, "The inspection could not be canceled."));
    }
  }

  const canAct = Boolean(canWrite && networkEnabled && capability?.actions.discover && !busy);
  return (
    <Card className="mt-5">
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-foreground">Saxo SIM account inspection</p>
            <p className="mt-1 text-xs text-muted-foreground">Separate read-only capability · does not connect a fund or enable trading</p>
          </div>
          <RadioTower className="h-4 w-4 text-accent" />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <Badge variant={capability?.state === "available" ? "positive" : "muted"}>
            {resource.loading ? "Checking status…" : capability?.state ?? "Unavailable"}
          </Badge>
          <span className="text-muted-foreground">SIM · GET only</span>
          {capability?.expires_at ? (
            <span className="text-muted-foreground">Lease expires {new Date(capability.expires_at).toLocaleString()}</span>
          ) : null}
        </div>
        {resource.error ? <ErrorState message={resource.error} error={resource.apiError} onRetry={resource.refresh} /> : null}
        {error ? <ErrorNotice error={error} onAction={error.action ? () => { setError(null); resource.refresh(); } : undefined} /> : null}
        {!networkEnabled ? <Alert tone="warning">Network capability is off for this server. No broker request will be sent.</Alert> : null}
        {capability?.state === "requires-auth" || capability?.state === "expired" || capability?.state === "revoked" ? (
          <p className="text-xs text-muted-foreground">Deliver a valid, unexpired inspection credential through the approved host-side private channel. This page never accepts or displays a token.</p>
        ) : null}
        <label className="flex items-start gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            disabled={!canAct}
            aria-label="Authorize one explicit Saxo SIM read-only network action"
          />
          I authorize this one read-only HTTPS request to Saxo SIM.
        </label>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void discover()} disabled={!canAct || !consent}>
            {busy ? "Working…" : "Discover SIM accounts"}
          </Button>
          {busy ? <Button variant="secondary" onClick={() => void cancel()}>Cancel inspection</Button> : null}
          {capability?.actions.revoke && canWrite ? (
            <Button variant="secondary" onClick={() => void revoke()}>Revoke inspection access</Button>
          ) : null}
        </div>
        {choices.length ? (
          <div className="space-y-3 border-t border-border pt-3">
            <label className="block space-y-2 text-xs text-muted-foreground" htmlFor="saxo-sim-account">
              Choose one account to inspect
              <select
                id="saxo-sim-account"
                className="block w-full rounded-md border border-border bg-background px-3 py-2 text-foreground"
                value={selectionId}
                onChange={(event) => setSelectionId(event.target.value)}
              >
                <option value="">Select a SIM account</option>
                {choices.map((choice) => (
                  <option key={choice.selection_id} value={choice.selection_id}>
                    {choice.label} · {choice.currency}
                  </option>
                ))}
              </select>
            </label>
            <Button onClick={() => void inspect()} disabled={!canAct || !selectionId || !consent}>
              Inspect selected account
            </Button>
          </div>
        ) : null}
        {result ? (
          <div className="space-y-3 border-t border-border pt-3" aria-live="polite">
            <p className="text-sm font-medium text-foreground">{result.account.label} · {result.account.currency}</p>
            <p className="text-xs text-muted-foreground">Cash balance: {result.account.cash_balance}</p>
            <p className="text-xs text-muted-foreground">Positions: {result.account.positions.length}</p>
            {result.account.positions.length ? (
              <ul className="grid gap-2 text-xs sm:grid-cols-2">
                {result.account.positions.map((position, index) => (
                  <li key={`${position.uic}-${index}`} className="rounded border border-border p-2">
                    UIC {position.uic} · amount {position.amount}
                  </li>
                ))}
              </ul>
            ) : <p className="text-xs text-muted-foreground">No positions were returned for this account.</p>}
            <p className="text-[10px] text-muted-foreground">SIM · read-only · fund not connected · trading disabled</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
