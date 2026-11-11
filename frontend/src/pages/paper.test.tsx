import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { DeskProvider } from "@/lib/hooks";
import { PaperDetailPage, SessionReportPage } from "@/pages/paper";
import type {
  Capabilities,
  Operation,
  PaperOperationPreview,
  PaperReconciliationPreview,
  PaperSnapshot,
  PaperTickIntentReconciliationPreview,
  RunnerState,
  SessionReport,
} from "@/lib/types";

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
  operator_trust_warning: null,
  protected_names: [],
  mutation_token: "synthetic-mutation-token",
  deferred_actions: {},
};

const stoppedRunner: RunnerState = { status: "stopped", available: false, reason: null };

function paperSnapshot(runner: RunnerState, halted = false): PaperSnapshot {
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
    halted: halted ? "synthetic tick failure" : null,
    halt_state: halted ? "halted" : "clear",
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
    outcome: kind === "tick" && dueSet.length === 0 ? "nothing-due" : "ready",
    capture_id: "3".repeat(32),
    capture_digest: "4".repeat(64),
    expires_at: "2099-01-01T00:00:00Z",
    payload: kind === "runner"
      ? { max_sessions: 1, max_runtime_minutes: 60 }
      : dueSet.length === 0
        ? { kind: "manual-no-work" }
        : { kind: "manual-tick", session: dueSet[0] },
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

function paperReconciliationPreview(
  overrides: Partial<PaperReconciliationPreview> = {},
): PaperReconciliationPreview {
  return {
    schema_version: 1,
    required: true,
    recoverable: true,
    reason: "ready",
    failure_id: "a".repeat(64),
    failed_request_id: "tick-synthetic",
    operation_id: "b".repeat(32),
    expected_head: HEAD,
    current_head: HEAD,
    broker_book_sha256: "c".repeat(64),
    fill_identity_sha256: "d".repeat(64),
    capture_id: "e".repeat(32),
    capture_digest: "f".repeat(64),
    book_matches_ledger: true,
    head_matches_failure: true,
    decision: "confirm-paper-book-matches-ledger",
    residual_uncertainty: "external-broker-state-not-applicable-local-paper-only",
    preview_digest: "1".repeat(64),
    ...overrides,
  };
}

function paperTickIntentPreview(
  overrides: Partial<PaperTickIntentReconciliationPreview> = {},
): PaperTickIntentReconciliationPreview {
  return {
    schema_version: 1,
    required: true,
    recoverable: true,
    reason: "ready",
    intent_request_id: null,
    intent_session: "2024-06-03",
    intent_digest: "7".repeat(64),
    metadata_complete: false,
    corrupt_event_digests: [],
    expected_head: null,
    current_head: HEAD,
    broker_book_sha256: "8".repeat(64),
    fill_identity_sha256: "9".repeat(64),
    book_matches_ledger: true,
    head_matches_intent: false,
    decision: "confirm-paper-book-matches-ledger",
    residual_uncertainty: "external-broker-state-not-applicable-local-paper-only",
    preview_digest: "a".repeat(64),
    ...overrides,
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

function renderDesk(
  runner: RunnerState,
  handlers: Record<string, Handler> = {},
  caps: Capabilities = capabilities,
) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    const call = { path, method, body: typeof init?.body === "string" ? JSON.parse(init.body) as Record<string, unknown> : null };
    calls.push(call);
    const handler = handlers[`${method} ${path}`];
    if (handler) return handler(call);
    if (method !== "GET") throw new Error(`Unexpected mutation: ${method} ${path}`);
    if (path === "/api/capabilities") return json(caps);
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

it("shows operator responsibility in trusted single-writer mode", async () => {
  const warning = "Stop and exclude every other program that can reach this root.";
  renderDesk(
    stoppedRunner,
    {},
    {
      ...capabilities,
      write_authority: "operator-trusted-single-writer",
      operator_trust_warning: warning,
    },
  );

  const notice = await screen.findByTestId("operator-trust-warning");
  expect(notice).toHaveTextContent("Trusted single-writer mode.");
  expect(notice).toHaveTextContent(warning);
});

async function enabledButton(name: string) {
  const button = await screen.findByRole("button", { name });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
}

it("reuses the reviewed verdict request ID after a lost response", async () => {
  const user = userEvent.setup();
  const pending = {
    decision_as_of: "2024-06-04",
    source_record_hash: HEAD,
    universe: ["AAPL"],
    target_weights: { AAPL: 1 },
    final_weights: { AAPL: 1 },
    strategies: ["synthetic"],
  };
  let attempts = 0;
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}`]: () => json({
      ...paperSnapshot(stoppedRunner),
      spec: { name: FUND, approval_required: true },
      pending,
    }),
    [`POST /api/paper/${FUND}/approval`]: () => {
      attempts += 1;
      return attempts === 1 ? Promise.reject(new TypeError("synthetic response loss")) : json({ saved: true });
    },
  });

  await user.click(await enabledButton("Approve"));
  await user.click(screen.getByRole("button", { name: "Approve displayed decision" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  await user.click(await enabledButton("Approve"));
  await user.click(screen.getByRole("button", { name: "Approve displayed decision" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(2));

  const submissions = mutations(calls);
  const requestId = submissions[0].body?.request_id;
  expect(requestId).toEqual(expect.stringMatching(/^[a-f0-9]{32}$/));
  expect(submissions[1].body).toMatchObject({
    request_id: requestId,
    verdict: "approve",
    decision_as_of: pending.decision_as_of,
    source_record_hash: pending.source_record_hash,
  });
});

it("reuses a Halt request ID after a lost response", async () => {
  const user = userEvent.setup();
  let attempts = 0;
  const calls = renderDesk(stoppedRunner, {
    [`POST /api/paper/${FUND}/halt`]: () => {
      attempts += 1;
      return attempts === 1 ? Promise.reject(new TypeError("synthetic Halt response loss")) : json({ name: FUND, halted: true });
    },
  });

  await user.click(await enabledButton("Halt"));
  let dialog = await screen.findByRole("dialog", { name: `Halt ${FUND}` });
  await user.type(within(dialog).getByLabelText("Reason"), "operator pause");
  await user.click(within(dialog).getByRole("button", { name: "Record halt" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const requestId = mutations(calls)[0].body?.request_id;
  expect(requestId).toMatch(/^[a-f0-9]{32}$/);

  await user.click(await enabledButton("Halt"));
  dialog = await screen.findByRole("dialog", { name: `Halt ${FUND}` });
  expect(within(dialog).getByLabelText("Reason")).toHaveValue("operator pause");
  await user.click(within(dialog).getByRole("button", { name: "Record halt" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(2));

  expect(mutations(calls)[1].body).toEqual({ request_id: requestId, reason: "operator pause" });
  expect(await screen.findByText("Halt state recorded in the ledger. Runner process control is not available here.")).toBeInTheDocument();
});

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

it("reviews and records an idempotent nothing-due manual operation", async () => {
  const user = userEvent.setup();
  let requestId = "";
  const calls = renderDesk(stoppedRunner, {
    [`POST /api/paper/${FUND}/tick/preview`]: () => json(paperPreview("tick", [])),
    [`POST /api/paper/${FUND}/tick`]: (call) => {
      requestId = String(call.body?.request_id ?? "");
      return json(paperOperation(requestId), 202);
    },
    [`GET /api/operations/${OPERATION_ID}`]: () => json(paperOperation(requestId, {
      status: "completed",
      progress: 100,
      result: { outcome: "nothing-due" },
    })),
  });

  await user.click(await enabledButton("Manual one-session tick"));
  const dialog = await screen.findByRole("dialog", { name: "Confirm one-session paper tick" });
  expect(within(dialog).getByText(/No session is due\. Accept records a completed no-work result; no session will be created\./)).toBeInTheDocument();
  expect(mutations(calls).map((call) => call.path)).toEqual([`/api/paper/${FUND}/tick/preview`]);

  await user.click(within(dialog).getByRole("button", { name: "Accept no-work result" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(2));
  expect(mutations(calls)[1].body).toMatchObject({
    expected_head: HEAD,
    due_set: [],
  });
  expect(await screen.findByText("Manual operation completed with nothing due. No session was recorded.")).toBeInTheDocument();
  expect(requestId).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  expect(window.localStorage.getItem(`aihf.paper.${FUND}.operation`)).toBe(OPERATION_ID);
  expect(JSON.stringify({ ...window.localStorage })).not.toContain("synthetic-confirmation");
});

it("reviews hash-bound local reconciliation before resuming without retrying the failed tick", async () => {
  const user = userEvent.setup();
  const preview = paperReconciliationPreview();
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}`]: () => json(paperSnapshot(stoppedRunner, true)),
    [`GET /api/paper/${FUND}/reconciliation`]: () => json({
      name: FUND,
      halted: "synthetic tick failure",
      resume_allowed: true,
      preview,
    }),
    [`POST /api/paper/${FUND}/resume`]: () => json({
      name: FUND,
      halted: false,
      reconciliation_id: "2".repeat(64),
    }),
  });

  expect(await screen.findByText("Ambiguous tick failure")).toBeInTheDocument();
  expect(screen.getByText(/Local paper book digest:/)).toBeInTheDocument();
  expect(screen.getByText(/^c{10}…c{6}$/)).toBeInTheDocument();
  await user.click(await enabledButton("Review recovery"));
  const dialog = await screen.findByRole("dialog", { name: "Reconcile and resume paper fund" });
  expect(dialog).toHaveTextContent("Failed tick will not be retried");
  expect(dialog).toHaveTextContent("No runner will be started");

  await user.click(within(dialog).getByRole("button", { name: "Confirm recovery and resume" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  expect(mutations(calls)[0].path).toBe(`/api/paper/${FUND}/resume`);
  expect(mutations(calls)[0].body).toMatchObject({
    failure_id: preview.failure_id,
    preview_digest: preview.preview_digest,
    decision: preview.decision,
  });
  expect(mutations(calls)[0].body?.request_id).toMatch(/^[a-f0-9]{32}$/);
  expect(await screen.findByText("Reconciliation receipt recorded. Halt cleared. Failed tick was not retried; no runner was started.")).toBeInTheDocument();
});

it("does not auto-resubmit a lost recovery response and reuses its request identity after review", async () => {
  const user = userEvent.setup();
  const preview = paperReconciliationPreview();
  let attempts = 0;
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}`]: () => json(paperSnapshot(stoppedRunner, true)),
    [`GET /api/paper/${FUND}/reconciliation`]: () => json({
      name: FUND,
      halted: "synthetic tick failure",
      resume_allowed: true,
      preview,
    }),
    [`POST /api/paper/${FUND}/resume`]: () => {
      attempts += 1;
      return attempts === 1
        ? Promise.reject(new TypeError("synthetic recovery response loss"))
        : json({ name: FUND, halted: false, reconciliation_id: "2".repeat(64) });
    },
  });

  await user.click(await enabledButton("Review recovery"));
  const firstDialog = await screen.findByRole("dialog", { name: "Reconcile and resume paper fund" });
  await user.click(within(firstDialog).getByRole("button", { name: "Confirm recovery and resume" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  const firstRequestId = mutations(calls)[0].body?.request_id;
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await new Promise((resolve) => setTimeout(resolve, 50));
  expect(mutations(calls)).toHaveLength(1);

  await user.click(await enabledButton("Review recovery"));
  const secondDialog = await screen.findByRole("dialog", { name: "Reconcile and resume paper fund" });
  await user.click(within(secondDialog).getByRole("button", { name: "Confirm recovery and resume" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(2));

  expect(mutations(calls)[1].body?.request_id).toBe(firstRequestId);
  expect(await screen.findByText("Reconciliation receipt recorded. Halt cleared. Failed tick was not retried; no runner was started.")).toBeInTheDocument();
});

it("resumes a manual halt with an empty confirmation and no paper operation", async () => {
  const user = userEvent.setup();
  const preview = paperReconciliationPreview({
    required: false,
    reason: "no-ambiguous-tick-failure",
    failure_id: null,
    failed_request_id: null,
    operation_id: null,
    expected_head: null,
    current_head: null,
    broker_book_sha256: null,
    capture_id: null,
    capture_digest: null,
    book_matches_ledger: false,
    head_matches_failure: false,
    preview_digest: null,
  });
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}`]: () => json(paperSnapshot(stoppedRunner, true)),
    [`GET /api/paper/${FUND}/reconciliation`]: () => json({
      name: FUND,
      halted: "operator pause",
      resume_allowed: true,
      preview,
    }),
    [`POST /api/paper/${FUND}/resume`]: () => json({
      name: FUND,
      halted: false,
      reconciliation_id: null,
    }),
  });

  expect(await screen.findByText(/No ambiguous tick failure requires reconciliation/)).toBeInTheDocument();
  await user.click(await enabledButton("Resume"));
  const dialog = await screen.findByRole("dialog", { name: "Resume paper fund" });
  expect(dialog).toHaveTextContent("clears Halt only");
  expect(dialog).toHaveTextContent("does not run a paper operation");
  await user.click(within(dialog).getByRole("button", { name: "Record resume" }));

  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  expect(mutations(calls)[0].body).toMatchObject({
    request_id: expect.stringMatching(/^[a-f0-9]{32}$/),
  });
  expect(await screen.findByText("Halt cleared. No paper operation ran and no runner was started.")).toBeInTheDocument();
});

