import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { DeskProvider } from "@/lib/hooks";
import { PaperDetailPage, SessionReportPage } from "@/pages/paper";
import type { Capabilities, Operation, PaperOperationPreview, PaperSnapshot, RunnerState, SessionReport } from "@/lib/types";

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
  window.localStorage.clear();
  window.sessionStorage.clear();
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

const FUND = "runner-fixture";
const HEAD = "e".repeat(64);
const OPERATION_ID = "f".repeat(32);

const capabilities: Capabilities = {
  mode: "live",
  read_only: false,
  writes: true,
  network: true,
  local_operator_only: true,
  csrf_authenticates_users: false,
  container_observer: false,
  enrollment_state: "enrolled",
  write_authority: "protocol-native",
  write_unavailable_reason: null,
  protected_names: [],
  mutation_token: "synthetic-mutation-token",
  deferred_actions: {},
};

const stoppedRunner: RunnerState = { status: "stopped", available: false, reason: null };

function paperSnapshot(runner: RunnerState): PaperSnapshot {
  return {
    name: FUND,
    spec: { name: FUND, approval_required: false },
    universe: ["AAPL"],
    broker: "paper",
    created: "2024-06-01T00:00:00+00:00",
    cadence: "daily",
    last_session: "2024-06-03",
    last_record_hash: HEAD,
    nav: 100_000,
    cash: 100_000,
    positions: [],
    curve: [],
    sessions: [],
    pending: null,
    approval: null,
    next_run: null,
    halted: null,
    halt_state: "clear",
    ledger: { ok: true, error: null },
    runner,
    live_value: {
      status: "unavailable",
      value: null,
      partial_estimate: null,
      as_of: null,
      provenance: null,
      expected_head: HEAD,
      recorded_nav: null,
      coverage: { total: 0, quoted: 0, usable: 0, missing: 0, stale: 0, errors: 0 },
      quotes: [],
      reason: "Synthetic fixture.",
    },
    scorecard: null,
    scorecard_error: null,
  };
}

function paperPreview(kind: "tick" | "runner", dueSet: string[]): PaperOperationPreview {
  return {
    preview_id: "1".repeat(32),
    preview_digest: "2".repeat(64),
    confirmation_token: "synthetic-confirmation",
    action: kind === "tick" ? "paper-tick" : "paper-runner-start",
    subject_id: FUND,
    expected_head: HEAD,
    due_set: dueSet,
    capture_id: "3".repeat(32),
    capture_digest: "4".repeat(64),
    expires_at: "2099-01-01T00:00:00Z",
    payload: kind === "runner" ? { max_sessions: 1, max_runtime_minutes: 60 } : { kind: "manual-tick", session: dueSet[0] },
    capture: {},
    estimate: {
      maximum_model_calls_per_session: 3,
      maximum_calls: 3,
      maximum_resources: 1,
      maximum_cost_usd: 0,
      market_data_provider: "synthetic-free",
    },
    warnings: ["Synthetic readiness warning."],
  };
}

function paperOperation(requestId: string, overrides: Partial<Operation> = {}): Operation {
  return {
    operation_id: OPERATION_ID,
    id: OPERATION_ID,
    request_id: requestId,
    action: "paper-tick",
    subject_id: FUND,
    fund: FUND,
    capture_id: "3".repeat(32),
    capture_digest: "4".repeat(64),
    status: "accepted",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:01Z",
    payload: {},
    result: null,
    progress: 0,
    provider: null,
    model: null,
    report_id: null,
    error: null,
    cancel_requested: false,
    status_url: `/api/operations/${OPERATION_ID}`,
    ...overrides,
  };
}

interface Call {
  path: string;
  method: string;
  body: Record<string, unknown> | null;
}

type Handler = (call: Call) => Response | Promise<Response>;

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}

