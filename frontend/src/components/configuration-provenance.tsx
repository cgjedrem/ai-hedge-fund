import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { SectionTitle } from "@/components/page";
import type { ConfigurationField, ConfigurationProvenance, RestartReason, SettingsSource } from "@/lib/types";

const FIELD_LABELS: Record<string, string> = {
  data_provider: "Data provider",
  llm_provider: "LLM provider",
  model: "LLM model",
  endpoint: "LLM endpoint",
  timeout_seconds: "Request timeout",
  parameters: "Model parameters",
};

const SOURCE_LABELS: Record<SettingsSource, string> = {
  default: "Safe default",
  persisted: "Saved in this root",
  environment: "Process environment",
  launch: "Launch argument",
};

const RESTART_REASONS: Record<RestartReason, string> = {
  "stored-version-changed":
    "Saved settings changed outside this server. This server keeps using its effective version until it is restarted; saves from this page are rejected as stale.",
  "override-shadows-stored":
    "A process environment override shadows a saved value. The saved value applies only after the variable is removed and the server is restarted.",
  "active-capture-stale":
    "Settings changed after active work captured its snapshot. That work is never switched to the new settings: its captured version stays recorded, and its next provider call or start is denied (fail-closed). To use the current settings, cancel it or let it end, then review and start it again. A server restart does not change captured work.",
  "owned-runner-stale":
    "A paper runner owned by this server was started on an older settings version, or its captured version is no longer known here. Runners do not re-check settings after launch: it keeps its captured version until it stops or expires. Stop it from its paper fund page and start it again to use the current settings. This page does not stop it, and a server restart does not change it.",
  "owned-runner-unverified":
    "A paper runner may still be running, but this server process cannot verify that it owns it (for example, after a server restart), so its settings version is unknown. It cannot be stopped or restarted from the paper page; offline recovery is required. Nothing is stopped, restarted or reloaded from here.",
};

const CREDENTIAL_STATES: Record<ConfigurationProvenance["credential_captures"][number]["state"], string> = {
  current: "Captured version is still the saved version.",
  superseded:
    "A newer credential was saved after capture. The work is never switched to the new key; its next provider call or start is denied, so it must be reviewed again.",
  "deleted-after-capture":
    "The saved credential was removed after capture. Removal does not erase the captured version or switch the work to another key; its next provider call or start is denied, so it must be reviewed again.",
  "not-captured": "No credential version was captured for this provider.",
  unavailable: "Credential status is unavailable; nothing is inferred.",
};

function formatValue(field: ConfigurationField, value: unknown): string {
  if (value === null || value === undefined) return field.field === "endpoint" ? "Not set" : "Unavailable";
  if (field.redacted) return `${String(value)} endpoint · origin hidden`;
  if (field.field === "timeout_seconds") return `${String(value)} s`;
  if (field.field === "parameters") {
    const entries = Object.entries(value as Record<string, number>);
    return entries.length ? entries.map(([name, item]) => `${name}=${item}`).join(", ") : "Provider defaults";
  }
  return String(value);
}

