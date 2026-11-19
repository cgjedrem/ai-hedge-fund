import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { DeskProvider } from "@/lib/hooks";
import type {
  Capabilities,
  MandateCollection,
  ModelOption,
  OperationPreview,
  OperationPreviewRequest,
  Settings,
} from "@/lib/types";
import { BacktestsPage } from "@/pages/backtests";

const HASH = "a".repeat(64);
const FUND = "synthetic-fund";

const capabilities: Capabilities = {
  mode: "demo",
  read_only: false,
  writes: true,
  network: true,
  local_operator_only: true,
  csrf_authenticates_users: false,
  container_observer: false,
  enrollment_state: "enrolled",
  write_unavailable_reason: null,
  operator_trust_warning: null,
  protected_names: [],
  mutation_token: "synthetic-csrf",
  deferred_actions: {},
};

const mandates: MandateCollection = {
  items: [{
    name: FUND,
    mandate_hash: HASH,
    agent_count: 1,
    strategies: [],
    cadence: "Daily",
    capital: 100_000,
    benchmark: "SPY",
    approval_required: false,
    broker: "paper",
  }],
  errors: [],
};

function settingsFor(model: ModelOption): Settings {
  return {
    model: model.id,
    llm_provider: model.provider,
    endpoint: null,
    timeout_seconds: 60,
    parameters: {},
    version: 1,
    provenance: {},
    settings_error: null,
    models: [model],
    providers: [],
    data_provider: "yfinance",
    data_providers: [{ id: "yfinance", label: "Yahoo Finance" }],
    active_captures: [],
    active_captures_available: true,
    network_enabled: true,
  };
}

function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderBacktests(settings: Settings) {
  const calls: {
    path: string;
    method: string;
    body: Record<string, unknown> | null;
  }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = new URL(String(input), window.location.origin).pathname;
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string"
      ? JSON.parse(init.body) as Record<string, unknown>
      : null;
    calls.push({ path, method, body });

    if (path === "/api/capabilities") return json(capabilities);
    if (path === "/api/mandates") return json(mandates);
    if (path === "/api/settings") return json(settings);
    if (path === "/api/operations" && method === "GET") return json({ items: [] });
    if (path === "/api/operations/preview" && method === "POST") {
      const request = body as unknown as OperationPreviewRequest;
      const preview: OperationPreview = {
        preview_id: "preview-id",
        preview_digest: "b".repeat(64),
        confirmation_token: "synthetic-confirmation",
        action: "backtest",
        subject_id: request.subject_id,
        expected_head: request.expected_head,
        due_set: [],
        capture_id: "c".repeat(32),
        capture_digest: "d".repeat(64),
        expires_at: "2026-11-20T12:00:00Z",
        payload: request.payload,
        capture: {},
        estimate: {
          maximum_model_calls: 1,
          paid_provider: "Ollama",
          maximum_cost_usd: 5,
          maximum_paid_calls: 10,
          maximum_attempt_cost_usd: 3.31072,
          cost_model_id: "ollama-kimi-k3.1-pro-1m-context-v1",
          cost_model_version: "2026-11-01-v2",
          cost_model: "Ollama Kimi K3.1 Pro",
          market_data_provider: "yfinance",
        },
        warnings: [],
      };
      return json(preview);
    }
    return json({ detail: "Unexpected test request." }, 404);
  }));
  render(
    <DeskProvider>
      <MemoryRouter>
        <BacktestsPage />
      </MemoryRouter>
    </DeskProvider>,
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

it("authorizes a paid-cloud Ollama backtest with its verified attempt bound", async () => {
  const user = userEvent.setup();
  const calls = renderBacktests(settingsFor({
    id: "kimi-k3.1-pro:cloud",
    label: "Kimi K3.1 Pro Cloud",
    provider: "Ollama",
    capability: "chat",
    cost_class: "paid-cloud",
  }));

  expect(await screen.findByText("Paid provider authorization")).toBeInTheDocument();
  expect(screen.getByText(/Per-attempt minimum: \$3\.310720/)).toBeInTheDocument();
  const attemptBudget = screen.getByLabelText("Worst-case / attempt ($)") as HTMLInputElement;
  expect(attemptBudget.min).toBe("3.31072");
  expect(attemptBudget.step).toBe("0.000001");

  const review = screen.getByRole("button", { name: "Review backtest" });
  expect(review).toBeDisabled();
  await user.type(screen.getByLabelText("Ticker universe"), "AAPL");
  fireEvent.change(attemptBudget, { target: { value: "3.31072" } });
  await user.click(screen.getByRole("checkbox", {
    name: "I deliberately authorize this paid provider for this reviewed backtest.",
  }));
  await waitFor(() => expect(review).toBeEnabled());
  await user.click(review);
  expect(await screen.findByRole("dialog")).toBeInTheDocument();

  const previewCall = calls.find((call) => call.path === "/api/operations/preview");
  expect(previewCall?.body?.action).toBe("backtest");
  expect(previewCall?.body?.payload).toMatchObject({
    provider: "yfinance",
    model: "kimi-k3.1-pro:cloud",
    authorize_paid_provider: true,
    paid_max_calls: 10,
    paid_max_cost_usd: "5.00",
    paid_max_attempt_cost_usd: "3.31072",
  });
});

it("keeps local Ollama backtests outside paid authorization controls", async () => {
  renderBacktests(settingsFor({
    id: "gemma3:4b",
    label: "Gemma 3 4B",
    provider: "Ollama",
    capability: "chat",
    cost_class: "local",
  }));

  expect(await screen.findByLabelText("Ticker universe")).toBeInTheDocument();
  expect(screen.queryByText("Paid provider authorization")).toBeNull();
  expect(screen.queryByLabelText("Worst-case / attempt ($)")).toBeNull();
});

it("keeps paid authorization controls for non-Ollama providers", async () => {
  renderBacktests(settingsFor({
    id: "jev-1.13.0",
    label: "Jev 1.13.0",
    provider: "TypeSafe",
  }));

  expect(await screen.findByText("Paid provider authorization")).toBeInTheDocument();
  expect(screen.getByLabelText("Worst-case / attempt ($)")).toBeInTheDocument();
});
