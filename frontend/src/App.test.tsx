import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "@/App";
import type {
  Capabilities,
  Catalog,
  HomeData,
  MandateCollection,
  PaperCollection,
  PaperSnapshot,
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
  protected_names: ["watchtower", "watchtower-weekly", "umbrella"],
  mutation_token: null,
  deferred_actions: {
    runner: "Runner ownership is not verified.",
    manual_run: "Manual execution is disabled.",
    delete: "Deletion is not available.",
    redo: "Redo is not available.",
    live_value: "Live quotes are not fetched.",
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
      halted: null,
      runner: { status: "unknown", available: false, reason: "Runner ownership is not verified." },
    },
  ],
  errors: [],
};

const paperDetail: PaperSnapshot = {
  name: "demo-quality",
  spec: { name: "demo-quality" },
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
  ledger: { ok: true, error: null },
  runner: { status: "unknown", available: false, reason: "Runner ownership is not verified; web process controls are disabled." },
  live_value: { status: "unavailable", value: null, as_of: null, provenance: null, reason: "Live quotes are not fetched by the web process." },
  scorecard: null,
  scorecard_error: null,
};

const mandates: MandateCollection = {
  items: [
    {
      name: "demo-quality",
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
  strategies: [{ name: "value", title: "Value", models: ["buffett", "munger"], kind: "systematic", mode: "long_only" }],
  default_model: "provider/model",
};

const settings: Settings = {
  model: "provider/model",
  models: catalog.models,
  providers: [{ provider: "test-provider", requires_key: true, configured: false }],
  data_provider: "yfinance",
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
  override?: (path: string, method: string, body: unknown) => { payload: unknown; status?: number } | null;
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
    const override = options?.override?.(path, method, body);
    if (override) return response(override.payload, override.status);
    if (path === "/api/capabilities") return response(options?.caps ?? capabilities);
    if (path === "/api/home") return response(home);
    if (path === "/api/mandates") return response(mandates);
    if (path === "/api/catalog") return response(catalog);
    if (path === "/api/settings") return response(settings);
    if (path === "/api/paper") return response({ items: home.paper_funds, errors: [] } satisfies PaperCollection);
    if (path === "/api/paper/demo-quality") return response(paperDetail);
    if (path === "/api/paper/demo-quality/scorecard") return response(scorecard);
    if (path === "/api/paper/demo-quality/sessions/2024-06-04") return response(sessionReport);
    if (path === "/api/research") return response({ items: [researchReport], errors: [] });
    if (path === "/api/research/demo-report.json") return response(researchReport);
    if (path === "/api/jobs") return response({ items: [] });
    return response({ detail: "Not found." }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

beforeEach(() => {
  window.history.replaceState({}, "", "/");
  installApi();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("local desk screens", () => {
  it("navigates from overview through ledger, session report, and scorecard", async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Research with a clear view of risk." })).toBeInTheDocument();
    await user.click(await screen.findByRole("link", { name: /demo-quality/ }));
    expect(await screen.findByRole("heading", { name: "demo-quality" })).toBeInTheDocument();
    expect(await screen.findAllByText("$101,000")).toHaveLength(2);
    expect(screen.getAllByText("Runner ownership is not verified; web process controls are disabled.")).toHaveLength(2);

    await user.click(screen.getByRole("link", { name: /2024-06-04/ }));
    expect(await screen.findByRole("heading", { name: "2024-06-04" })).toBeInTheDocument();
    expect(screen.getByText("Executed orders")).toBeInTheDocument();
    expect(screen.getByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(document.querySelector("img")).not.toBeInTheDocument();
    expect(screen.getByText("$10,000")).toBeInTheDocument();

    await user.click(screen.getByRole("link", { name: "Paper fund" }));
    await screen.findByRole("heading", { name: "demo-quality" });
    await user.click(screen.getByRole("link", { name: /Scorecard/ }));
    expect(await screen.findByRole("heading", { name: "demo-quality scorecard" })).toBeInTheDocument();
    expect(screen.getAllByText("$1,000")).toHaveLength(2);
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
    expect(request?.body).toEqual({ provider: "test-provider", value: sentinel });
    expect(request?.headers.get("x-csrf-token")).toBe("settings-token");

    fireEvent.keyDown(document.body, { key: "k", ctrlKey: true });
    expect(await screen.findByPlaceholderText("Search pages…")).toBeInTheDocument();
  });
});