export function ConfigurationProvenancePanel({ configuration }: { configuration: ConfigurationProvenance }) {
  const { stored, effective, active } = configuration;
  return (
    <Card className="mt-5" aria-label="Configuration provenance">
      <CardHeader>
        <SectionTitle
          title="Configuration provenance"
          note="Stored, effective and captured versions · override sources are named, values that could reveal origins are hidden"
        />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 text-xs sm:grid-cols-3">
          <div>
            <p className="text-muted-foreground">Stored in this root</p>
            <p className="mono mt-1 text-foreground">
              {stored.available ? (stored.present ? `v${stored.version}` : "Nothing saved · defaults") : "Unavailable"}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Effective for new operations</p>
            <p className="mono mt-1 text-foreground">
              v{effective.version} · started at v{effective.startup_version}
            </p>
          </div>
          <div>
            <p className="text-muted-foreground">Active captured work</p>
            <p className="mono mt-1 text-foreground">
              {active.available ? `${active.count} active · ${active.stale_count} on an older version` : "Unavailable"}
            </p>
            {configuration.runners.available ? (
              <p className="mono mt-1 text-muted-foreground">
                {configuration.runners.count} paper runner{configuration.runners.count === 1 ? "" : "s"} live · {configuration.runners.stale_count} on an
                older version
                {configuration.runners.stale_unverified_count ? ` · ${configuration.runners.stale_unverified_count} version unknown` : ""}
                {configuration.runners.ownership_unknown_count ? ` · ${configuration.runners.ownership_unknown_count} owner unverified` : ""}
              </p>
            ) : null}
          </div>
        </div>

        {configuration.restart_required ? (
          <Alert tone="warning">
            <p className="font-semibold">Restart required</p>
            <p className="mt-1 text-xs">Saved settings may not apply everywhere yet. Each reason names what must be restarted or recovered and what happens until then.</p>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs">
              {configuration.restart_reasons.map((reason) => (
                <li key={reason}>{RESTART_REASONS[reason] ?? reason}</li>
              ))}
            </ul>
            <p className="mt-2 text-xs">
              This page never restarts the server or running work, reloads settings into it, or swaps settings in running work. Restart is a manual operator action.
            </p>
          </Alert>
        ) : (
          <p className="text-xs text-muted-foreground">Stored and effective settings agree. No restart is needed.</p>
        )}

        {active.stale_count > 0 ? (
          <p className="text-xs text-muted-foreground">
            {active.stale_count} active operation{active.stale_count === 1 ? " was" : "s were"} captured on an older settings version. Captured work
            is never hot-swapped and a server restart would not change it; its next provider call is denied. New operations use the current effective
            version.
          </p>
        ) : null}

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-2 pr-3 font-medium">Setting</th>
                <th className="py-2 pr-3 font-medium">Stored</th>
                <th className="py-2 pr-3 font-medium">Effective</th>
                <th className="py-2 font-medium">Effective source</th>
              </tr>
            </thead>
            <tbody>
              {configuration.fields.map((field) => (
                <tr key={field.field} className="border-t border-border" data-testid={`provenance-${field.field}`}>
                  <td className="py-2 pr-3 text-foreground">{FIELD_LABELS[field.field] ?? field.field}</td>
                  <td className="mono py-2 pr-3 text-muted-foreground">{stored.available ? formatValue(field, field.stored) : "Unavailable"}</td>
                  <td className="mono py-2 pr-3 text-foreground">{formatValue(field, field.effective)}</td>
                  <td className="py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant={field.override ? "warning" : "muted"}>{SOURCE_LABELS[field.source] ?? field.source}</Badge>
                      {field.override ? <span className="mono text-[10px] text-muted-foreground">{field.override}</span> : null}
                      {field.shadowed ? <Badge variant="warning">Saved value shadowed</Badge> : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {configuration.credential_captures.length ? (
          <div className="space-y-2 border-t border-border pt-3">
            <SectionTitle title="Captured credential versions" note="Version numbers only · values are never returned" />
            {configuration.credential_captures.map((item) => (
              <div key={`${item.capture_id}-${item.provider}`} className="rounded-lg border border-border bg-black/10 p-3 text-xs">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-foreground">
                    {item.subject_id} · <span className="mono">{item.provider}</span> · captured v{item.captured_version}
                    {item.current_version !== null ? ` · saved v${item.current_version}` : ""}
                  </span>
                  <Badge variant={item.state === "current" ? "positive" : "warning"}>{item.state}</Badge>
                </div>
                <p className="mt-2 text-muted-foreground">{CREDENTIAL_STATES[item.state]}</p>
                {item.captured_version_retained === true && item.state !== "current" ? (
                  <p className="mt-1 text-muted-foreground">The captured version remains in private storage for this work.</p>
                ) : null}
                {item.captured_version_retained === false && item.state !== "not-captured" ? (
                  <p className="mt-1 text-warning">The captured version is no longer readable in private storage.</p>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}

        <p className="text-[10px] leading-relaxed text-muted-foreground">
          Environment overrides are read once at server start. Provider keys in the process environment are not used by web operations; only versioned
          credentials saved in this root are captured. Saving here changes the stored version for new operations only.
        </p>
      </CardContent>
    </Card>
  );
}
