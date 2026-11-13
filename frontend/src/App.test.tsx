import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import type {
  Capabilities,
  Catalog,
  HomeData,
  MandateCollection,
  Operation,
  OperationPreview,
  PaperOperationPreview,
  PaperCollection,
  PaperSnapshot,
  RunnerState,
  ResearchReport,
  ScoreMetrics,
  SessionReport,
  Settings,
} from "@/lib/types";

const hash = "a".repeat(64);
const sourceHash = "b".repeat(64);

const capabilities: Capabilities = {
  mode: "demo",
  read_only: true,
  writes: false,
  network: false,
  local_operator_only: true,
  csrf_authenticates_users: false,
  container_observer: false,
  enrollment_state: "unenrolled",
  write_unavailable_reason: null,
  operator_trust_warning: null,
  protected_names: ["watchtower", "watchtower-weekly", "umbrella"],
  mutation_token: null,
  deferred_actions: {
    runner: "Runner ownership is not verified.",
    manual_run: "Manual execution is disabled.",
    delete: "Deletion is not available.",
    redo: "Redo is not available.",
    live_value: "Valuation refresh is disabled.",
  },
};

const home: HomeData = {
  mode: "demo",
  mandate_count: 1,
  paper_count: 1,
  research_count: 1,
  recorded_nav_total: 101_000,
  paper_funds: [
    {
      name: "demo-quality",
      universe: ["AAPL", "MSFT"],
      cadence: "daily",
      broker: "paper",
      nav: 101_000,
      cash: 90_000,
      last_session: "2024-06-05",
      ledger_ok: true,
      recovery_state: "ready",
      halted: null,
      halt_state: "clear",
      runner: { status: "unknown", available: false, reason: "Runner ownership is not verified." },
    },
  ],
  errors: [],
};

const paperDetail: PaperSnapshot = {
  name: "demo-quality",
  spec: { name: "demo-quality", approval_required: true },
  universe: ["AAPL", "MSFT"],
  broker: "paper",
  created: "2024-06-01T00:00:00+00:00",
  cadence: "daily",
  last_session: "2024-06-05",
  last_record_hash: sourceHash,
  nav: 101_000,
  cash: 90_000,
  positions: [{ ticker: "AAPL", shares: 100, mark: 110, market_value: 11_000 }],
  curve: [
    { session: "2024-06-03", nav: 100_000, benchmark_nav: 100_000 },
    { session: "2024-06-04", nav: 100_500, benchmark_nav: 101_000 },
    { session: "2024-06-05", nav: 101_000, benchmark_nav: 102_000 },
  ],
  sessions: [
    { session: "2024-06-04", hash, nav: 100_500, cash: 90_000, rebalance: true, orders: 1, fills: 1, decision_as_of: "2024-06-03" },
    { session: "2024-06-05", hash: sourceHash, nav: 101_000, cash: 90_000, rebalance: true, orders: 0, fills: 0, decision_as_of: "2024-06-04" },
  ],
  pending: {
    decision_as_of: "2024-06-05",
    source_record_hash: sourceHash,
    universe: ["AAPL", "MSFT"],
    target_weights: { AAPL: 0.1 },
    final_weights: { AAPL: 0.1 },
    strategies: ["earnings-drift"],
  },
  approval: null,
  next_run: "2024-06-06T13:30:00+00:00",
  halted: null,
  halt_state: "clear",
  recovery_state: "ready",
  ledger: { ok: true, error: null },
  runner: { status: "unknown", available: false, reason: "Runner ownership is not verified; web process controls are disabled." },
  live_value: {
    status: "unavailable",
    value: null,
    partial_estimate: null,
    as_of: null,
    provenance: null,
    expected_head: sourceHash,
    recorded_nav: null,
    coverage: { total: 0, quoted: 0, usable: 0, missing: 0, stale: 0, errors: 0 },
    quotes: [],
    reason: "Network capability is disabled.",
  },
  scorecard: null,
  scorecard_error: null,
};

const mandates: MandateCollection = {
  items: [
    {
      name: "demo-quality",
      mandate_hash: "e".repeat(64),
      agent_count: 2,
      strategies: [{ name: "earnings-drift", title: "Earnings Drift", mode: "long_short", weight: 1 }],
      cadence: "daily",
      capital: 100_000,
      benchmark: "SPY",
      approval_required: true,
      broker: "paper",
    },
  ],
  errors: [],
};

const catalog: Catalog = {
  models: [{ label: "Test provider", id: "provider/model", provider: "test-provider" }],
  strategies: [{
    name: "value",
    title: "Value",
    models: [
      { name: "buffett", weight: 1, params: {} },
      { name: "munger", weight: 1, params: {} },
    ],
    kind: "systematic",
    mode: "long_only",
    blend: { method: "conviction_weighted", gross_target: 1, mode: "long_only" },
  }],
  analysts: [
    { name: "buffett", approach: "long_only" },
    { name: "munger", approach: "long_only" },
    { name: "druckenmiller", approach: "long_short" },
  ],
  default_model: "provider/model",
};

const settings: Settings = {
  model: "provider/model",
  llm_provider: "Test provider",
  endpoint: null,
  timeout_seconds: 60,
  parameters: {},
  version: 3,
  provenance: {
    data_provider: "default",
    llm_provider: "default",
    model: "default",
    endpoint: "default",
    timeout_seconds: "default",
    parameters: "default",
  },
  settings_error: null,
  models: catalog.models,
  providers: [{ provider: "test-provider", requires_key: true, configured: false, version: 0 }],
  data_provider: "yfinance",
  data_providers: [
    { id: "fd", label: "Financial Datasets" },
    { id: "yfinance", label: "Yahoo Finance" },
  ],
  active_captures: [],
  active_captures_available: true,
  network_enabled: false,
};

const sessionReport: SessionReport = {
  session: "2024-06-04",
  fund: "demo-quality",
  hash,
  prev_hash: "c".repeat(64),
  code_version: "test-version",
  mandate_hash: "d".repeat(64),
  nav: 100_500,
  cash: 90_000,
  positions: { AAPL: 100 },
  marks: { AAPL: 105 },
  benchmark: "SPY",
  benchmark_close: 505,
  rebalance: true,
  executed: {
    as_of: "2024-06-03",
    spec: { risk: { max_position_pct: 0.25, max_gross_exposure: 1 } },
    clamps: [],
    risk_scale_factor: null,
    orders: [{ ticker: "AAPL", side: "buy", quantity: 100, price: 100 }],
    fills: [{ ticker: "AAPL", side: "buy", quantity: 100, price: 100 }],
    trading_cost: 5,
    traded_notional: 10_000,
    commission: 0.5,
    slippage: 4.5,
  },
  proposed: {
    as_of: "2024-06-03",
    universe: ["AAPL", "MSFT"],
    target_weights: { AAPL: 0.1 },
    final_weights: { AAPL: 0.1 },
    clamps: [],
    risk: { max_position_pct: 0.25, max_gross_exposure: 1 },
    risk_scale_factor: null,
    strategies: [
      {
        name: "earnings-drift",
        signals: [
          {
            model_name: "pead",
            ticker: "AAPL",
            date: "2024-06-03",
            value: 0.8,
            reasoning: "<img src=x onerror=alert(1)>",
            components: {},
          },
        ],
        convictions: { AAPL: 0.8 },
        weights: { AAPL: 0.1 },
      },
    ],
  },
};

const scorecard: ScoreMetrics = {
  fund: "demo-quality",
  first_session: "2024-06-03",
  last_session: "2024-06-05",
  horizon: "2 sessions",
  fund_pnl: 1_000,
  trading_cost: 5,
  unattributed: 0,
  analysts: [{ name: "pead", n_views: 2, n_directional: 2, n_abstained: 0, hit_rate: 0.5, slugging: 0.2, ic_mean: 0.1, ic_t_stat: 0.3 }],
  strategies: [{ name: "earnings-drift", n_periods: 2, pnl: 1_000, return_pct: 0.01, win_rate: 0.5, share_of_pnl: 1, max_drawdown_pct: 0.02 }],
};

const researchReport: ResearchReport = {
  id: "demo-report.json",
  fund: "demo-quality",
  start: "2024-06-03",
  end: "2024-06-05",
  rebalance: "daily",
  benchmark: "SPY",
  universe: ["AAPL", "MSFT"],
  session_count: 3,
  metrics: {
    total_return_pct: 0.01,
    annualized_return_pct: 0.12,
    sharpe_ratio: 1.2,
    max_drawdown_pct: 0.02,
    benchmark_return_pct: 0.02,
    excess_return_pct: -0.01,
    n_cycles: 2,
    n_orders: 1,
    traded_notional: 10_000,
    trading_cost: 5,
  },
  dates: ["2024-06-03", "2024-06-04", "2024-06-05"],
  nav: [100_000, 100_500, 101_000],
  benchmark_nav: [100_000, 101_000, 102_000],
  sessions: paperDetail.sessions,
};

const fetchRequests: { path: string; method: string; body: unknown; headers: Headers }[] = [];

function response(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}

