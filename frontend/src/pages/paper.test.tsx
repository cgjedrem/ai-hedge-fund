import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { SessionReportPage } from "@/pages/paper";
import type { SessionReport } from "@/lib/types";

const report = {
  session: "2024-06-04",
  fund: "report-fixture",
  hash: "a".repeat(64),
  prev_hash: null,
  code_version: "pinned-synthetic",
  mandate_hash: "b".repeat(64),
  nav: 100500.125,
  cash: 90000.125,
  positions: { AAPL: 100, MSFT: -0.125 },
  marks: { AAPL: 105, MSFT: 50 },
  benchmark: "SPY",
  benchmark_close: 505,
  rebalance: true,
  executed: {
    as_of: "2024-06-03",
    spec: { risk: { max_position_pct: 0.5, max_gross_exposure: 1 } },
    clamps: [{ limit: "max_gross_exposure", ticker: null, before: 2, after: 1 }],
    risk_scale_factor: 0.5,
    orders: [],
    fills: [],
  },
  proposed: {
    as_of: "2024-06-04",
    universe: ["AAPL", "MSFT"],
    target_weights: { AAPL: 0.4, MSFT: -0.125 },
    final_weights: { AAPL: 0.25, MSFT: -0.125 },
    risk: { max_position_pct: 0.25, max_gross_exposure: 1.25 },
    clamps: [{ limit: "max_position_pct", ticker: "AAPL", before: 0.4, after: 0.25 }],
    risk_scale_factor: null,
    strategies: [{
      name: "synthetic",
      signals: [{
        model_name: "synthetic",
        ticker: "AAPL",
        date: "2024-06-04",
        value: 0.4,
        reasoning: "<script>throw 'inert report text'</script>",
        components: {},
      }],
      convictions: { AAPL: 0.4 },
      weights: { AAPL: 0.4 },
    }],
  },
} satisfies SessionReport;

function renderReport(payload: SessionReport = report) {
  const fetchMock = vi.fn(async () => ({
    ok: true,
    status: 200,
    json: async () => payload,
  }));
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/paper/report-fixture/sessions/2024-06-04"]}>
      <Routes>
        <Route path="/paper/:name/sessions/:session" element={<SessionReportPage />} />
      </Routes>
    </MemoryRouter>,
  );
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("separates recorded proposed and executed clamps from requested and final weights", async () => {
  const fetchMock = renderReport();

  const proposed = await screen.findByRole("region", { name: "Proposed risk" });
  expect(within(proposed).getByText("Max position: 25.00%")).toBeInTheDocument();
  expect(within(proposed).getByText("Max gross exposure: 125.00%")).toBeInTheDocument();
  const proposedClamps = within(proposed).getByRole("region", { name: "Proposed risk clamps table" });
  expect(within(proposedClamps).getByText("Position limit")).toBeInTheDocument();
  expect(within(proposedClamps).getByText("AAPL")).toBeInTheDocument();
  expect(within(proposedClamps).getByText("40.00%")).toBeInTheDocument();
  expect(within(proposedClamps).getByText("25.00%")).toBeInTheDocument();

  const executed = screen.getByRole("region", { name: "Executed risk" });
  expect(within(executed).getByText("Max position: 50.00%")).toBeInTheDocument();
  expect(within(executed).getByText("Risk scale factor: 50.00%")).toBeInTheDocument();
  expect(within(executed).getByText("Gross exposure")).toBeInTheDocument();
  expect(within(executed).getByText("Portfolio")).toBeInTheDocument();
  expect(within(executed).queryByText("Position limit")).not.toBeInTheDocument();

  const weights = screen.getByRole("region", { name: "Proposed weights table" });
  expect(within(weights).getByRole("columnheader", { name: "Requested weight (pre-risk)" })).toBeInTheDocument();
  expect(within(weights).getByRole("columnheader", { name: "Final weight (post-risk)" })).toBeInTheDocument();
  expect(within(weights).getByText("40.00%")).toBeInTheDocument();
  expect(within(weights).getByText("25.00%")).toBeInTheDocument();
  expect(within(weights).getAllByText("-12.50%")).toHaveLength(2);
  expect(screen.getByText("<script>throw 'inert report text'</script>")).toBeInTheDocument();
  expect(document.querySelector("script")).toBeNull();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(fetchMock).toHaveBeenCalledWith("/api/paper/report-fixture/sessions/2024-06-04", expect.objectContaining({ method: "GET" }));
});

it("offers a keyboard-accessible source-hash-bound canonical download without browser JSON conversion", async () => {
  const user = userEvent.setup();
  const fetchMock = renderReport();
  const download = await screen.findByRole("link", { name: "Download canonical JSON" });

  expect(download).toHaveAttribute("href", `/api/paper/report-fixture/sessions/2024-06-04/download?expected_hash=${"a".repeat(64)}`);
  expect(download).not.toHaveAttribute("download");
  screen.getByRole("link", { name: "Paper fund" }).focus();
  await user.tab();
  expect(download).toHaveFocus();
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});

it("labels empty recorded clamp lists without inventing a risk event or scale factor", async () => {
  renderReport({
    ...report,
    executed: { ...report.executed, clamps: [], risk_scale_factor: null },
    proposed: { ...report.proposed, clamps: [] },
  });
  expect(await screen.findByText("No proposed clamps")).toBeInTheDocument();
  expect(screen.getByText("No executed clamps")).toBeInTheDocument();
  expect(screen.getAllByText("No common scale factor recorded.")).toHaveLength(2);
  expect(screen.queryByText("Risk scale factor: 100.00%")).not.toBeInTheDocument();
});

it("distinguishes missing decision records from recorded decisions without clamps", async () => {
  renderReport({ ...report, executed: null, proposed: null });
  expect(await screen.findByText("No proposed decision")).toBeInTheDocument();
  expect(screen.getByText("No executed decision")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Proposed risk" })).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Executed risk" })).not.toBeInTheDocument();
  expect(screen.queryByText("No proposed clamps")).not.toBeInTheDocument();
});

it("keeps tickers from either recorded weight map without treating absent weights as zero", async () => {
  renderReport({
    ...report,
    proposed: { ...report.proposed, final_weights: { AAPL: 0.25, NVDA: 0.1 } },
  });
  const weights = await screen.findByRole("region", { name: "Proposed weights table" });
  const msft = within(weights).getByText("MSFT").closest("tr");
  const nvda = within(weights).getByText("NVDA").closest("tr");
  expect(msft).toHaveTextContent("-12.50%");
  expect(msft).toHaveTextContent("—");
  expect(nvda).toHaveTextContent("10.00%");
  expect(nvda).toHaveTextContent("—");
  expect(within(weights).queryByText("0.00%")).not.toBeInTheDocument();
});