function renderDesk(runner: RunnerState, handlers: Record<string, Handler> = {}) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const call = { path, method, body: typeof init?.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : null };
    calls.push(call);
    const handler = handlers[`${method} ${path}`];
    if (handler) return handler(call);
    if (method !== "GET") throw new Error(`Unexpected mutation: ${method} ${path}`);
    if (path === "/api/capabilities") return json(capabilities);
    if (path === `/api/paper/${FUND}`) return json(paperSnapshot(runner));
    if (path === `/api/paper/${FUND}/runner`) return json(runner);
    if (path.startsWith(`/api/paper/${FUND}/sessions?`)) {
      return json({ items: [], errors: [], next_cursor: null, limit: 50, total: 0, search: "", ledger: { ok: true, error: null } });
    }
    return json({ detail: "Not found.", code: "not-found", message: "Not found.", refresh_required: false, retry_policy: "none" }, 404);
  }));
  render(
    <DeskProvider>
      <MemoryRouter initialEntries={[`/paper/${FUND}`]}>
        <Routes><Route path="/paper/:name" element={<PaperDetailPage />} /></Routes>
      </MemoryRouter>
    </DeskProvider>,
  );
  return calls;
}

const mutations = (calls: Call[]) => calls.filter((call) => call.method !== "GET");