it("reuses a manual Resume request ID after a lost response", async () => {
  const user = userEvent.setup();
  const preview = paperReconciliationPreview({
    required: false,
    reason: "no-ambiguous-tick-failure",
    failure_id: null,
    failed_request_id: null,
    operation_id: null,
    expected_head: null,
    current_head: null,
    broker_book_sha256: null,
    capture_id: null,
    capture_digest: null,
    book_matches_ledger: false,
    head_matches_failure: false,
    preview_digest: null,
  });
  let attempts = 0;
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}`]: () => json(paperSnapshot(stoppedRunner, true)),
    [`GET /api/paper/${FUND}/reconciliation`]: () => json({
      name: FUND,
      halted: "operator pause",
      resume_allowed: true,
      preview,
    }),
    [`POST /api/paper/${FUND}/resume`]: () => {
      attempts += 1;
      return attempts === 1
        ? Promise.reject(new TypeError("synthetic Resume response loss"))
        : json({ name: FUND, halted: false, reconciliation_id: null });
    },
  });

  await user.click(await enabledButton("Resume"));
  let dialog = await screen.findByRole("dialog", { name: "Resume paper fund" });
  await user.click(within(dialog).getByRole("button", { name: "Record resume" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  const requestId = mutations(calls)[0].body?.request_id;
  expect(requestId).toMatch(/^[a-f0-9]{32}$/);

  await user.click(await enabledButton("Resume"));
  dialog = await screen.findByRole("dialog", { name: "Resume paper fund" });
  await user.click(within(dialog).getByRole("button", { name: "Record resume" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(2));

  expect(mutations(calls)[1].body).toEqual({ request_id: requestId });
  expect(await screen.findByText("Halt cleared. No paper operation ran and no runner was started.")).toBeInTheDocument();
});

it("keeps resume disabled when local reconciliation is not recoverable", async () => {
  const preview = paperReconciliationPreview({
    recoverable: false,
    reason: "broker-book-mismatch",
    book_matches_ledger: false,
  });
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}`]: () => json(paperSnapshot(stoppedRunner, true)),
    [`GET /api/paper/${FUND}/reconciliation`]: () => json({
      name: FUND,
      halted: "synthetic tick failure",
      resume_allowed: false,
      preview,
    }),
  });

  await screen.findByText("Ambiguous tick failure");
  const recovery = screen.getByTestId("paper-reconciliation");
  expect(recovery).toHaveTextContent("Resume denied. Halt remains active.");
  expect(recovery).toHaveTextContent("broker-book-mismatch");
  expect(screen.getByRole("button", { name: "Review recovery" })).toBeDisabled();
  expect(mutations(calls)).toEqual([]);
});

