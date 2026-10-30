import { ArrowRight, BadgeDollarSign, BarChart3, BriefcaseBusiness, Radio, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";

import { DataTable, type TableColumn } from "@/components/data-table";
import { MetricCard } from "@/components/metric-card";
import { ErrorState, PageHeader } from "@/components/page";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDesk, useResource } from "@/lib/hooks";
import type { HomeData, PaperSummary } from "@/lib/types";
import { dateLabel, money } from "@/lib/utils";

export function HomePage() {
  const { capabilities } = useDesk();
  const resource = useResource<HomeData>("/api/home");
  const data = resource.data;

  const columns: TableColumn<PaperSummary>[] = [
    {
      key: "name",
      label: "Paper fund",
      render: (item) => (
        <Link
          to={`/paper/${encodeURIComponent(item.name)}`}
          className="font-medium text-foreground underline-offset-4 hover:text-accent hover:underline"
        >
          {item.name}
        </Link>
      ),
    },
    { key: "cadence", label: "Cadence", render: (item) => <span className="mono">{item.cadence}</span> },
    { key: "nav", label: "Recorded NAV", align: "right", render: (item) => <span className="mono text-foreground">{money(item.nav)}</span> },
    { key: "last", label: "Last record", render: (item) => <span className="mono text-[11px]">{dateLabel(item.last_session)}</span> },
    {
      key: "state",
      label: "State",
      render: (item) => (
        <Badge variant={!item.ledger_ok ? "negative" : item.halted ? "warning" : "positive"}>
          {!item.ledger_ok ? "Ledger issue" : item.halted ? "Halted" : "Recorded"}
        </Badge>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Desk overview · local workspace"
        title="Research with a clear view of risk."
        description="Inspect canonical mandates, paper ledgers, and saved research. This desk does not execute orders or fetch live quotes."
        actions={
          <>
            <Button asChild variant="secondary">
              <Link to="/mandates">
                View mandates <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </Button>
            <Button asChild>
              <Link to="/builder">Create mandate</Link>
            </Button>
          </>
        }
      />

      {resource.loading ? <div className="mb-6 h-24 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <div className="mb-6"><ErrorState message={resource.error} /></div> : null}

      {data ? (
        <>
          {data.errors.length > 0 ? (
            <Alert tone="warning" className="mb-6">
              <p className="font-medium">Some saved records need attention.</p>
              <ul className="mt-2 space-y-1 text-xs">
                {data.errors.slice(0, 5).map((item, index) => (
                  <li key={`${item.name ?? item.id ?? "record"}-${index}`}>
                    <span className="mono">{item.name ?? item.id ?? "record"}</span>
                    <span className="px-2 opacity-50">/</span>
                    <span>{item.error}</span>
                  </li>
                ))}
              </ul>
            </Alert>
          ) : null}

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Recorded paper NAV"
              value={money(data.recorded_nav_total)}
              note="Latest ledger values · not live valuation"
              icon={BadgeDollarSign}
            />
            <MetricCard
              label="Paper funds"
              value={String(data.paper_count)}
              note="Locally deployed fund books"
              icon={BriefcaseBusiness}
            />
            <MetricCard
              label="Mandates"
              value={String(data.mandate_count)}
              note="Validated strategy configurations"
              icon={ShieldCheck}
            />
            <MetricCard
              label="Saved research"
              value={String(data.research_count)}
              note="Persisted backtest reports"
              icon={BarChart3}
            />
          </div>

          <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(0,1.65fr)_minmax(280px,0.8fr)]">
            <Card>
              <CardHeader className="flex-row items-start justify-between gap-4">
                <div>
                  <CardTitle>Paper books</CardTitle>
                  <p className="mt-1 text-xs text-muted-foreground">Latest verified ledger snapshot for each fund</p>
                </div>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/paper">All funds <ArrowRight className="h-3 w-3" /></Link>
                </Button>
              </CardHeader>
              <CardContent>
                <DataTable
                  columns={columns}
                  rows={data.paper_funds}
                  rowKey={(item) => item.name}
                  emptyTitle="No paper books yet"
                  emptyDescription="Deploy a validated mandate to create a paper ledger. Deployment never starts a runner."
                />
              </CardContent>
            </Card>

            <div className="space-y-5">
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between gap-3">
                    <CardTitle>Local capability boundary</CardTitle>
                    <Radio className="h-4 w-4 text-accent" />
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">Data mode</span>
                    <Badge variant={data.mode === "demo" ? "warning" : "muted"}>
                      {data.mode === "demo" ? "Synthetic demo" : "Local records"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">Writes</span>
                    <Badge variant={capabilities?.writes ? "warning" : "positive"}>
                      {capabilities?.writes ? "Explicitly enabled" : "Read only"}
                    </Badge>
                  </div>
                  <div className="flex items-center justify-between gap-3 text-xs">
                    <span className="text-muted-foreground">External network</span>
                    <Badge variant={capabilities?.network ? "warning" : "positive"}>
                      {capabilities?.network ? "Enabled at startup" : "Off"}
                    </Badge>
                  </div>
                  <p className="border-t border-border pt-3 text-[11px] leading-relaxed text-muted-foreground">
                    Runner ownership is not verified by this web process. Start, stop, and manual-run controls stay disabled.
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle>Recorded values, not quotes</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-xs leading-relaxed text-muted-foreground">
                    NAV and holdings come from the verified local ledger. Live estimates are explicitly unavailable unless a separate, consented workflow supplies them.
                  </p>
                  <Link to="/settings" className="mt-4 inline-flex items-center gap-2 text-xs font-medium text-accent hover:underline">
                    Review environment settings <ArrowRight className="h-3 w-3" />
                  </Link>
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}