function installApi(options?: {
  caps?: Capabilities;
  override?: (path: string, method: string, body: unknown) =>
    { payload: unknown; status?: number } | null | Promise<{ payload: unknown; status?: number } | null>;
}): void {
  fetchRequests.length = 0;
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    let body: unknown = null;
    if (typeof init?.body === "string") {
      try {
        body = JSON.parse(init.body);
      } catch {
        body = init.body;
      }
    }
    fetchRequests.push({ path, method, body, headers: new Headers(init?.headers) });
    const override = await options?.override?.(path, method, body);
    if (override) return response(override.payload, override.status);
    if (path === "/api/capabilities") return response(options?.caps ?? capabilities);
    if (path === "/api/home") return response(home);
    if (path === "/api/mandates") return response(mandates);
    if (path === "/api/catalog") return response(catalog);
    if (path === "/api/settings") return response(settings);
    if (path === "/api/paper") return response({ items: home.paper_funds, errors: [] } satisfies PaperCollection);
    if (path === "/api/paper/demo-quality") return response(paperDetail);
    if (path === "/api/paper/demo-quality/scorecard") return response(scorecard);
    if (path.startsWith("/api/paper/demo-quality/sessions?")) {
      const requestUrl = new URL(path, "http://127.0.0.1");
      const cursor = requestUrl.searchParams.get("cursor");
      if (cursor === "demo-session-next") {
        return response({
          items: [],
          errors: [],
          next_cursor: null,
          limit: 50,
          total: paperDetail.sessions.length,
          search: requestUrl.searchParams.get("search") ?? "",
          ledger: { ok: true, error: null },
        });
      }
      return response({
        items: paperDetail.sessions,
        errors: [],
        next_cursor: "demo-session-next",
        limit: 50,
        total: paperDetail.sessions.length,
        search: requestUrl.searchParams.get("search") ?? "",
        ledger: { ok: true, error: null },
      });
    }
    if (path === "/api/paper/demo-quality/sessions/2024-06-04") return response(sessionReport);
    if (path.startsWith("/api/research?")) {
      const requestUrl = new URL(path, "http://127.0.0.1");
      const cursor = requestUrl.searchParams.get("cursor");
      const search = requestUrl.searchParams.get("search") ?? "";
      if (cursor === "demo-next.json") {
        return response({
          items: [],
          errors: [],
          next_cursor: null,
          limit: 50,
          total: 1,
          search,
        });
      }
      return response({
        items: [researchReport],
        errors: [],
        next_cursor: "demo-next.json",
        limit: 50,
        total: 1,
        search,
      });
    }
    if (path === "/api/research/demo-report.json") return response(researchReport);
    if (path === "/api/operations") return response({ items: [] });
    return response({ detail: "Not found." }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => {
  window.localStorage.clear();
  window.sessionStorage.clear();
  window.history.replaceState({}, "", "/");
  installApi();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("local desk screens", () => {
  it("recovers a pending backtest request after reload without another mutation", async () => {
    const requestId = "a".repeat(32);
    const operationId = "b".repeat(32);
    const pendingKey = `aihf.pending-operation.${requestId}`;
    const operation: Operation = {
      id: operationId,
      operation_id: operationId,
      request_id: requestId,
      action: "backtest",
      subject_id: "demo-quality",
      fund: "demo-quality",
      capture_id: "c".repeat(32),
      capture_digest: "d".repeat(64),
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:01Z",
      status: "running",
      progress: 10,
      payload: {},
      result: null,
      provider: null,
      model: null,
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: `/api/operations/${operationId}`,
    };
    window.localStorage.setItem(pendingKey, JSON.stringify({
      requestId, action: operation.action, subjectId: operation.subject_id,
    }));
    installApi({
      override: (path, method) => method === "GET" && (
        path === `/api/operations/by-request/${requestId}` || path === `/api/operations/${operationId}`
      ) ? { payload: operation } : null,
    });
    window.history.replaceState({}, "", "/backtests");
    render(<App />);

    expect(await screen.findByText(operationId)).toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.backtests.selected-operation")).toBe(operationId);
    expect(window.localStorage.getItem(pendingKey)).toBeNull();
    expect(fetchRequests.some((item) => item.path === `/api/operations/by-request/${requestId}`)).toBe(true);
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("retains a missing pending request and warns that forgetting cannot prove its outcome", async () => {
    const requestId = "e".repeat(32);
    const pendingKey = `aihf.pending-operation.${requestId}`;
    window.localStorage.setItem(pendingKey, JSON.stringify({
      requestId, action: "backtest", subjectId: "demo-quality",
    }));
    window.history.replaceState({}, "", "/backtests");
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText(/no operation was found.*outcome.*unknown/i)).toBeInTheDocument();
    expect(window.localStorage.getItem(pendingKey)).not.toBeNull();
    expect(screen.getByText(/forgetting.*does not prove/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /forget pending request/i }));
    expect(window.localStorage.getItem(pendingKey)).toBeNull();
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("observes another tab's pending identity and blocks a new backtest without overwriting it", async () => {
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
    });
    window.history.replaceState({}, "", "/backtests");
    render(<App />);
    const universe = await screen.findByLabelText("Ticker universe");
    await waitFor(() => expect(universe).toBeEnabled());

    const requestId = "f".repeat(32);
    const key = `aihf.pending-operation.${requestId}`;
    const value = JSON.stringify({ requestId, action: "backtest", subjectId: "demo-quality" });
    window.localStorage.setItem(key, value);
    act(() => window.dispatchEvent(new StorageEvent("storage", { key, newValue: value })));
    expect(await screen.findByText(/no operation was found.*outcome.*unknown/i)).toBeInTheDocument();
    expect(universe).toBeDisabled();
    expect(window.localStorage.getItem(key)).toBe(value);
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it.each(["backtest", "paper-tick"] as const)(
    "keeps both %s identities when concurrent requests are recovered",
    async (action) => {
      const operations: Operation[] = ["1", "2"].map((digit, index) => {
        const requestId = digit.repeat(32);
        const operationId = (index === 0 ? "a" : "b").repeat(32);
        return {
          id: operationId, operation_id: operationId, request_id: requestId,
          action, subject_id: "demo-quality", fund: "demo-quality",
          capture_id: "c".repeat(32), capture_digest: "d".repeat(64),
          created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
          status: "completed", progress: 100, payload: {}, result: null,
          provider: null, model: null, report_id: null, error: null,
          cancel_requested: false, status_url: `/api/operations/${operationId}`,
        };
      });
      for (const operation of operations) {
        window.localStorage.setItem(`aihf.pending-operation.${operation.request_id}`, JSON.stringify({
          requestId: operation.request_id, action, subjectId: operation.subject_id,
        }));
      }
      installApi({
        override: (path, method) => {
          const operation = operations.find((item) =>
            path === `/api/operations/by-request/${item.request_id}` || path === `/api/operations/${item.id}`,
          );
          return method === "GET" && operation ? { payload: operation } : null;
        },
      });
      window.history.replaceState({}, "", action === "backtest" ? "/backtests" : "/paper/demo-quality");
      const user = userEvent.setup();
      render(<App />);

      for (const operation of operations) {
        expect(await screen.findByRole("button", { name: `Monitor saved operation ${operation.id}` })).toBeVisible();
        expect(JSON.parse(window.localStorage.getItem(`aihf.operation-identity.${operation.request_id}`) ?? "null"))
          .toMatchObject({ requestId: operation.request_id, operationId: operation.id });
      }
      await user.click(screen.getByRole("button", { name: `Monitor saved operation ${operations[0].id}` }));
      const key = action === "backtest" ? "aihf.backtests.selected-operation" : "aihf.paper.demo-quality.operation";
      expect(window.localStorage.getItem(key)).toBe(operations[0].id);
      expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
    },
  );

  it.each([
    ["backtest", "running", true],
    ["backtest", "unknown", true],
    ["backtest", "mismatch", true],
    ["backtest", "completed", false],
    ["paper-tick", "running", true],
    ["paper-tick", "unknown", true],
    ["paper-tick", "mismatch", true],
    ["paper-tick", "completed", false],
  ] as const)(
    "checks every saved %s monitor before enabling another operation (%s)",
    async (action, firstStatus, blocked) => {
      const operations: Operation[] = ["1", "2"].map((digit, index) => {
        const requestId = digit.repeat(32);
        const operationId = (index === 0 ? "a" : "b").repeat(32);
        return {
          id: operationId, operation_id: operationId, request_id: requestId,
          action, subject_id: "demo-quality", fund: "demo-quality",
          capture_id: "c".repeat(32), capture_digest: "d".repeat(64),
          created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
          status: index === 0 && firstStatus === "running" ? "running" : "completed",
          progress: index === 0 && firstStatus === "running" ? 25 : 100,
          payload: {}, result: null, provider: null, model: null, report_id: null,
          error: null, cancel_requested: false, status_url: `/api/operations/${operationId}`,
        };
      });
      for (const operation of operations) {
        window.localStorage.setItem(`aihf.operation-identity.${operation.request_id}`, JSON.stringify({
          requestId: operation.request_id, action, subjectId: operation.subject_id, operationId: operation.id,
        }));
      }
      const selectionKey = action === "backtest" ? "aihf.backtests.selected-operation" : "aihf.paper.demo-quality.operation";
      window.localStorage.setItem(selectionKey, operations[1].id);
      installApi({
        caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
        override: (path, method) => {
          if (path === "/api/paper/demo-quality/runner" && method === "GET") {
            return { payload: { status: "stopped", available: false, reason: null } };
          }
          const operation = operations.find((item) => path === `/api/operations/${item.id}`);
          if (method !== "GET" || !operation) return null;
          if (operation.id === operations[0].id && firstStatus === "unknown") {
            return { status: 503, payload: { detail: "Status unavailable.", code: "observation-conflict", retry_policy: "retry-read-only" } };
          }
          if (operation.id === operations[0].id && firstStatus === "mismatch") {
            return { payload: { ...operation, request_id: "different-request" } };
          }
          return { payload: operation };
        },
      });
      window.history.replaceState({}, "", action === "backtest" ? "/backtests" : "/paper/demo-quality");
      render(<App />);
      const control = action === "backtest"
        ? await screen.findByLabelText("Ticker universe")
        : await screen.findByRole("button", { name: "Manual one-session tick" });
      await waitFor(() => expect(fetchRequests.some((item) => item.path === `/api/operations/${operations[0].id}`)).toBe(true));
      await waitFor(() => blocked ? expect(control).toBeDisabled() : expect(control).toBeEnabled());
      expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
    },
  );

  it("limits simultaneous saved-operation observations and blocks unobserved identities", async () => {
    const operations: Operation[] = Array.from({ length: 17 }, (_, index) => {
      const requestId = `request-${index}`;
      const operationId = (index + 1).toString(16).padStart(32, "0");
      window.localStorage.setItem(`aihf.operation-identity.${requestId}`, JSON.stringify({
        requestId, action: "backtest", subjectId: "demo-quality", operationId,
      }));
      return {
        id: operationId, operation_id: operationId, request_id: requestId,
        action: "backtest", subject_id: "demo-quality", fund: "demo-quality",
        capture_id: "c".repeat(32), capture_digest: "d".repeat(64),
        created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
        status: "completed", progress: 100, payload: {}, result: null,
        provider: null, model: null, report_id: null, error: null,
        cancel_requested: false, status_url: `/api/operations/${operationId}`,
      };
    });
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
      override: (path, method) => {
        const operation = operations.find((item) => path === `/api/operations/${item.id}`);
        return method === "GET" && operation ? { payload: operation } : null;
      },
    });
    window.history.replaceState({}, "", "/backtests");
    render(<App />);
    const control = await screen.findByLabelText("Ticker universe");
    expect(await screen.findByText(/observation limit reached/i)).toBeVisible();
    await waitFor(() => expect(fetchRequests.filter((item) => /^\/api\/operations\/[a-f0-9]{32}$/.test(item.path))).toHaveLength(16));
    expect(fetchRequests.some((item) => item.path === `/api/operations/${operations[16].id}`)).toBe(false);
    expect(control).toBeDisabled();
  });

  it.each([
    { code: "expired-confirmation", forgotten: true },
    { code: null, forgotten: false },
  ])("clears only a confirmed expired paper admission ($code)", async ({ code, forgotten }) => {
    const preview: PaperOperationPreview = {
      preview_id: "5".repeat(32), preview_digest: "6".repeat(64),
      confirmation_token: "offline-confirmation-token", action: "paper-tick",
      subject_id: "demo-quality", expected_head: sourceHash, due_set: ["2024-06-06"],
      capture_id: "3".repeat(32), capture_digest: "4".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00", payload: { kind: "manual-tick" },
      capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
      estimate: { maximum_model_calls_per_session: 4, maximum_calls: 3, maximum_resources: 4, maximum_cost_usd: 0, market_data_provider: "yfinance" },
      warnings: [],
    };
    let requestId = "";
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
      override: (path, method, body) => {
        if (path === "/api/paper/demo-quality/runner" && method === "GET") {
          return { payload: { status: "stopped", available: false, reason: null } };
        }
        if (path === "/api/paper/demo-quality/tick/preview" && method === "POST") return { payload: preview };
        if (path === "/api/paper/demo-quality/tick" && method === "POST") {
          requestId = (body as { request_id: string }).request_id;
          return { status: 410, payload: { detail: "Confirmation expired.", code, retry_policy: "review-again" } };
        }
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    const review = await screen.findByRole("button", { name: "Manual one-session tick" });
    await waitFor(() => expect(review).toBeEnabled());
    await user.click(review);
    await user.click(await screen.findByRole("button", { name: "Accept one-session tick" }));
    await waitFor(() => expect(requestId).not.toBe(""));
    await waitFor(() => expect(window.localStorage.getItem(`aihf.pending-operation.${requestId}`) === null).toBe(forgotten));
    expect(fetchRequests.filter((item) => item.path === "/api/paper/demo-quality/tick" && item.method === "POST")).toHaveLength(1);
  });

  it("recovers a pending paper request for the matching fund without another mutation", async () => {
    const requestId = "1".repeat(32);
    const operationId = "2".repeat(32);
    const pendingKey = `aihf.pending-operation.${requestId}`;
    const operation: Operation = {
      id: operationId, operation_id: operationId, request_id: requestId,
      action: "paper-tick", subject_id: "demo-quality", fund: "demo-quality",
      capture_id: "3".repeat(32), capture_digest: "4".repeat(64),
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
      status: "running", progress: 25, payload: {}, result: null,
      provider: null, model: null, report_id: null, error: null,
      cancel_requested: false, status_url: `/api/operations/${operationId}`,
    };
    window.localStorage.setItem(pendingKey, JSON.stringify({
      requestId, action: operation.action, subjectId: operation.subject_id,
    }));
    installApi({
      override: (path, method) => method === "GET" && (
        path === `/api/operations/by-request/${requestId}` || path === `/api/operations/${operationId}`
      ) ? { payload: operation } : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    expect(await screen.findByText("Manual tick · running")).toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(operationId);
    expect(window.localStorage.getItem(pendingKey)).toBeNull();
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("retains a lost paper admission and recovers it after reload without resubmitting", async () => {
    const operationId = "9".repeat(32);
    const preview: PaperOperationPreview = {
      preview_id: "5".repeat(32), preview_digest: "6".repeat(64),
      confirmation_token: "offline-confirmation-token", action: "paper-tick",
      subject_id: "demo-quality", expected_head: sourceHash, due_set: ["2024-06-06"],
      capture_id: "3".repeat(32), capture_digest: "4".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00", payload: { kind: "manual-tick" },
      capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
      estimate: { maximum_model_calls_per_session: 4, maximum_calls: 3, maximum_resources: 4, maximum_cost_usd: 0, market_data_provider: "yfinance" },
      warnings: [],
    };
    const operation: Operation = {
      id: operationId, operation_id: operationId, request_id: "",
      action: "paper-tick", subject_id: "demo-quality", fund: "demo-quality",
      capture_id: preview.capture_id, capture_digest: preview.capture_digest,
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
      status: "running", progress: 25, payload: {}, result: null,
      provider: null, model: null, report_id: null, error: null,
      cancel_requested: false, status_url: `/api/operations/${operationId}`,
    };
    let recoverable = false;
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
      override: (path, method, body) => {
        if (path === "/api/paper/demo-quality/runner" && method === "GET") {
          return { payload: { status: "stopped", available: false, reason: null } };
        }
        if (path === "/api/paper/demo-quality/tick/preview" && method === "POST") return { payload: preview, status: 201 };
        if (path === "/api/paper/demo-quality/tick" && method === "POST") {
          operation.request_id = (body as { request_id: string }).request_id;
          expect(window.localStorage.getItem(`aihf.pending-operation.${operation.request_id}`)).not.toBeNull();
          throw new TypeError("synthetic response lost");
        }
        if (path === `/api/operations/by-request/${operation.request_id}` && method === "GET") {
          return recoverable ? { payload: operation } : { status: 404, payload: { detail: "Not found.", code: "not-found" } };
        }
        if (path === `/api/operations/${operationId}` && method === "GET") return { payload: operation };
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    const view = render(<App />);
    const review = await screen.findByRole("button", { name: "Manual one-session tick" });
    await waitFor(() => expect(review).toBeEnabled());
    await user.click(review);
    await user.click(await screen.findByRole("button", { name: "Accept one-session tick" }));

    expect(await screen.findByText(/no operation was found.*outcome.*unknown/i)).toBeInTheDocument();
    const pendingKey = `aihf.pending-operation.${operation.request_id}`;
    expect(window.localStorage.getItem(pendingKey)).not.toBeNull();
    expect(JSON.stringify(window.localStorage)).not.toContain(preview.confirmation_token);
    expect(JSON.stringify(window.sessionStorage)).not.toContain(preview.confirmation_token);
    expect(fetchRequests.filter((item) => item.path === "/api/paper/demo-quality/tick" && item.method === "POST")).toHaveLength(1);

    view.unmount();
    recoverable = true;
    render(<App />);
    expect(await screen.findByText("Manual tick · running")).toBeInTheDocument();
    expect(window.localStorage.getItem(pendingKey)).toBeNull();
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(operationId);
    expect(fetchRequests.filter((item) => item.path === "/api/paper/demo-quality/tick" && item.method === "POST")).toHaveLength(1);
  });

  it("does not submit and closes the review if request identity storage fails", async () => {
    const preview: PaperOperationPreview = {
      preview_id: "5".repeat(32), preview_digest: "6".repeat(64),
      confirmation_token: "offline-confirmation-token", action: "paper-tick",
      subject_id: "demo-quality", expected_head: sourceHash, due_set: ["2024-06-06"],
      capture_id: "3".repeat(32), capture_digest: "4".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00", payload: { kind: "manual-tick" },
      capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
      estimate: { maximum_model_calls_per_session: 4, maximum_calls: 3, maximum_resources: 4, maximum_cost_usd: 0, market_data_provider: "yfinance" },
      warnings: [],
    };
    const originalSet = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key, value) {
      if (key.startsWith("aihf.pending-operation.")) throw new DOMException("Storage denied");
      return originalSet.call(this, key, value);
    });
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
      override: (path, method) => {
        if (path === "/api/paper/demo-quality/runner" && method === "GET") return { payload: { status: "stopped", available: false, reason: null } };
        if (path === "/api/paper/demo-quality/tick/preview" && method === "POST") return { payload: preview, status: 201 };
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    const review = await screen.findByRole("button", { name: "Manual one-session tick" });
    await waitFor(() => expect(review).toBeEnabled());
    await user.click(review);
    await user.click(await screen.findByRole("button", { name: "Accept one-session tick" }));

    expect(await screen.findByText(/request identity could not be preserved/i)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry browser storage" })).toBeVisible();
    expect(fetchRequests.filter((item) => item.path === "/api/paper/demo-quality/tick" && item.method === "POST")).toHaveLength(0);
  });

  it("does not move a completed paper admission into a different fund after navigation", async () => {
    const preview: PaperOperationPreview = {
      preview_id: "5".repeat(32), preview_digest: "6".repeat(64),
      confirmation_token: "offline-confirmation-token", action: "paper-tick",
      subject_id: "demo-quality", expected_head: sourceHash, due_set: ["2024-06-06"],
      capture_id: "3".repeat(32), capture_digest: "4".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00", payload: { kind: "manual-tick" },
      capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
      estimate: { maximum_model_calls_per_session: 4, maximum_calls: 3, maximum_resources: 4, maximum_cost_usd: 0, market_data_provider: "yfinance" },
      warnings: [],
    };
    const first: Operation = {
      id: "a".repeat(32), operation_id: "a".repeat(32), request_id: "",
      action: "paper-tick", subject_id: "demo-quality", fund: "demo-quality",
      capture_id: preview.capture_id, capture_digest: preview.capture_digest,
      created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
      status: "running", progress: 10, payload: {}, result: null,
      provider: null, model: null, report_id: null, error: null,
      cancel_requested: false, status_url: `/api/operations/${"a".repeat(32)}`,
    };
    const second: Operation = {
      ...first, id: "b".repeat(32), operation_id: "b".repeat(32), request_id: "second-request",
      subject_id: "second-fund", fund: "second-fund", progress: 25,
    };
    let resolveAccept: ((value: { payload: unknown; status: number }) => void) | undefined;
    window.localStorage.setItem("aihf.paper.second-fund.operation", second.id);
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, network: true, enrollment_state: "enrolled", mutation_token: "synthetic-csrf" },
      override: (path, method, body) => {
        if (path === "/api/paper/demo-quality/runner" && method === "GET") return { payload: { status: "stopped", available: false, reason: null } };
        if (path === "/api/paper/second-fund/runner" && method === "GET") return { payload: { status: "stopped", available: false, reason: null } };
        if (path === "/api/paper/second-fund" && method === "GET") return { payload: { ...paperDetail, name: "second-fund" } };
        if (path.startsWith("/api/paper/second-fund/sessions?") && method === "GET") return { payload: { items: [], errors: [], next_cursor: null, limit: 50, total: 0, search: "", ledger: { ok: true, error: null } } };
        if (path === "/api/paper/demo-quality/tick/preview" && method === "POST") return { payload: preview, status: 201 };
        if (path === "/api/paper/demo-quality/tick" && method === "POST") {
          first.request_id = (body as { request_id: string }).request_id;
          return new Promise((resolve) => { resolveAccept = resolve; });
        }
        if (path === `/api/operations/${first.id}` && method === "GET") return { payload: first };
        if (path === `/api/operations/${second.id}` && method === "GET") return { payload: second };
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    const review = await screen.findByRole("button", { name: "Manual one-session tick" });
    await waitFor(() => expect(review).toBeEnabled());
    await user.click(review);
    await user.click(await screen.findByRole("button", { name: "Accept one-session tick" }));
    await waitFor(() => expect(resolveAccept).toBeDefined());

    act(() => {
      window.history.pushState({}, "", "/paper/second-fund");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(await screen.findByRole("heading", { name: "second-fund" })).toBeInTheDocument();
    expect(await screen.findByText("Manual tick · running")).toBeInTheDocument();
    await act(async () => { resolveAccept!({ payload: first, status: 202 }); });

    expect(screen.getByText("Manual tick · running")).toBeInTheDocument();
    expect(screen.queryByText(/reviewed one-session paper tick accepted/i)).not.toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(first.id);
    expect(window.localStorage.getItem("aihf.paper.second-fund.operation")).toBe(second.id);
    expect(fetchRequests.some((item) => item.path === `/api/operations/${first.id}` && item.method === "GET")).toBe(false);
  });

  it("navigates from overview through ledger, session report, and scorecard", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Research with a clear view of risk." })).toBeInTheDocument();
    await user.click(await screen.findByRole("link", { name: /demo-quality/ }));
    expect(await screen.findByRole("heading", { name: "demo-quality" })).toBeInTheDocument();
    expect(await screen.findAllByText("$101,000")).toHaveLength(2);
    expect(screen.getAllByText("Runner ownership is not verified; web process controls are disabled.")).toHaveLength(1);

    await user.click(screen.getByRole("link", { name: /2024-06-04/ }));
    expect(await screen.findByRole("heading", { name: "2024-06-04" })).toBeInTheDocument();
    expect(screen.getByText("Executed orders")).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByText("$10,000.00")).toBeInTheDocument();
    expect(screen.getByText("$0.50")).toBeInTheDocument();
    expect(screen.getByText("$4.50")).toBeInTheDocument();
    expect(screen.getByText("$5.00")).toBeInTheDocument();
    expect(sessionReport.executed?.commission! + sessionReport.executed?.slippage!).toBe(sessionReport.executed?.trading_cost);

    await user.click(screen.getByRole("link", { name: "Paper fund" }));
    await screen.findByRole("heading", { name: "demo-quality" });
    await user.click(screen.getByRole("link", { name: /Scorecard/ }));
    expect(await screen.findByRole("heading", { name: "demo-quality scorecard" })).toBeInTheDocument();
    expect(screen.getAllByText("$1,000")).toHaveLength(2);
    expect(await screen.findByText("$5.00")).toBeInTheDocument();
  });

  it("shows enrolled-root write denial instead of a green recorded book state", async () => {
    installApi({
      caps: {
        ...capabilities,
        mode: "live",
        enrollment_state: "enrolled",
        write_unavailable_reason: "write-capability-disabled",
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "demo-quality" })).toBeInTheDocument();
    expect(screen.getByText(/Root enrollment:/)).toHaveTextContent("enrolled");
    expect(screen.getAllByRole("status").some((status) => status.textContent?.includes("write-capability-disabled"))).toBe(true);
    expect(screen.getByText("Writes unavailable")).toBeInTheDocument();
  });

  it("shows unreadable halt state in list and detail and disables paper actions", async () => {
    const unreadableSummary = { ...home.paper_funds[0], halt_state: "unreadable" as const };
    const unreadableDetail = { ...paperDetail, halt_state: "unreadable" as const };
    installApi({
      override: (path, method) => {
        if (method !== "GET") return null;
        if (path === "/api/paper") return { payload: { items: [unreadableSummary], errors: [] } };
        if (path === "/api/paper/demo-quality") return { payload: unreadableDetail };
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper");
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText("Halt state unknown")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: /demo-quality/ }));
    expect(await screen.findByRole("heading", { name: "demo-quality" })).toBeInTheDocument();
    expect(screen.getAllByText("Halt state unknown").length).toBeGreaterThan(0);
    expect(screen.getByText("Halt state cannot be verified. Verdicts are disabled.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Halt" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Resume" })).toBeDisabled();
  });

  it.each([true, false])("does not describe unavailable paper state as awaiting a verdict (pending=%s)", async (hasPending) => {
    const unavailableDetail = {
      ...paperDetail,
      pending: hasPending ? paperDetail.pending : null,
      ledger: { ok: false, error: "Paper work is in progress or requires reconciliation." },
    };
    installApi({
      caps: {
        ...capabilities,
        mode: "live",
        writes: true,
        read_only: false,
        network: true,
        enrollment_state: "enrolled",
        mutation_token: "paper-only-token",
      },
      override: (path, method) =>
        path === "/api/paper/demo-quality" && method === "GET" ? { payload: unavailableDetail } : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    expect(await screen.findByText("Paper state unavailable.")).toBeInTheDocument();
    expect(screen.getByText("Paper work is in progress or requires reconciliation.")).toBeInTheDocument();
    expect(screen.getByText("Decision unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Awaiting verdict")).not.toBeInTheDocument();
    if (hasPending) {
      expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    }
  });

  it("keeps every web mutation disabled for a SIM deployment", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      network: true,
      mutation_token: "paper-only-token",
    };
    const simDetail = { ...paperDetail, broker: "saxo" };
    const activeRunner: RunnerState = {
      ...paperDetail.runner,
      status: "running",
      available: true,
      reason: null,
    };
    installApi({
      caps: writeCaps,
      override: (path, method) => {
        if (method !== "GET") return null;
        if (path === "/api/paper/demo-quality") return { payload: simDetail };
        if (path === "/api/paper/demo-quality/runner") return { payload: activeRunner };
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    expect(await screen.findByRole("heading", { name: "demo-quality" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Halt" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Resume" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Stop runner" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Manual one-session tick" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Refresh estimate" })).toBeDisabled();
    expect(fetchRequests.filter((request) => request.method === "POST")).toHaveLength(0);
  });

  it("fetches valuation only after an explicit refresh and keeps recorded NAV separate", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      network: true,
      mutation_token: "valuation-token",
    };
    const estimate = {
      status: "estimated",
      value: "100500.125",
      partial_estimate: null,
      as_of: "2026-10-29T12:00:00Z",
      provenance: "yfinance",
      expected_head: sourceHash,
      recorded_nav: "101000",
      request_id: "a".repeat(32),
      deployment: "demo-quality",
      coverage: { total: 1, quoted: 1, usable: 1, missing: 0, stale: 0, errors: 0 },
      quotes: [{
        ticker: "AAPL",
        shares: "100",
        price: "105.00125",
        quote_time: "2026-10-29T11:59:55Z",
        observation_age_seconds: 5,
        status: "quoted",
        freshness: "unknown",
        reason: "Observation time is not an exchange print time; freshness is unverified.",
      }],
      reason: "Complete symbol coverage; provider print freshness is unverified.",
    };
    installApi({
      caps: writeCaps,
      override: (path, method) =>
        path === "/api/paper/demo-quality/valuation" && method === "POST"
          ? { payload: estimate }
          : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "demo-quality" });

    expect(fetchRequests.some((item) => item.path.endsWith("/valuation"))).toBe(false);
    const refresh = screen.getByRole("button", { name: "Refresh estimate" });
    expect(refresh).toBeEnabled();
    await user.click(refresh);

    expect(await screen.findByText("Exact estimate · 100500.125")).toBeInTheDocument();
    const recordedNote = screen.getByText(/Quote time is provider observation time/);
    expect(recordedNote).toHaveTextContent(/Recorded NAV \$101,000 remains unchanged/);
    expect(recordedNote).toHaveTextContent(/exchange print freshness is unverified/);
    const request = fetchRequests.find((item) => item.path === "/api/paper/demo-quality/valuation" && item.method === "POST");
    expect(request?.body).toEqual({ expected_head: sourceHash });
    expect(request?.headers.get("x-csrf-token")).toBe("valuation-token");
  });

  it("keeps valuation refresh unavailable when network capability is off", async () => {
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    await screen.findByRole("heading", { name: "demo-quality" });
    expect(screen.queryByRole("button", { name: "Refresh estimate" })).not.toBeInTheDocument();
    expect(fetchRequests.some((item) => item.path.endsWith("/valuation"))).toBe(false);
  });

  it("shows a verified-ledger error without session metrics", async () => {
    installApi({
      override: (path, method) =>
        path === "/api/paper/demo-quality/sessions/2024-06-04" && method === "GET"
          ? { status: 409, payload: { detail: "Ledger verification failed (LedgerError)." } }
          : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality/sessions/2024-06-04");
    render(<App />);

    expect(await screen.findByText(/Ledger verification failed \(LedgerError\)\./)).toBeInTheDocument();
    expect(screen.queryByText("Trading cost", { exact: true })).not.toBeInTheDocument();
    expect(screen.queryByText("$5.00")).not.toBeInTheDocument();
  });

  it("submits the exact displayed approval identity and surfaces a stale conflict", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "launch-token-for-test",
    };
    installApi({
      caps: writeCaps,
      override: (path, method) =>
        path === "/api/paper/demo-quality/approval" && method === "POST"
          ? { status: 409, payload: { detail: "Pending decision changed; reload before submitting a verdict." } }
          : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "demo-quality" });
    await user.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve pending decision" });
    await user.click(within(dialog).getByRole("button", { name: "Approve displayed decision" }));

    expect(await screen.findByText("Pending decision changed; reload before submitting a verdict.")).toBeInTheDocument();
    const request = fetchRequests.find((item) => item.path === "/api/paper/demo-quality/approval" && item.method === "POST");
    expect(request?.body).toEqual({
      request_id: expect.stringMatching(/^[a-f0-9]{32}$/),
      verdict: "approve",
      decision_as_of: "2024-06-05",
      source_record_hash: sourceHash,
    });
    expect(request?.headers.get("x-csrf-token")).toBe("launch-token-for-test");
  });

  it("reports canonical name conflicts when saving a mandate", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "builder-token",
    };
    installApi({
      caps: writeCaps,
      override: (path, method) =>
        path === "/api/mandates" && method === "POST"
          ? { status: 409, payload: { detail: "A mandate with this name already exists." } }
          : null,
    });
    window.history.replaceState({}, "", "/builder");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Value");
    await user.type(screen.getByLabelText("Mandate name"), "taken");
    await user.click(screen.getByRole("button", { name: "Save new mandate" }));

    expect(await screen.findByText("A mandate with this name already exists.")).toBeInTheDocument();
    const request = fetchRequests.find((item) => item.path === "/api/mandates" && item.method === "POST");
    expect(request?.body).toMatchObject({
      spec: {
        schema_version: 2,
        name: "taken",
        strategies: [{ name: "value", models: [{ name: "buffett" }, { name: "munger" }] }],
        rebalance: "weekly",
        benchmark: "SPY",
      },
    });
  });

  it("offers paper-only mandates and saves a paper broker identity", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "builder-token",
    };
    installApi({
      caps: writeCaps,
      override: (path, method, body) =>
        path === "/api/mandates" && method === "POST"
          ? {
              status: 201,
              payload: {
                name: "paper-only",
                strategies: [],
                cadence: "weekly",
                capital: 100_000,
                benchmark: "SPY",
                approval_required: true,
                broker: "paper",
                spec: (body as { spec: Record<string, unknown> }).spec,
              },
            }
          : null,
    });
    window.history.replaceState({}, "", "/builder");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Value");

    expect(screen.queryByRole("combobox", { name: "Broker book" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Mandate name"), "paper-only");
    await user.click(screen.getByRole("button", { name: "Save new mandate" }));
    expect(await screen.findByText("Mandate saved")).toBeInTheDocument();

    const request = fetchRequests.find((item) => item.path === "/api/mandates" && item.method === "POST");
    expect(request?.body).toMatchObject({ spec: { broker: "paper" } });
  });

  it("keeps library rosters fixed and derives custom blend from analyst profiles", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "builder-token",
    };
    installApi({
      caps: writeCaps,
      override: (path, method, body) =>
        path === "/api/mandates" && method === "POST"
          ? {
              status: 201,
              payload: {
                name: "custom-test",
                strategies: [],
                cadence: "weekly",
                capital: 100_000,
                benchmark: "SPY",
                approval_required: true,
                broker: "paper",
                spec: (body as { spec: Record<string, unknown> }).spec,
              },
            }
          : null,
    });
    window.history.replaceState({}, "", "/builder");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByText("Value");

    expect(screen.queryByRole("checkbox", { name: "Custom analyst buffett" })).not.toBeInTheDocument();
    await user.type(screen.getByLabelText("Mandate name"), "custom-test");
    await user.click(screen.getByRole("button", { name: "Add custom sleeve" }));
    await user.click(screen.getByRole("checkbox", { name: "Custom analyst buffett" }));
    expect(screen.getAllByText("long only", { exact: true })).toHaveLength(2);
    await user.click(screen.getByRole("checkbox", { name: "Custom analyst druckenmiller" }));
    expect(screen.getAllByText("long only", { exact: true })).toHaveLength(1);
    expect(screen.getByText("long short")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save new mandate" }));
    expect(await screen.findByText("Mandate saved")).toBeInTheDocument();

    const request = fetchRequests.find((item) => item.path === "/api/mandates" && item.method === "POST");
    const savedSpec = (request?.body as { spec: { strategies: { name: string; models: { name: string; weight: number; params: Record<string, unknown> }[]; blend: { mode: string } }[] } }).spec;
    expect(savedSpec.strategies[0].models).toEqual(catalog.strategies[0].models);
    const custom = savedSpec.strategies.find((strategy) => strategy.name === "custom");
    expect(custom?.models).toEqual([
      { name: "buffett", weight: 1, params: {} },
      { name: "druckenmiller", weight: 1, params: {} },
    ]);
    expect(custom?.blend.mode).toBe("long_short");
  });

  it("creates a complete advanced FundSpec without rebuilding custom fields", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "builder-token",
    };
    installApi({
      caps: writeCaps,
      override: (path, method, body) =>
        path === "/api/mandates" && method === "POST"
          ? {
              status: 201,
              payload: {
                name: "advanced-json",
                mandate_hash: "c".repeat(64),
                strategies: [],
                cadence: "every 2m",
                capital: 250_000,
                benchmark: "IWM",
                approval_required: true,
                broker: "paper",
                spec: (body as { spec: Record<string, unknown> }).spec,
              },
            }
          : null,
    });
    window.history.replaceState({}, "", "/builder?advanced=true");
    const user = userEvent.setup();
    render(<App />);
    const editor = await screen.findByRole("textbox", { name: "Full FundSpec JSON" });
    const submitted = {
      schema_version: 2,
      name: "advanced-json",
      strategies: [{
        name: "custom",
        display_name: "Custom sleeve",
        weight: 2,
        models: [{ name: "druckenmiller", weight: 3.25, params: { news: true, samples: 2, temperature: 0.25 } }],
        blend: { method: "conviction_weighted", gross_target: 0.8, mode: "dollar_neutral" },
      }],
      risk: { max_position_pct: 0.2, max_gross_exposure: 1.2 },
      costs: { spread_bps: 2, commission_per_share: 0.01 },
      min_order_pct_of_equity: 0.003,
      capital: 250_000,
      rebalance: "minute",
      interval: 2,
      window: { start: "09:30", end: "15:59" },
      benchmark: "IWM",
      approval_required: true,
      broker: "paper",
    };
    fireEvent.change(editor, { target: { value: JSON.stringify(submitted, null, 2) } });
    await user.click(screen.getByRole("button", { name: "Create mandate" }));
    await screen.findByText(/Saved revision/);

    const request = fetchRequests.find((item) => item.path === "/api/mandates" && item.method === "POST");
    expect(request?.body).toEqual({ spec: submitted });
    expect(request?.headers.get("x-csrf-token")).toBe("builder-token");
  });

  it("edits a mandate against its loaded revision hash", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "builder-token",
    };
    const sourceSpec = {
      schema_version: 2,
      name: "demo-quality",
      strategies: [{
        name: "earnings-drift",
        models: [{ name: "pead", weight: 1, params: {} }],
        blend: { method: "conviction_weighted", gross_target: 1, mode: "long_short" },
      }],
      risk: { max_position_pct: 0.25, max_gross_exposure: 1 },
      costs: { spread_bps: 4.5, commission_per_share: 0.005 },
      capital: 100_000,
      rebalance: "daily",
      benchmark: "SPY",
      approval_required: true,
    };
    const source = {
      name: "demo-quality",
      mandate_hash: sourceHash,
      agent_count: 1,
      strategies: [{ name: "earnings-drift", title: "Earnings Drift", mode: "long_short", weight: 1 }],
      cadence: "daily",
      capital: 100_000,
      benchmark: "SPY",
      approval_required: true,
      broker: "paper",
      spec: sourceSpec,
    };
    installApi({
      caps: writeCaps,
      override: (path, method, body) => {
        if (path === "/api/mandates/demo-quality" && method === "GET") return { payload: source };
        if (path === "/api/mandates/demo-quality" && method === "PUT") {
          return {
            payload: {
              ...source,
              mandate_hash: "d".repeat(64),
              spec: (body as { spec: Record<string, unknown> }).spec,
            },
          };
        }
        return null;
      },
    });
    window.history.replaceState({}, "", "/builder?edit=demo-quality");
    const user = userEvent.setup();
    render(<App />);
    const editor = await screen.findByRole("textbox", { name: "Full FundSpec JSON" });
    const edited = { ...sourceSpec, min_order_pct_of_equity: 0.0025 };
    fireEvent.change(editor, { target: { value: JSON.stringify(edited, null, 2) } });
    await user.click(screen.getByRole("button", { name: "Save revision" }));
    await screen.findByText(/Saved revision/);

    const request = fetchRequests.find((item) => item.path === "/api/mandates/demo-quality" && item.method === "PUT");
    expect(request?.body).toEqual({ expected_hash: sourceHash, spec: edited });
    expect(request?.headers.get("x-csrf-token")).toBe("builder-token");
  });

  it("clones a mandate with a distinct name and the captured source revision", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "builder-token",
    };
    const source = {
      name: "demo-quality",
      mandate_hash: sourceHash,
      agent_count: 1,
      strategies: [{ name: "earnings-drift", title: "Earnings Drift", mode: "long_short", weight: 1 }],
      cadence: "daily",
      capital: 100_000,
      benchmark: "SPY",
      approval_required: true,
      broker: "paper",
      spec: {
        schema_version: 2,
        name: "demo-quality",
        strategies: [{
          name: "earnings-drift",
          models: [{ name: "pead", weight: 1, params: {} }],
          blend: { method: "conviction_weighted", gross_target: 1, mode: "long_short" },
        }],
        risk: { max_position_pct: 0.25, max_gross_exposure: 1 },
        costs: { spread_bps: 4.5, commission_per_share: 0.005 },
        capital: 100_000,
        rebalance: "daily",
        benchmark: "SPY",
        approval_required: true,
      },
    };
    installApi({
      caps: writeCaps,
      override: (path, method, body) => {
        if (path === "/api/mandates/demo-quality" && method === "GET") return { payload: source };
        if (path === "/api/mandates/demo-quality/clone" && method === "POST") {
          return {
            status: 201,
            payload: {
              ...source,
              name: "demo-quality-copy",
              mandate_hash: "f".repeat(64),
              spec: (body as { spec: Record<string, unknown> }).spec,
            },
          };
        }
        return null;
      },
    });
    window.history.replaceState({}, "", "/builder?clone=demo-quality");
    const user = userEvent.setup();
    render(<App />);
    const editor = await screen.findByRole("textbox", { name: "Full FundSpec JSON" });
    const cloned = JSON.parse((editor as HTMLTextAreaElement).value) as { name: string };
    expect(cloned.name).toBe("demo-quality-copy");
    await user.click(screen.getByRole("button", { name: "Create clone" }));
    await screen.findByText(/Saved revision/);

    const request = fetchRequests.find((item) => item.path === "/api/mandates/demo-quality/clone" && item.method === "POST");
    expect(request?.body).toMatchObject({
      expected_hash: sourceHash,
      spec: { name: "demo-quality-copy" },
    });
    expect(request?.headers.get("x-csrf-token")).toBe("builder-token");
  });

  it("clears credential input, does not render its value, and leaves Ctrl+K inside text input", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "settings-token",
    };
    installApi({
      caps: writeCaps,
      override: (path, method) =>
        path === "/api/settings/credentials" && method === "POST"
          ? { status: 422, payload: { detail: [{ message: "Invalid request." }] } }
          : null,
    });
    window.history.replaceState({}, "", "/settings");
    const user = userEvent.setup();
    render(<App />);
    const input = await screen.findByLabelText("New credential");
    const sentinel = "private-test-sentinel";
    await user.type(input, sentinel);
    fireEvent.keyDown(input, { key: "k", ctrlKey: true });
    expect(screen.queryByPlaceholderText("Search pages…")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save credential" }));

    expect(await screen.findByText("Invalid request.")).toBeInTheDocument();
    expect(input).toHaveValue("");
    expect(document.body).not.toHaveTextContent(sentinel);
    const request = fetchRequests.find((item) => item.path === "/api/settings/credentials" && item.method === "POST");
    expect(request?.body).toEqual({
      provider: "test-provider",
      value: sentinel,
      expected_version: 0,
    });
    expect(request?.headers.get("x-csrf-token")).toBe("settings-token");

    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    expect(await screen.findByPlaceholderText("Search pages…")).toBeInTheDocument();
  });

  it("labels effective runtime settings as root-persisted", async () => {
    window.history.replaceState({}, "", "/settings");
    render(<App />);

    expect(await screen.findByText("Effective values · saved to this root")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save runtime settings for this root" })).toBeDisabled();
  });

  it("persists effective runtime settings with the mutation token", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "runtime-settings-token",
    };
    installApi({ caps: writeCaps });
    window.history.replaceState({}, "", "/settings");
    const user = userEvent.setup();
    render(<App />);

    await screen.findByText("Effective values · saved to this root");
    await user.type(screen.getByLabelText("LLM endpoint override"), "https://api.example/v1");
    await user.click(screen.getByRole("button", { name: "Save runtime settings for this root" }));

    const request = fetchRequests.find((item) => item.path === "/api/settings" && item.method === "PUT");
    expect(request?.body).toEqual({
      data_provider: "yfinance",
      model: "provider/model",
      endpoint: "https://api.example/v1",
      timeout_seconds: 60,
      parameters: {},
      expected_version: 3,
    });
    expect(request?.headers.get("x-csrf-token")).toBe("runtime-settings-token");
    expect(await screen.findByText(/Runtime settings are saved in this root/)).toBeInTheDocument();
  });

  it("edits the stored record instead of persisting environment overrides", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      mutation_token: "runtime-settings-token",
    };
    const overridden: Settings = {
      ...settings,
      model: "provider/override",
      endpoint: null,
      endpoint_redacted: true,
      provenance: { ...settings.provenance, model: "environment", endpoint: "environment" },
      configuration: {
        stored: { available: true, version: 3, present: true },
        effective: { version: 3, startup_version: 3 },
        fields: [],
        overrides: [
          { field: "model", source: "environment", variable: "AIHF_MODEL" },
          { field: "endpoint", source: "environment", variable: "AIHF_ENDPOINT" },
        ],
        restart_required: true,
        restart_reasons: ["override-shadows-stored"],
        stored_values: {
          data_provider: "yfinance",
          llm_provider: "Ollama",
          model: "provider/model",
          endpoint: "http://127.0.0.1:11434",
          timeout_seconds: 60,
          parameters: {},
        },
        active: { available: true, count: 0, stale_count: 0 },
        runners: { available: true, count: 0, stale_count: 0, stale_unverified_count: 0, ownership_unknown_count: 0 },
        credential_captures: [],
        policy: { hot_reload: false, environment_read_at: "startup", process_environment_credentials_used: false, restart_action: "manual" },
      },
    };
    installApi({
      caps: writeCaps,
      override: (path, method) => (path === "/api/settings" && method === "GET" ? { payload: overridden } : null),
    });
    window.history.replaceState({}, "", "/settings");
    const user = userEvent.setup();
    render(<App />);

    const endpoint = await screen.findByLabelText("LLM endpoint override");
    expect(endpoint).toHaveValue("http://127.0.0.1:11434");
    expect(screen.getByText(/process-environment override and is hidden; this field edits the saved value only/)).toBeInTheDocument();
    expect(screen.getByText("Configuration provenance")).toBeInTheDocument();
    await user.clear(screen.getByLabelText("Request timeout (seconds)"));
    await user.type(screen.getByLabelText("Request timeout (seconds)"), "90");
    await user.click(screen.getByRole("button", { name: "Save runtime settings for this root" }));

    const request = fetchRequests.find((item) => item.path === "/api/settings" && item.method === "PUT");
    expect(request?.body).toEqual({
      data_provider: "yfinance",
      model: "provider/model",
      endpoint: "http://127.0.0.1:11434",
      timeout_seconds: 90,
      parameters: {},
      expected_version: 3,
    });
    expect(await screen.findByText(/keep the override until restart without it/)).toBeInTheDocument();
  });

  it("blocks saving when the stored version changed outside this server", async () => {
    const writeCaps: Capabilities = { ...capabilities, mode: "live", writes: true, read_only: false, mutation_token: "t" };
    const ahead: Settings = {
      ...settings,
      configuration: {
        stored: { available: true, version: 5, present: true },
        effective: { version: 3, startup_version: 3 },
        fields: [],
        overrides: [],
        restart_required: true,
        restart_reasons: ["stored-version-changed"],
        stored_values: null,
        active: { available: true, count: 0, stale_count: 0 },
        runners: { available: true, count: 0, stale_count: 0, stale_unverified_count: 0, ownership_unknown_count: 0 },
        credential_captures: [],
        policy: { hot_reload: false, environment_read_at: "startup", process_environment_credentials_used: false, restart_action: "manual" },
      },
    };
    installApi({
      caps: writeCaps,
      override: (path, method) => (path === "/api/settings" && method === "GET" ? { payload: ahead } : null),
    });
    window.history.replaceState({}, "", "/settings");
    render(<App />);

    expect(await screen.findByText(/Saving is blocked to avoid overwriting them; restart the server manually/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save runtime settings for this root" })).toBeDisabled();
    expect(screen.getByText(/saves from this page are rejected as stale/)).toBeInTheDocument();
  });

  it("shows active captures with their frozen settings version", async () => {
    const activeSettings: Settings = {
      ...settings,
      version: 4,
      active_captures: [
        {
          capture_id: "c".repeat(32),
          subject_id: "demo-quality",
          status: "running",
          capture_details_available: true,
          settings_version: 3,
          data_provider: "yfinance",
          llm_provider: "Ollama",
          model: "gemma3:4b",
          endpoint: null,
          restart_needed: true,
        },
      ],
    };
    installApi({
      override: (path, method) =>
        path === "/api/settings" && method === "GET"
          ? { payload: activeSettings }
          : null,
    });
    window.history.replaceState({}, "", "/settings");
    render(<App />);

    expect(await screen.findByText("Active execution snapshots")).toBeInTheDocument();
    expect(screen.getByText("gemma3:4b")).toBeInTheDocument();
    expect(screen.getByText("Settings version")).toBeInTheDocument();
    expect(screen.getByText(/New settings apply to later operations/)).toBeInTheDocument();
  });

  it("keeps a remembered backtest even when it is outside the bounded recent-operations list", async () => {
    const operationId = "9".repeat(32);
    const saved: Operation = {
      operation_id: operationId,
      id: operationId,
      request_id: "remembered-request",
      action: "backtest",
      subject_id: "synthetic-fund",
      fund: "synthetic-fund",
      capture_id: "8".repeat(32),
      capture_digest: "7".repeat(64),
      status: "completed",
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:01Z",
      payload: {},
      result: null,
      progress: 100,
      provider: null,
      model: null,
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: `/api/operations/${operationId}`,
    };
    window.localStorage.setItem("aihf.backtests.selected-operation", operationId);
    installApi({
      override: (path, method) => {
        if (path === "/api/operations" && method === "GET") return { payload: { items: [] } };
        if (path === `/api/operations/${operationId}` && method === "GET") return { payload: saved };
        return null;
      },
    });
    window.history.replaceState({}, "", "/backtests");
    render(<App />);

    expect(await screen.findByText(operationId)).toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.backtests.selected-operation")).toBe(operationId);
    expect(fetchRequests.some((item) => item.path === `/api/operations/${operationId}`)).toBe(true);
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("identifies a non-backtest receipt before offering cancellation", async () => {
    const operationId = "6".repeat(32);
    const operation: Operation = {
      operation_id: operationId,
      id: operationId,
      request_id: "synthetic-paper-tick",
      action: "paper-tick",
      subject_id: "demo-quality",
      fund: "demo-quality",
      capture_id: "7".repeat(32),
      capture_digest: "8".repeat(64),
      status: "running",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:01+00:00",
      payload: {},
      result: null,
      progress: 10,
      provider: null,
      model: null,
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: `/api/operations/${operationId}`,
    };
    window.localStorage.setItem("aihf.backtests.selected-operation", operationId);
    installApi({
      caps: { ...capabilities, writes: true, read_only: false, mutation_token: "synthetic" },
      override: (path, method) => {
        if (path === "/api/operations" && method === "GET") return { payload: { items: [operation] } };
        if (path === `/api/operations/${operationId}` && method === "GET") return { payload: operation };
        return null;
      },
    });
    window.history.replaceState({}, "", "/backtests");
    render(<App />);

    expect(await screen.findByText(operationId)).toBeInTheDocument();
    expect(screen.queryByText(/cancellation is cooperative at valuation boundaries/i)).not.toBeInTheDocument();
    expect(screen.getByText("Action · paper-tick")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Request cancellation" })).toBeEnabled();
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("restores, selects, and persists a durable backtest operation for monitoring and cancellation", async () => {
    const activeOperation: Operation = {
      operation_id: "a".repeat(32),
      request_id: "active-backtest",
      action: "backtest",
      subject_id: "demo-quality",
      capture_id: "c".repeat(32),
      capture_digest: "d".repeat(64),
      status: "running",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:01+00:00",
      payload: {
        fund: "demo-quality",
        universe: ["AAPL"],
        start: "2026-10-01",
        end: "2026-10-30",
        provider: "yfinance",
        model: "provider/model",
        mandate_hash: hash,
      },
      result: null,
      progress: 45,
      id: "a".repeat(32),
      fund: "demo-quality",
      provider: "yfinance",
      model: "provider/model",
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: "/api/operations/" + "a".repeat(32),
    };
    const completedOperation: Operation = {
      ...activeOperation,
      operation_id: "b".repeat(32),
      request_id: "complete-backtest",
      capture_id: "e".repeat(32),
      id: "b".repeat(32),
      fund: "archived-research",
      subject_id: "archived-research",
      status: "completed",
      progress: 100,
      created_at: "2026-10-31T12:00:30+00:00",
      updated_at: "2026-10-31T12:01:00+00:00",
      report_id: "archived-report.json",
      status_url: "/api/operations/" + "b".repeat(32),
    };
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      network: true,
      mutation_token: "operation-test-token",
    };
    let currentActiveOperation = activeOperation;
    window.localStorage.removeItem("aihf.backtests.selected-operation");
    installApi({
      caps: writeCaps,
      override: (path, method) => {
        if (path === "/api/operations" && method === "GET") {
          return { payload: { items: [currentActiveOperation, completedOperation] } };
        }
        if (path === `/api/operations/${activeOperation.id}` && method === "GET") {
          return { payload: currentActiveOperation };
        }
        if (path === `/api/operations/${completedOperation.id}` && method === "GET") {
          return { payload: completedOperation };
        }
        if (path === `/api/operations/${activeOperation.id}/cancel` && method === "POST") {
          currentActiveOperation = {
            ...currentActiveOperation,
            status: "cancel-requested",
            cancel_requested: true,
          };
          return { payload: currentActiveOperation };
        }
        return null;
      },
    });
    window.history.replaceState({}, "", "/backtests");
    const user = userEvent.setup();
    const view = render(<App />);

    expect(await screen.findByText(activeOperation.id)).toBeInTheDocument();
    const cancel = screen.getByRole("button", { name: "Request cancellation" });
    expect(cancel).toBeEnabled();
    act(() => {
      fireEvent.click(cancel);
      fireEvent.click(cancel);
    });
    await screen.findByRole("button", { name: "Cancellation requested…" });
    const cancelRequests = fetchRequests.filter(
      (item) => item.path === `/api/operations/${activeOperation.id}/cancel` && item.method === "POST",
    );
    expect(cancelRequests).toHaveLength(1);
    expect((cancelRequests[0].body as { request_id?: string }).request_id).toMatch(/^[a-f0-9]{32}$/);

    await user.click(screen.getByRole("button", { name: `Monitor operation ${completedOperation.id}` }));
    expect(await screen.findByText(completedOperation.id)).toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.backtests.selected-operation")).toBe(completedOperation.id);

    await user.click(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Research" }));
    expect(await screen.findByRole("heading", { name: "Research reports" })).toBeInTheDocument();
    await user.click(within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", { name: "Backtests" }));
    expect(await screen.findByText(completedOperation.id)).toBeInTheDocument();

    view.unmount();
    render(<App />);
    expect(await screen.findByText(completedOperation.id)).toBeInTheDocument();
  });

  it("searches reports and advances with the server cursor", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(
      within(screen.getByRole("navigation", { name: "Primary navigation" })).getByRole("link", {
        name: "Research",
      }),
    );

    await user.type(await screen.findByRole("searchbox", { name: "Search reports or funds" }), "demo");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("link", { name: "demo-quality" })).toBeInTheDocument();

    const searchRequest = fetchRequests
      .filter((item) => item.path.startsWith("/api/research?"))
      .map((item) => new URL(item.path, "http://127.0.0.1"));
    expect(searchRequest.at(-1)?.searchParams.get("search")).toBe("demo");
    expect(searchRequest.at(-1)?.searchParams.has("cursor")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("No research reports")).toBeInTheDocument();
    await waitFor(() => {
      const latest = fetchRequests
        .filter((item) => item.path.startsWith("/api/research?"))
        .map((item) => new URL(item.path, "http://127.0.0.1"))
        .at(-1);
      expect(latest?.searchParams.get("cursor")).toBe("demo-next.json");
      expect(latest?.searchParams.get("search")).toBe("demo");
    });
    expect(screen.getByText("Page 2")).toBeInTheDocument();
  });

  it("searches paper history and advances with the session cursor", async () => {
    const user = userEvent.setup();
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    await screen.findByRole("heading", { name: "demo-quality" });
    await user.type(await screen.findByRole("searchbox", { name: "Search sessions or hashes" }), "2024");
    await user.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByRole("link", { name: /2024-06-04/ })).toBeInTheDocument();

    const firstPage = fetchRequests
      .filter((item) => item.path.startsWith("/api/paper/demo-quality/sessions?"))
      .map((item) => new URL(item.path, "http://127.0.0.1"));
    expect(firstPage[firstPage.length - 1]?.searchParams.get("search")).toBe("2024");
    expect(firstPage[firstPage.length - 1]?.searchParams.has("cursor")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Page 2")).toBeInTheDocument();
    const latest = fetchRequests
      .filter((item) => item.path.startsWith("/api/paper/demo-quality/sessions?"))
      .map((item) => new URL(item.path, "http://127.0.0.1"));
    expect(latest[latest.length - 1]?.searchParams.get("search")).toBe("2024");
    expect(latest[latest.length - 1]?.searchParams.get("cursor")).toBe("demo-session-next");
  });

  it("requires a fresh server preview before durable acceptance", async () => {
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      network: true,
      mutation_token: "review-test-token",
    };
    const paidSettings: Settings = {
      ...settings,
      model: "gemma3:4b",
      llm_provider: "Ollama",
      models: [{ label: "Gemma 3 4B", id: "gemma3:4b", provider: "Ollama" }],
      data_provider: "fd",
    };
    const payload = {
      fund: "demo-quality",
      universe: ["AAPL"],
      start: "2026-10-01",
      end: "2026-10-30",
      provider: "fd",
      model: "gemma3:4b",
      mandate_hash: mandates.items[0].mandate_hash,
      authorize_paid_provider: true,
      confirm_fd_self_service_pricing: true,
      paid_max_calls: 10,
      paid_max_cost_usd: "5.00",
      paid_max_attempt_cost_usd: "0.25",
    };
    const preview: OperationPreview = {
      preview_id: "c".repeat(32),
      preview_digest: "d".repeat(64),
      confirmation_token: "synthetic-confirmation-token",
      action: "backtest",
      subject_id: "demo-quality",
      expected_head: mandates.items[0].mandate_hash,
      due_set: [],
      capture_id: "e".repeat(32),
      capture_digest: "f".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00",
      payload,
      capture: { model: payload.model },
      estimate: {
        maximum_model_calls: 2,
        paid_provider: "fd",
        maximum_paid_calls: 10,
        maximum_cost_usd: 5,
        maximum_attempt_cost_usd: 0.25,
        cost_model: "Financial Datasets self-service rates",
        market_data_provider: "fd",
      },
      warnings: [],
    };
    const acceptedOperation: Operation = {
      operation_id: "1".repeat(32),
      request_id: "accepted-backtest",
      action: "backtest",
      subject_id: "demo-quality",
      capture_id: preview.capture_id,
      capture_digest: preview.capture_digest,
      status: "accepted",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:00+00:00",
      payload,
      result: null,
      progress: 0,
      id: "1".repeat(32),
      fund: "demo-quality",
      provider: "fd",
      model: "gemma3:4b",
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: "/api/operations/" + "1".repeat(32),
    };
    let previewCount = 0;
    let acceptCount = 0;
    installApi({
      caps: writeCaps,
      override: (path, method, body) => {
        if (path === "/api/settings" && method === "GET") {
          return { payload: paidSettings };
        }
        if (path === "/api/operations/preview" && method === "POST") {
          previewCount += 1;
          expect(body).toMatchObject({
            action: "backtest",
            subject_id: "demo-quality",
            expected_head: mandates.items[0].mandate_hash,
            payload: expect.objectContaining({
              provider: "fd",
              authorize_paid_provider: true,
              confirm_fd_self_service_pricing: true,
            }),
          });
          return { payload: preview, status: 201 };
        }
        if (path === "/api/operations" && method === "POST") {
          acceptCount += 1;
          expect(body).toMatchObject({
            preview_id: preview.preview_id,
            preview_digest: preview.preview_digest,
            confirmation_token: preview.confirmation_token,
            expected_head: preview.expected_head,
          });
          acceptedOperation.request_id = (body as { request_id: string }).request_id;
          expect(JSON.parse(window.localStorage.getItem(`aihf.pending-operation.${acceptedOperation.request_id}`) ?? "null")).toEqual({
            requestId: acceptedOperation.request_id,
            action: "backtest",
            subjectId: "demo-quality",
          });
          return { payload: acceptedOperation, status: 202 };
        }
        if (path === "/api/operations" && method === "GET") {
          return { payload: { items: acceptCount ? [acceptedOperation] : [] } };
        }
        if (path === `/api/operations/${acceptedOperation.id}` && method === "GET") {
          return { payload: acceptedOperation };
        }
        return null;
      },
    });
    window.localStorage.removeItem("aihf.backtests.selected-operation");
    window.history.replaceState({}, "", "/backtests");
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Ticker universe"), "AAPL");
    const reviewButton = screen.getByRole("button", { name: "Review backtest" });
    expect(reviewButton).toBeDisabled();
    await user.click(screen.getByLabelText(/I deliberately authorize this paid provider/));
    expect(reviewButton).toBeDisabled();
    await user.click(screen.getByLabelText(/I confirm this account uses public Financial Datasets self-service pricing/));
    await waitFor(() => expect(reviewButton).toBeEnabled());
    act(() => {
      fireEvent.click(reviewButton);
      fireEvent.click(reviewButton);
    });
    expect(await screen.findByRole("heading", { name: "Confirm reviewed backtest" })).toBeInTheDocument();
    expect(screen.getByText("Self-service; custom Enterprise pricing unsupported")).toBeInTheDocument();
    expect(previewCount).toBe(1);
    expect(acceptCount).toBe(0);

    const accept = screen.getByRole("button", { name: "Accept reviewed operation" });
    act(() => {
      fireEvent.click(accept);
      fireEvent.click(accept);
    });
    expect(await screen.findByText(acceptedOperation.id)).toBeInTheDocument();
    expect(acceptCount).toBe(1);
    expect((fetchRequests.find((item) => item.path === "/api/operations" && item.method === "POST")?.body as { request_id?: string }).request_id).toMatch(/^[a-f0-9]{32}$/);
    expect(window.localStorage.getItem("aihf.backtests.selected-operation")).toBe(acceptedOperation.id);
    expect(window.localStorage.getItem("synthetic-confirmation-token")).toBeNull();
    expect(JSON.stringify(window.localStorage)).not.toContain(preview.confirmation_token);
    expect(JSON.stringify(window.localStorage)).not.toContain(writeCaps.mutation_token);
    expect(JSON.stringify(window.sessionStorage)).not.toContain(preview.confirmation_token);
    expect(JSON.stringify(window.sessionStorage)).not.toContain(writeCaps.mutation_token);
  });

  it("reviews one manual tick, accepts once, and restores progress after reload", async () => {
    const operationId = "2".repeat(32);
    const operation: Operation = {
      operation_id: operationId,
      request_id: "manual-tick-test",
      action: "paper-tick",
      subject_id: "demo-quality",
      capture_id: "3".repeat(32),
      capture_digest: "4".repeat(64),
      status: "running",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:01+00:00",
      payload: { kind: "manual-tick", session: "2024-06-06" },
      result: null,
      progress: 25,
      id: operationId,
      fund: "demo-quality",
      provider: null,
      model: null,
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: `/api/operations/${operationId}`,
    };
    const preview: PaperOperationPreview = {
      preview_id: "5".repeat(32),
      preview_digest: "6".repeat(64),
      confirmation_token: "offline-confirmation-token",
      action: "paper-tick",
      subject_id: "demo-quality",
      expected_head: sourceHash,
      due_set: ["2024-06-06"],
      capture_id: "3".repeat(32),
      capture_digest: "4".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00",
      payload: { kind: "manual-tick", session: "2024-06-06" },
      capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
      estimate: {
        maximum_model_calls_per_session: 4,
        maximum_calls: 3,
        maximum_resources: 4,
        maximum_cost_usd: 0,
        market_data_provider: "yfinance",
      },
      warnings: ["Only free market data and the captured local Ollama model are authorized."],
    };
    const stoppedRunner: RunnerState = {
      status: "stopped",
      available: false,
      reason: "No owned runner is active.",
      started_at: null,
      expires_at: null,
      sessions_completed: 0,
      max_sessions: null,
      last_session: null,
    };
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      network: true,
      enrollment_state: "enrolled",
      mutation_token: "manual-tick-token",
    };
    let acceptCount = 0;
    window.localStorage.removeItem("aihf.paper.demo-quality.operation");
    installApi({
      caps: writeCaps,
      override: (path, method, body) => {
        if (path === "/api/paper/demo-quality/runner" && method === "GET") {
          return { payload: stoppedRunner };
        }
        if (path === "/api/paper/demo-quality/tick/preview" && method === "POST") {
          expect(body).toEqual({ expected_head: sourceHash });
          return { payload: preview, status: 201 };
        }
        if (path === "/api/paper/demo-quality/tick" && method === "POST") {
          acceptCount += 1;
          expect(body).toMatchObject({
            preview_id: preview.preview_id,
            preview_digest: preview.preview_digest,
            confirmation_token: preview.confirmation_token,
            expected_head: sourceHash,
            due_set: ["2024-06-06"],
          });
          operation.request_id = (body as { request_id: string }).request_id;
          expect(JSON.parse(window.localStorage.getItem(`aihf.pending-operation.${operation.request_id}`) ?? "null")).toEqual({
            requestId: operation.request_id,
            action: "paper-tick",
            subjectId: "demo-quality",
          });
          return { payload: operation, status: 202 };
        }
        if (path === `/api/operations/${operationId}` && method === "GET") {
          return { payload: operation };
        }
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    const view = render(<App />);

    await screen.findByRole("heading", { name: "demo-quality" });
    const review = await screen.findByRole("button", { name: "Manual one-session tick" });
    await waitFor(() => expect(review).toBeEnabled());
    await user.click(review);
    expect(await screen.findByRole("heading", { name: "Confirm one-session paper tick" })).toBeInTheDocument();
    expect(acceptCount).toBe(0);

    const accept = screen.getByRole("button", { name: "Accept one-session tick" });
    fireEvent.click(accept);
    fireEvent.click(accept);
    expect(await screen.findByText("Manual tick · running")).toBeInTheDocument();
    expect(acceptCount).toBe(1);
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(operationId);
    const acceptRequest = fetchRequests.find(
      (item) => item.path === "/api/paper/demo-quality/tick" && item.method === "POST",
    );
    expect((acceptRequest?.body as { request_id?: string }).request_id).toMatch(/^[a-f0-9]{32}$/);

    view.unmount();
    const postCount = fetchRequests.filter((item) => item.method === "POST").length;
    render(<App />);
    expect(await screen.findByText("Manual tick · running")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Paper operation progress" })).toHaveAttribute("aria-valuenow", "25");
    expect(fetchRequests.filter((item) => item.method === "POST")).toHaveLength(postCount);
  });

  it("reviews finite runner bounds and confirms cooperative stop without PID fields", async () => {
    const operationId = "7".repeat(32);
    const preview: PaperOperationPreview = {
      preview_id: "8".repeat(32),
      preview_digest: "9".repeat(64),
      confirmation_token: "runner-confirmation-token",
      action: "paper-runner-start",
      subject_id: "demo-quality",
      expected_head: sourceHash,
      due_set: [],
      capture_id: "a".repeat(32),
      capture_digest: "b".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00",
      payload: {
        kind: "runner-start",
        max_sessions: 1,
        max_runtime_minutes: 60,
        max_calls: 63,
        max_resources: 130,
      },
      capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
      estimate: {
        maximum_model_calls_per_session: 4,
        maximum_calls: 63,
        maximum_resources: 130,
        maximum_cost_usd: 0,
        market_data_provider: "yfinance",
      },
      warnings: ["Only free market data and the captured local Ollama model are authorized."],
    };
    const operation: Operation = {
      operation_id: operationId,
      request_id: "runner-start-test",
      action: "paper-runner-start",
      subject_id: "demo-quality",
      capture_id: preview.capture_id,
      capture_digest: preview.capture_digest,
      status: "completed",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:01+00:00",
      payload: preview.payload,
      result: { runner: { status: "running" } },
      progress: 100,
      id: operationId,
      fund: "demo-quality",
      provider: null,
      model: null,
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: `/api/operations/${operationId}`,
    };
    const stoppedRunner: RunnerState = {
      status: "stopped",
      available: false,
      reason: "No owned runner is active.",
      sessions_completed: 0,
      max_sessions: null,
      started_at: null,
      expires_at: null,
      last_session: null,
    };
    let currentRunner = stoppedRunner;
    let startCount = 0;
    let stopCount = 0;
    const writeCaps: Capabilities = {
      ...capabilities,
      mode: "live",
      writes: true,
      read_only: false,
      network: true,
      enrollment_state: "enrolled",
      mutation_token: "runner-control-token",
    };
    window.localStorage.removeItem("aihf.paper.demo-quality.operation");
    installApi({
      caps: writeCaps,
      override: (path, method, body) => {
        if (path === "/api/paper/demo-quality/runner" && method === "GET") {
          return { payload: currentRunner };
        }
        if (path === "/api/paper/demo-quality/runner/preview" && method === "POST") {
          expect(body).toEqual({
            expected_head: sourceHash,
            max_sessions: 1,
            max_runtime_minutes: 60,
          });
          return { payload: preview, status: 201 };
        }
        if (path === "/api/paper/demo-quality/runner" && method === "POST") {
          startCount += 1;
          expect(body).toMatchObject({
            preview_id: preview.preview_id,
            max_sessions: 1,
            max_runtime_minutes: 60,
            due_set: [],
          });
          operation.request_id = (body as { request_id: string }).request_id;
          expect(JSON.parse(window.localStorage.getItem(`aihf.pending-operation.${operation.request_id}`) ?? "null")).toEqual({
            requestId: operation.request_id,
            action: "paper-runner-start",
            subjectId: "demo-quality",
          });
          currentRunner = {
            ...stoppedRunner,
            status: "running",
            available: true,
            reason: null,
            max_sessions: 1,
            expires_at: "2026-10-31T13:00:00+00:00",
          };
          return { payload: operation, status: 202 };
        }
        if (path === `/api/operations/${operationId}` && method === "GET") {
          return { payload: operation };
        }
        if (path === "/api/paper/demo-quality/runner/stop" && method === "POST") {
          stopCount += 1;
          currentRunner = { ...currentRunner, status: "stopping" };
          return { payload: currentRunner };
        }
        return null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);

    const start = await screen.findByRole("button", { name: "Start runner" });
    await waitFor(() => expect(start).toBeEnabled());
    await user.click(start);
    expect(await screen.findByRole("heading", { name: "Confirm finite runner start" })).toBeInTheDocument();
    expect(startCount).toBe(0);
    await user.click(screen.getByRole("button", { name: "Accept finite runner" }));
    await waitFor(() => expect(startCount).toBe(1));
    const stop = await screen.findByRole("button", { name: "Stop runner" });
    await waitFor(() => expect(stop).toBeEnabled());
    await user.click(stop);
    expect(await screen.findByRole("heading", { name: "Stop owned runner for demo-quality" })).toBeInTheDocument();
    expect(stopCount).toBe(0);
    await user.click(screen.getByRole("button", { name: "Request runner stop" }));
    await waitFor(() => expect(stopCount).toBe(1));
    const stopRequest = fetchRequests.find(
      (item) => item.path === "/api/paper/demo-quality/runner/stop" && item.method === "POST",
    );
    expect(stopRequest?.body).toEqual({});
    expect(JSON.stringify(stopRequest?.body)).not.toContain("pid");
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(operationId);
  });
});

describe("error recovery and reconnect", () => {
  const writeCaps: Capabilities = {
    ...capabilities,
    mode: "live",
    writes: true,
    read_only: false,
    mutation_token: "launch-token-for-test",
  };

  afterEach(() => {
    window.localStorage.clear();
  });

  it("offers Review again for a stale verdict and refreshes without resubmitting", async () => {
    installApi({
      caps: writeCaps,
      override: (path, method) =>
        path === "/api/paper/demo-quality/approval" && method === "POST"
          ? {
              status: 409,
              payload: {
                detail: "Pending decision changed; reload before submitting a verdict.",
                code: "stale-preview",
                message: "Pending decision changed; reload before submitting a verdict.",
                refresh_required: true,
                retry_policy: "review-again",
                subject_id: "demo-quality",
                request_id: null,
                current_head: "c".repeat(64),
              },
            }
          : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "demo-quality" });
    await user.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve pending decision" });
    await user.click(within(dialog).getByRole("button", { name: "Approve displayed decision" }));

    const notice = await screen.findByText("Pending decision changed; reload before submitting a verdict.");
    const alert = notice.closest("[role=alert]") as HTMLElement;
    expect(alert).toHaveTextContent(/Nothing was submitted/);
    expect(alert).toHaveTextContent("Ref demo-quality");
    const detailReads = () => fetchRequests.filter((item) => item.path === "/api/paper/demo-quality" && item.method === "GET").length;
    const readsBefore = detailReads();
    await user.click(within(alert).getByRole("button", { name: "Review again" }));

    await waitFor(() => expect(detailReads()).toBeGreaterThan(readsBefore));
    expect(screen.queryByRole("dialog", { name: "Approve pending decision" })).not.toBeInTheDocument();
    expect(fetchRequests.filter((item) => item.path === "/api/paper/demo-quality/approval")).toHaveLength(1);
  });

  it("renews an expired operator session with a read-only reload and never resubmits the mutation", async () => {
    let renewed = false;
    installApi({
      caps: writeCaps,
      override: (path, method) => {
        if (path === "/api/capabilities" && fetchRequests.some((item) => item.path === "/api/paper/demo-quality/halt")) {
          renewed = true;
          return { payload: { ...writeCaps, mutation_token: "renewed-token-for-test" } };
        }
        return path === "/api/paper/demo-quality/halt" && method === "POST"
          ? {
              status: 403,
              payload: {
                detail: "A valid server-owned operator session is required.",
                code: "capability-denied",
                message: "A valid server-owned operator session is required.",
                refresh_required: true,
                retry_policy: "reload",
                subject_id: null,
                request_id: null,
                current_head: null,
              },
            }
          : null;
      },
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "demo-quality" });
    await user.click(screen.getByRole("button", { name: "Halt" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByRole("textbox"), "synthetic stop");
    await user.click(within(dialog).getByRole("button", { name: "Record halt" }));

    expect(await screen.findByText(/Operator session was renewed\. The rejected request was not submitted/)).toBeInTheDocument();
    await waitFor(() => expect(renewed).toBe(true));
    expect(fetchRequests.filter((item) => item.path === "/api/paper/demo-quality/halt")).toHaveLength(1);
    expect(fetchRequests.filter((item) => item.path === "/api/capabilities").every((item) => item.method === "GET")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByText(/Operator session was renewed/)).not.toBeInTheDocument();
  });

  it("shows a lost connection banner and reloads views after an explicit reconnect", async () => {
    installApi();
    const working = globalThis.fetch;
    let offline = false;
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (offline) throw new TypeError("Failed to fetch");
      return working(input, init);
    }));
    window.history.replaceState({}, "", "/paper");
    const user = userEvent.setup();
    offline = true;
    render(<App />);

    const banner = await screen.findByText(/Connection to the local desk was lost/);
    expect((await screen.findAllByText("The local desk server is unreachable.")).length).toBeGreaterThan(0);
    offline = false;
    await user.click(within(banner.closest("[role=alert]") as HTMLElement).getByRole("button", { name: "Reconnect" }));

    await waitFor(() => expect(screen.queryByText(/Connection to the local desk was lost/)).not.toBeInTheDocument());
    expect(await screen.findByRole("link", { name: "demo-quality" })).toBeInTheDocument();
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("lets the operator forget a remembered paper operation the server no longer knows", async () => {
    const staleId = "f".repeat(32);
    window.localStorage.setItem("aihf.paper.demo-quality.operation", staleId);
    installApi({
      caps: writeCaps,
      override: (path) =>
        path === `/api/operations/${staleId}`
          ? {
              status: 404,
              payload: {
                detail: "Operation not found.",
                code: "not-found",
                message: "Operation not found.",
                refresh_required: false,
                retry_policy: "none",
                subject_id: staleId,
                request_id: null,
                current_head: null,
              },
            }
          : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText(/is no longer known to this server/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Forget operation" }));
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBeNull();
    expect(screen.queryByText(/is no longer known to this server/)).not.toBeInTheDocument();
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("does not label a same-fund non-paper receipt as a runner start", async () => {
    const operationId = "d".repeat(32);
    const operation: Operation = {
      operation_id: operationId,
      id: operationId,
      request_id: "synthetic-lifecycle",
      action: "lifecycle-archive",
      subject_id: "demo-quality",
      fund: "demo-quality",
      capture_id: "1".repeat(32),
      capture_digest: "2".repeat(64),
      status: "completed",
      created_at: "2026-10-31T12:00:00+00:00",
      updated_at: "2026-10-31T12:00:01+00:00",
      payload: {},
      result: null,
      progress: 100,
      provider: null,
      model: null,
      report_id: null,
      error: null,
      cancel_requested: false,
      status_url: `/api/operations/${operationId}`,
    };
    window.localStorage.setItem("aihf.paper.demo-quality.operation", operationId);
    installApi({
      caps: writeCaps,
      override: (path) => path === `/api/operations/${operationId}` ? { payload: operation } : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByText(/remembered operation is not a paper tick or runner start/i)).toBeInTheDocument();
    expect(screen.queryByText("Runner start · completed")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(operationId);
    await user.click(screen.getByRole("button", { name: "Forget operation" }));
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBeNull();
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });

  it("keeps a remembered operation when status storage is unavailable instead of offering to forget it", async () => {
    const operationId = "e".repeat(32);
    window.localStorage.setItem("aihf.paper.demo-quality.operation", operationId);
    installApi({
      caps: writeCaps,
      override: (path) =>
        path === `/api/operations/${operationId}`
          ? {
              status: 503,
              payload: {
                detail: "Operation status storage is unavailable; the operation outcome is unknown. Retry the read.",
                code: "observation-conflict",
                message: "Operation status storage is unavailable; the operation outcome is unknown. Retry the read.",
                refresh_required: false,
                retry_policy: "retry-read-only",
                subject_id: operationId,
                request_id: null,
                current_head: null,
              },
            }
          : null,
    });
    window.history.replaceState({}, "", "/paper/demo-quality");
    render(<App />);

    expect(await screen.findByText(/operation outcome is unknown/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Forget operation" })).not.toBeInTheDocument();
    expect(window.localStorage.getItem("aihf.paper.demo-quality.operation")).toBe(operationId);
    expect(fetchRequests.every((item) => item.method === "GET")).toBe(true);
  });
});