it("selects an ID-less tick-intent target by digest before confirming recovery", async () => {
  const user = userEvent.setup();
  const firstDigest = "1".repeat(64);
  const secondDigest = "2".repeat(64);
  const aggregatePreview = paperTickIntentPreview({
    recoverable: false,
    reason: "multiple-unresolved-tick-intents",
    intent_session: null,
    intent_digest: null,
    metadata_complete: null,
    preview_digest: "3".repeat(64),
  });
  const selectedPreview = paperTickIntentPreview({
    intent_session: "2024-06-02",
    intent_digest: secondDigest,
    preview_digest: "4".repeat(64),
  });
  const targets = [
    { intent_request_id: null, intent_session: "2024-06-01", intent_digest: firstDigest, recorded_at: null, metadata_complete: false },
    { intent_request_id: null, intent_session: "2024-06-02", intent_digest: secondDigest, recorded_at: null, metadata_complete: false },
  ];
  const reconciliationPreview = paperReconciliationPreview({
    required: false,
    recoverable: false,
    reason: "no-ambiguous-tick-failure",
    failure_id: null,
    failed_request_id: null,
    operation_id: null,
    expected_head: null,
    current_head: null,
    broker_book_sha256: null,
    capture_id: null,
    capture_digest: null,
    book_matches_ledger: false,
    head_matches_failure: false,
    preview_digest: null,
  });
  const recovery = (intentPreview: PaperTickIntentReconciliationPreview) => ({
    name: FUND,
    halted: null,
    resume_allowed: false,
    preview: reconciliationPreview,
    intent_preview: intentPreview,
    intent_targets: targets,
  });
  const calls = renderDesk(stoppedRunner, {
    [`GET /api/paper/${FUND}/reconciliation`]: () => json(recovery(aggregatePreview)),
    [`GET /api/paper/${FUND}/reconciliation?intent_digest=${secondDigest}`]: () => json(recovery(selectedPreview)),
    [`POST /api/paper/${FUND}/reconcile-tick-request`]: () => json({
      name: FUND,
      intent_request_id: null,
      reconciliation_id: "5".repeat(64),
    }),
  });

  const section = await screen.findByTestId("tick-intent-reconciliation");
  expect(section).toHaveTextContent("Multiple unresolved tick intents");
  const target = within(section).getAllByTestId("tick-intent-target")[1];
  await user.click(within(target).getByRole("button", { name: "Review intent target" }));
  await screen.findByText("Recovery preview:");
  await waitFor(() => expect(calls.some((call) => call.path === `/api/paper/${FUND}/reconciliation?intent_digest=${secondDigest}`)).toBe(true));

  await user.click(await enabledButton("Review orphaned tick resolution"));
  const dialog = await screen.findByRole("dialog", { name: "Resolve orphaned paper tick" });
  await user.click(within(dialog).getByRole("button", { name: "Record intent resolution" }));
  await waitFor(() => expect(mutations(calls)).toHaveLength(1));
  expect(mutations(calls)[0].body).toMatchObject({
    intent_request_id: null,
    intent_digest: secondDigest,
    preview_digest: selectedPreview.preview_digest,
  });
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
