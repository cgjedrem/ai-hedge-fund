import { ArrowLeft, ArrowRight, BadgeDollarSign, Box, Clock3, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { DataTable, type TableColumn } from "@/components/data-table";
import { ErrorState, PageHeader, SectionTitle } from "@/components/page";
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
import type { MandateCollection, MandateSummary } from "@/lib/types";
import { money } from "@/lib/utils";

export function MandatesPage() {
  const resource = useResource<MandateCollection>("/api/mandates");
  const columns: TableColumn<MandateSummary>[] = [
    {
      key: "name",
      label: "Mandate",
      render: (item) => (
        <div>
          <Link
            to={`/mandates/${encodeURIComponent(item.name)}`}
            className="font-medium text-foreground underline-offset-4 hover:text-accent hover:underline"
          >
            {item.name}
          </Link>
          <p className="mt-1 text-[10px] text-muted-foreground">{item.strategies.map((strategy) => strategy.title).join(" · ")}</p>
        </div>
      ),
    },
    { key: "cadence", label: "Cadence", render: (item) => <span className="mono">{item.cadence}</span> },
    { key: "capital", label: "Capital", align: "right", render: (item) => <span className="mono text-foreground">{money(item.capital)}</span> },
    {
      key: "approval",
      label: "Approval gate",
      render: (item) => <Badge variant={item.approval_required ? "warning" : "muted"}>{item.approval_required ? "Required" : "Not required"}</Badge>,
    },
    { key: "broker", label: "Book", render: (item) => <Badge variant="muted">{item.broker}</Badge> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Workspace / mandates"
        title="Mandates"
        description="Canonical fund specifications. Existing configurations are never overwritten by the builder."
        actions={
          <Button asChild>
            <Link to="/builder">Create mandate <ArrowRight className="h-3.5 w-3.5" /></Link>
          </Button>
        }
      />
      {resource.loading ? <div className="h-52 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} /> : null}
      {resource.data ? (
        <div className="space-y-5">
          {resource.data.errors.length > 0 ? (
            <Alert tone="warning">
              <p className="font-medium">Invalid mandate files were not hidden.</p>
              <ul className="mt-2 space-y-1 text-xs">
                {resource.data.errors.map((item) => (
                  <li key={item.name}><span className="mono">{item.name}</span><span className="px-2 opacity-50">/</span>{item.error}</li>
                ))}
              </ul>
            </Alert>
          ) : null}
          <Card>
            <CardHeader>
              <SectionTitle title="Saved configurations" note={`${resource.data.items.length} validated mandate${resource.data.items.length === 1 ? "" : "s"}`} />
            </CardHeader>
            <CardContent>
              <DataTable
                columns={columns}
                rows={resource.data.items}
                rowKey={(item) => item.name}
                emptyTitle="No mandates found"
                emptyDescription="Build a mandate to define strategy, risk, cadence, and paper-fund settings."
              />
            </CardContent>
          </Card>
        </div>
      ) : null}
    </>
  );
}

interface MandateDetail extends MandateSummary {
  spec?: Record<string, unknown>;
}

export function MandateDetailPage() {
  const { name = "" } = useParams();
  const navigate = useNavigate();
  const { capabilities } = useDesk();
  const resource = useResource<MandateDetail>(name ? `/api/mandates/${encodeURIComponent(name)}` : null);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [universeText, setUniverseText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const protectedName = capabilities?.protected_names.some((entry) => entry.toLowerCase() === name.toLowerCase()) ?? false;
  const canWrite = capabilities?.writes === true && !protectedName;

  async function deploy(): Promise<void> {
    const universe = universeText
      .split(/[,\s]+/)
      .map((ticker) => ticker.trim().toUpperCase())
      .filter(Boolean);
    if (universe.length === 0) {
      setError("Enter at least one ticker for the paper universe.");
      return;
    }
    if (universe.some((ticker) => !/^[A-Z0-9.^-]{1,16}$/.test(ticker))) {
      setError("Tickers must use up to 16 ASCII letters, digits, dots, carets, or hyphens.");
      return;
    }
    if (new Set(universe).size !== universe.length) {
      setError("Each ticker must appear only once.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await apiPost<{ name: string }>("/api/mandates/" + encodeURIComponent(name) + "/deploy", { universe });
      setDialogOpen(false);
      navigate(`/paper/${encodeURIComponent(result.name)}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Deployment failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Workspace / mandates / detail"
        title={name || "Mandate"}
        description="This is the stored canonical mandate. Deployment creates a new paper book; it does not start a runner."
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/mandates"><ArrowLeft className="h-3.5 w-3.5" /> All mandates</Link>
            </Button>
            <Button onClick={() => { setError(null); setDialogOpen(true); }} disabled={!canWrite}>
              Deploy to paper
            </Button>
          </>
        }
      />
      {!canWrite && capabilities ? (
        <Alert tone="warning" className="mb-5">
          {protectedName
            ? "Protected fund names cannot be modified by this web desk."
            : "Deployment is disabled because this server started without write capability."}
        </Alert>
      ) : null}
      {resource.loading ? <div className="h-52 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} /> : null}
      {resource.data ? (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.7fr)]">
          <div className="space-y-5">
            <Card>
              <CardHeader>
                <CardTitle>Strategy allocation</CardTitle>
                <p className="text-xs text-muted-foreground">Library definitions and configured weights</p>
              </CardHeader>
              <CardContent className="space-y-3">
                {resource.data.strategies.map((strategy) => (
                  <div key={strategy.name} className="rounded-lg border border-border bg-black/10 p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-foreground">{strategy.title}</h3>
                        <p className="mono mt-1 text-[10px] text-muted-foreground">{strategy.name}</p>
                      </div>
                      <Badge variant="muted">{strategy.mode.replaceAll("_", " ")}</Badge>
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                      <span className="mono">Weight {strategy.weight}</span>
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Canonical specification</CardTitle>
                <p className="text-xs text-muted-foreground">Model output remains text; no HTML interpretation.</p>
              </CardHeader>
              <CardContent>
                <pre className="max-h-[520px] overflow-auto rounded-lg border border-border bg-[#090d11] p-4 text-[11px] leading-relaxed text-slate-300">
                  {JSON.stringify(resource.data.spec ?? {}, null, 2)}
                </pre>
              </CardContent>
            </Card>
          </div>
          <div className="space-y-5">
            <Card>
              <CardHeader><CardTitle>Mandate parameters</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <InfoRow icon={BadgeDollarSign} label="Starting capital" value={money(resource.data.capital)} />
                <InfoRow icon={Clock3} label="Decision cadence" value={resource.data.cadence} />
                <InfoRow icon={ShieldAlert} label="Benchmark" value={resource.data.benchmark} />
                <InfoRow icon={ShieldCheck} label="Approval" value={resource.data.approval_required ? "Required before next execution" : "Not required"} />
                <InfoRow icon={Box} label="Broker book" value={resource.data.broker} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Deployment boundary</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs leading-relaxed text-muted-foreground">
                  The paper book is an isolated ledger. Deployment does not create orders or start a process. Existing names are rejected by the server.
                </p>
                <Button className="w-full" onClick={() => setDialogOpen(true)} disabled={!canWrite}>
                  Choose universe <ArrowRight className="h-3.5 w-3.5" />
                </Button>
                <p className="text-[10px] leading-relaxed text-muted-foreground">
                  {capabilities?.deferred_actions.manual_run ?? "Manual run is disabled because runner ownership is not verified."}
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      ) : null}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Deploy {name} to a paper ledger</DialogTitle>
            <DialogDescription>Enter the ticker universe. This creates a paper book only; no runner starts and no order is submitted.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="paper-universe">Tickers</Label>
            <Input
              id="paper-universe"
              value={universeText}
              onChange={(event) => setUniverseText(event.target.value)}
              placeholder="AAPL, MSFT, SPY"
              autoComplete="off"
            />
            <p className="text-[10px] text-muted-foreground">Comma or space separated · up to 25 unique tickers.</p>
          </div>
          {error ? <Alert tone="danger">{error}</Alert> : null}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)} disabled={busy}>Cancel</Button>
            <Button onClick={() => void deploy()} disabled={busy || !canWrite}>{busy ? "Deploying…" : "Create paper book"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function InfoRow({ icon: Icon, label, value }: { icon: typeof BadgeDollarSign; label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-border/70 pb-3 last:border-0 last:pb-0">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5 text-accent" />
        <span>{label}</span>
      </div>
      <span className="mono text-right text-xs text-foreground">{value}</span>
    </div>
  );
}
