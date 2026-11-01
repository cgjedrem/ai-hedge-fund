import { useState, type FormEvent } from "react";
import { ArrowLeft, FileBarChart2, FlaskConical } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { DataTable, type TableColumn } from "@/components/data-table";
import { ArchivePanel } from "@/components/archive-panel";
import { LifecycleActions } from "@/components/lifecycle-actions";
import { EquityChart } from "@/components/equity-chart";
import { MetricCard } from "@/components/metric-card";
import { ErrorState, PageHeader, SectionTitle } from "@/components/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useResource } from "@/lib/hooks";
import type { ResearchCollection, ResearchReport, ResearchSummary, SessionSummary } from "@/lib/types";
import { dateLabel, money, pct } from "@/lib/utils";

export function ResearchPage() {
  const [searchText, setSearchText] = useState("");
  const [search, setSearch] = useState("");
  const [cursorStack, setCursorStack] = useState<(string | null)[]>([null]);
  const cursor = cursorStack[cursorStack.length - 1];
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("cursor", cursor);
  if (search) query.set("search", search);
  const resource = useResource<ResearchCollection>(`/api/research?${query.toString()}`);
  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setCursorStack([null]);
    setSearch(searchText);
  };
  const columns: TableColumn<ResearchSummary>[] = [
    {
      key: "fund",
      label: "Research receipt",
      render: (item) => (
        <div>
          <Link to={`/research/${encodeURIComponent(item.id)}`} className="font-medium text-foreground hover:text-accent hover:underline">
            {item.fund}
          </Link>
          <p className="mono mt-1 text-[10px] text-muted-foreground">{item.id}</p>
        </div>
      ),
    },
    { key: "range", label: "Period", render: (item) => <span className="mono text-[11px]">{item.start} → {item.end}</span> },
    { key: "benchmark", label: "Benchmark", render: (item) => <Badge variant="muted">{item.benchmark}</Badge> },
    { key: "return", label: "Total return", align: "right", render: (item) => <span className="mono">{pct(item.metrics.total_return_pct)}</span> },
    { key: "drawdown", label: "Max drawdown", align: "right", render: (item) => <span className="mono text-rose-300">{pct(item.metrics.max_drawdown_pct)}</span> },
    { key: "cycles", label: "Sessions", align: "right", render: (item) => <span className="mono">{item.session_count}</span> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Research / saved reports"
        title="Research reports"
        description="Persisted backtest receipts. These are historical simulations, not a forecast or live portfolio value."
        actions={<Button asChild><Link to="/backtests"><FlaskConical className="h-3.5 w-3.5" /> New backtest</Link></Button>}
      />
      <form className="mb-5 flex max-w-xl gap-2" onSubmit={submitSearch} role="search" aria-label="Search saved research">
        <Input
          aria-label="Search reports or funds"
          maxLength={128}
          onChange={(event) => setSearchText(event.target.value)}
          placeholder="Search reports or funds"
          type="search"
          value={searchText}
        />
        <Button type="submit" variant="secondary" disabled={resource.loading}>Search</Button>
      </form>
      {resource.loading ? <div className="h-52 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} /> : null}
      {resource.data ? (
        <>
          {resource.data.errors.length > 0 ? (
            <div className="mb-5 space-y-2">
              {resource.data.errors.map((item) => (
                <div key={item.id} className="rounded-lg border border-negative/30 bg-negative/10 px-4 py-3 text-xs text-rose-200">
                  <span className="mono">{item.id}</span><span className="px-2 opacity-50">/</span>{item.error}
                </div>
              ))}
            </div>
          ) : null}
          <Card>
            <CardHeader>
              <SectionTitle
                title="Saved reports"
                note={`${resource.data.total} saved entr${resource.data.total === 1 ? "y" : "ies"}`}
              />
            </CardHeader>
            <CardContent>
              <DataTable
                columns={columns}
                rows={resource.data.items}
                rowKey={(item) => item.id}
                emptyTitle="No research reports"
                emptyDescription="A completed backtest saves its canonical result in the local research directory."
              />
              <div className="mt-4 flex items-center justify-between gap-3 border-t border-border pt-4">
                <p className="text-xs text-muted-foreground">Page {cursorStack.length}</p>
                <div className="flex gap-2">
                  <Button
                    disabled={cursorStack.length <= 1 || resource.loading}
                    onClick={() => setCursorStack((current) => current.slice(0, -1))}
                    variant="secondary"
                  >
                    Previous
                  </Button>
                  <Button
                    disabled={!resource.data.next_cursor || resource.loading}
                    onClick={() => {
                      const nextCursor = resource.data?.next_cursor;
                      if (nextCursor) {
                        setCursorStack((current) => [...current, nextCursor]);
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
        </>
      ) : null}
      <ArchivePanel kind="research" onChange={resource.refresh} />
    </>
  );
}

export function ResearchReportPage() {
  const { reportId = "" } = useParams();
  const navigate = useNavigate();
  const resource = useResource<ResearchReport>(reportId ? `/api/research/${encodeURIComponent(reportId)}` : null);
  const report = resource.data;
  const curve = report
    ? report.dates.map((session, index) => ({
        session,
        nav: report.nav[index] ?? 0,
        benchmark_nav: report.benchmark_nav[index] ?? null,
      }))
    : [];
  const sessionColumns: TableColumn<SessionSummary>[] = [
    { key: "session", label: "Session", render: (item) => <span className="mono text-foreground">{dateLabel(item.session)}</span> },
    { key: "nav", label: "NAV", align: "right", render: (item) => <span className="mono">{money(item.nav)}</span> },
    { key: "cash", label: "Cash", align: "right", render: (item) => <span className="mono">{money(item.cash)}</span> },
    { key: "orders", label: "Orders", align: "right", render: (item) => <span className="mono">{item.orders}</span> },
    { key: "rebalance", label: "Rebalance", render: (item) => <Badge variant={item.rebalance ? "positive" : "muted"}>{item.rebalance ? "Yes" : "No"}</Badge> },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Research / report detail"
        title={report ? `${report.fund} backtest` : "Backtest report"}
        description={report ? `${report.start} → ${report.end} · ${report.rebalance} · ${report.benchmark} benchmark` : "Canonical persisted research report."}
        actions={<>
          <Button asChild variant="secondary"><Link to="/research"><ArrowLeft className="h-3.5 w-3.5" /> All reports</Link></Button>
          <LifecycleActions kind="research" identity={reportId} onComplete={() => navigate("/research")} />
        </>}
      />
      {resource.loading ? <div className="h-48 animate-pulse rounded-xl border border-border bg-white/[0.025]" /> : null}
      {resource.error ? <ErrorState message={resource.error} /> : null}
      {report ? (
        <>
          <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Total return" value={pct(report.metrics.total_return_pct)} note="Start-to-end performance" tone={report.metrics.total_return_pct >= 0 ? "positive" : "negative"} />
            <MetricCard label="Annualized return" value={pct(report.metrics.annualized_return_pct)} note="Annualized from recorded backtest dates" />
            <MetricCard label="Max drawdown" value={pct(report.metrics.max_drawdown_pct)} note="Peak-to-trough NAV change" tone="negative" />
            <MetricCard label="Excess return" value={pct(report.metrics.excess_return_pct)} note={`vs ${report.benchmark}`} tone={report.metrics.excess_return_pct >= 0 ? "positive" : "negative"} />
          </div>
          <div className="mb-5 grid gap-3 sm:grid-cols-3">
            <MetricCard label="Sharpe ratio" value={report.metrics.sharpe_ratio.toFixed(2)} note="Canonical backtest metric" />
            <MetricCard label="Trading cost" value={money(report.metrics.trading_cost, 2)} note="Recorded modeled fills" />
            <MetricCard label="Orders / sessions" value={`${report.metrics.n_orders} / ${report.session_count}`} note={`${report.metrics.n_cycles} rebalance cycles`} />
          </div>
          <div className="grid gap-5">
            <EquityChart data={curve} title="Backtest NAV vs benchmark" description="Saved report series · normalized by canonical backtest result" />
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-foreground">Session history</p>
                    <p className="mt-1 text-xs text-muted-foreground">Stored close values and simulated activity counts</p>
                  </div>
                  <FileBarChart2 className="h-4 w-4 text-accent" />
                </div>
              </CardHeader>
              <CardContent>
                <DataTable columns={sessionColumns} rows={[...report.sessions].reverse()} rowKey={(item) => item.session} emptyTitle="No report sessions" emptyDescription="This report contains no session records." />
              </CardContent>
            </Card>
          </div>
          <p className="mt-4 text-[10px] text-muted-foreground">Fund universe: <span className="mono">{report.universe.join(" · ")}</span></p>
        </>
      ) : null}
      {resource.error ? <ArchivePanel kind="research" onChange={resource.refresh} /> : null}
    </>
  );
}