async function enabledButton(name: string) {
  const button = await screen.findByRole("button", { name });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

it("reviews readiness, capture and the exact due-set before one accepted manual tick", async () => {
  const user = userEvent.setup();
  let accept!: (value: Response) => void;
  const calls = renderDesk(stoppedRunner, {
    [`POST /api/paper/${FUND}/tick/preview`]: () => json(paperPreview("tick", ["2024-06-04"])),
    [`POST /api/paper/${FUND}/tick`]: () => new Promise<Response>((resolve) => { accept = resolve; }),
    [`GET /api/operations/${OPERATION_ID}`]: (call) => json(paperOperation(String(mutations(calls).at(-1)?.body?.request_id ?? call.path), { status: "running", progress: 30 })),
  });

  await user.click(await enabledButton("Manual one-session tick"));
  const dialog = await screen.findByRole("dialog", { name: "Confirm one-session paper tick" });
  expect(mutations(calls).map((call) => call.path)).toEqual([`/api/paper/${FUND}/tick/preview`]);
  expect(mutations(calls)[0].body).toEqual({ expected_head: HEAD });
  expect(within(dialog).getByText(/eeeeeeee/)).toBeInTheDocument();
  expect(within(dialog).getByText(/synthetic-free/)).toBeInTheDocument();
  expect(within(dialog).getByText("Synthetic readiness warning.")).toBeInTheDocument();
  expect(within(dialog).queryByText(/Nothing due now/)).toBeNull();

  const acceptButton = within(dialog).getByRole("button", { name: "Accept one-session tick" });
  await user.click(acceptButton);
  await user.click(acceptButton);
  await waitFor(() => expect(mutations(calls)).toHaveLength(2));
  const admission = mutations(calls)[1];
  expect(admission.path).toBe(`/api/paper/${FUND}/tick`);
  expect(admission.body).toMatchObject({
    preview_id: "1".repeat(32),
    preview_digest: "2".repeat(64),
    confirmation_token: "synthetic-confirmation",
    expected_head: HEAD,
    due_set: ["2024-06-04"],
  });
  expect(admission.body).not.toHaveProperty("max_sessions");

  accept(json(paperOperation(String(admission.body?.request_id)), 202));
  expect(await screen.findByText(/Manual tick · (accepted|running)/)).toBeInTheDocument();
  await screen.findByText("Manual tick · running");
  expect(mutations(calls)).toHaveLength(2);
  expect(window.localStorage.getItem(`aihf.paper.${FUND}.operation`)).toBe(OPERATION_ID);
  expect(JSON.stringify({ ...window.localStorage })).not.toContain("synthetic-confirmation");
  expect(JSON.stringify({ ...window.localStorage })).not.toContain("synthetic-mutation-token");
});

it("labels an empty reviewed runner due-set as nothing due and sends the reviewed bounds", async () => {
  const user = userEvent.setup();
  const calls = renderDesk(stoppedRunner, {
    [`POST /api/paper/${FUND}/runner/preview`]: () => json(paperPreview("runner", [])),
  });

  await user.click(await enabledButton("Start runner"));
  const dialog = await screen.findByRole("dialog", { name: "Confirm finite runner start" });
  expect(within(dialog).getByText(/Nothing due now; the runner waits/)).toBeInTheDocument();
  expect(within(dialog).getByText("1 sessions / 60 minutes")).toBeInTheDocument();
  expect(mutations(calls)[0].body).toEqual({ expected_head: HEAD, max_sessions: 1, max_runtime_minutes: 60 });

  await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(mutations(calls)).toHaveLength(1);
});

it("reports a nothing-due manual preview denial without opening an admission", async () => {
  const user = userEvent.setup();
  const calls = renderDesk(stoppedRunner, {
    [`POST /api/paper/${FUND}/tick/preview`]: () => json({
      detail: "No paper session is currently due.",
      code: "request-conflict",
      message: "No paper session is currently due.",
      refresh_required: false,
      retry_policy: "reload",
    }, 409),
  });

  await user.click(await enabledButton("Manual one-session tick"));
  expect(await screen.findByText(/No paper session is currently due/)).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(mutations(calls).map((call) => call.path)).toEqual([`/api/paper/${FUND}/tick/preview`]);
});

it.each([
  [{ status: "starting", available: false, reason: "Owned runner is starting." }, "Runner starting"],
  [{ status: "running", available: true, reason: null }, "Runner running"],
  [{ status: "stopping", available: true, reason: null }, "Runner stopping"],
  [{ status: "failed", available: false, reason: "Child exited." }, "Runner error"],
  [{ status: "unknown", available: false, reason: "Owner cannot be verified." }, "Runner unverified"],
] as const)("labels the control panel for runner state %o and blocks new paper work while not inactive", async (runner, label) => {
  renderDesk(runner);

  expect(await screen.findByText(label)).toBeInTheDocument();
  const tick = screen.getByRole("button", { name: "Manual one-session tick" });
  if (runner.status === "failed") await waitFor(() => expect(tick).toBeEnabled());
  else expect(tick).toBeDisabled();
});

it("does not resubmit when an accepted response is lost and keeps the request identity for inspection", async () => {
  const user = userEvent.setup();
  const calls = renderDesk(stoppedRunner, {
    [`POST /api/paper/${FUND}/tick/preview`]: () => json(paperPreview("tick", ["2024-06-04"])),
    [`POST /api/paper/${FUND}/tick`]: () => Promise.reject(new TypeError("synthetic connection reset")),
  });

  await user.click(await enabledButton("Manual one-session tick"));
  const dialog = await screen.findByRole("dialog", { name: "Confirm one-session paper tick" });
  await user.click(within(dialog).getByRole("button", { name: "Accept one-session tick" }));

  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const requestId = String(mutations(calls)[1].body?.request_id);
  expect(window.localStorage.getItem(`aihf.pending-operation.${requestId}`)).not.toBeNull();
  expect(window.localStorage.getItem(`aihf.paper.${FUND}.operation`)).toBeNull();
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(mutations(calls).map((call) => call.path)).toEqual([`/api/paper/${FUND}/tick/preview`, `/api/paper/${FUND}/tick`]);
});

it("restores a persisted operation on reload by reading it and rejects a late older status", async () => {
  window.localStorage.setItem(`aihf.paper.${FUND}.operation`, OPERATION_ID);
  const reads = [
    paperOperation("synthetic-request", { status: "running", progress: 60, updated_at: "2026-01-01T00:00:05Z" }),
    paperOperation("synthetic-request", { status: "accepted", progress: 10, updated_at: "2026-01-01T00:00:02Z" }),
    paperOperation("synthetic-request", { status: "running", progress: 60, updated_at: "2026-01-01T00:00:05Z" }),
  ];
  let read = 0;
  const calls = renderDesk({ status: "running", available: true, reason: null }, {
    [`GET /api/operations/${OPERATION_ID}`]: () => json(reads[Math.min(read++, reads.length - 1)]),
  });

  expect(await screen.findByText("Manual tick · running")).toBeInTheDocument();
  await waitFor(() => expect(read).toBeGreaterThanOrEqual(2), { timeout: 4_000 });
  expect(screen.getByText("Manual tick · running")).toBeInTheDocument();
  expect(screen.queryByText("Manual tick · accepted")).toBeNull();
  expect(screen.getByRole("progressbar", { name: "Paper operation progress" })).toHaveAttribute("aria-valuenow", "60");
  expect(mutations(calls)).toEqual([]);
});
