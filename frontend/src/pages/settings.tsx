import { AlertCircle, CheckCircle2, KeyRound, LockKeyhole, RadioTower, Settings2 } from "lucide-react";
import { useEffect, useState } from "react";

import { MetricCard } from "@/components/metric-card";
import { ErrorState, PageHeader, SectionTitle } from "@/components/page";
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
import { apiPost } from "@/lib/api";
import { useDesk, useResource } from "@/lib/hooks";
import type { Settings } from "@/lib/types";

export function SettingsPage() {
  const { capabilities } = useDesk();
  const resource = useResource<Settings>("/api/settings");
  const settings = resource.data;
  const [selectedModel, setSelectedModel] = useState("");
  const [provider, setProvider] = useState("");
  const [credential, setCredential] = useState("");
  const [savingModel, setSavingModel] = useState(false);
  const [savingCredential, setSavingCredential] = useState(false);
  const [feedback, setFeedback] = useState<{ tone: "danger" | "neutral"; message: string } | null>(null);
  const canWrite = capabilities?.writes === true;
  const credentialProviders = settings?.providers.filter((item) => item.requires_key) ?? [];

  useEffect(() => {
    if (settings && !selectedModel) setSelectedModel(settings.model);
  }, [selectedModel, settings]);

  useEffect(() => {
    if (credentialProviders.length && !provider) setProvider(credentialProviders[0].provider);
  }, [credentialProviders, provider]);

  async function saveModel(): Promise<void> {
    if (!selectedModel || !canWrite) return;
    setSavingModel(true);
    setFeedback(null);
    try {
      await apiPost("/api/settings/model", { model: selectedModel });
      setFeedback({ tone: "neutral", message: "Model selection applies to this server process. New research jobs capture the selected model; the shared .env file is unchanged." });
      resource.refresh();
    } catch (cause) {
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Model selection could not be saved." });
    } finally {
      setSavingModel(false);
    }
  }

  async function saveCredential(): Promise<void> {
    if (!provider || !credential || !canWrite) return;
    const secret = credential;
    setCredential("");
    setSavingCredential(true);
    setFeedback(null);
    try {
      await apiPost("/api/settings/credentials", { provider, value: secret });
      setFeedback({ tone: "neutral", message: `Credential saved for ${provider}. The value is not returned or displayed.` });
      resource.refresh();
    } catch (cause) {
      setFeedback({ tone: "danger", message: cause instanceof Error ? cause.message : "Credential could not be saved." });
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
      {resource.error ? <div className="mb-5"><ErrorState message={resource.error} /></div> : null}
      {!canWrite && capabilities ? <Alert tone="warning" className="mb-5">Settings are read only. Start a separate server with explicit write consent to save a model or credential.</Alert> : null}
      {feedback ? <Alert tone={feedback.tone} className="mb-5">{feedback.message}</Alert> : null}
      {settings ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricCard label="Selected data provider" value={settings.data_provider} note="Provider selection is not a network request" icon={RadioTower} />
            <MetricCard label="External network" value={settings.network_enabled ? "Enabled" : "Off"} note="Fixed at server startup" tone={settings.network_enabled ? "warning" : "positive"} icon={settings.network_enabled ? RadioTower : LockKeyhole} />
            <MetricCard label="Configured providers" value={`${settings.providers.filter((item) => item.configured).length} / ${settings.providers.length}`} note="Presence flags only · no values exposed" icon={KeyRound} />
          </div>
          <div className="mt-5 grid items-start gap-5 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">LLM model</p>
                    <p className="mt-1 text-xs text-muted-foreground">Supported provider catalog · applies to this server process</p>
                  </div>
                  <Settings2 className="h-4 w-4 text-accent" />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="model-choice">Model</Label>
                  <Select value={selectedModel || settings.model} onValueChange={setSelectedModel} disabled={!canWrite || !settings.models.length}>
                    <SelectTrigger id="model-choice"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {settings.models.map((item) => (
                        <SelectItem key={item.id} value={item.id}>{item.label} · {item.provider}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button className="w-full" variant="secondary" onClick={() => void saveModel()} disabled={!canWrite || savingModel || !selectedModel || selectedModel === settings.model}>
                  {savingModel ? "Applying…" : "Use model for this process"}
                </Button>
                <p className="text-[10px] leading-relaxed text-muted-foreground">
                  Changing this setting does not submit a model request or edit the shared <span className="mono">.env</span> file. New research jobs record the model selected when submitted.
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
                    <Button className="w-full" onClick={() => void saveCredential()} disabled={!canWrite || savingCredential || !credential}>
                      {savingCredential ? "Saving securely…" : "Save credential"}
                    </Button>
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
