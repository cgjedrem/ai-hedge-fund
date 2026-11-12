import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { DeskProvider } from "@/lib/hooks";
import { HomePage } from "@/pages/home";
import type { Capabilities, HomeData } from "@/lib/types";

const capabilities: Capabilities = {
  mode: "demo",
  read_only: true,
  writes: false,
  network: false,
  local_operator_only: true,
  csrf_authenticates_users: false,
  container_observer: false,
  enrollment_state: "enrolled",
  write_unavailable_reason: null,
  operator_trust_warning: null,
  protected_names: [],
  mutation_token: null,
  deferred_actions: {},
};

const home = {
  mode: "demo",
  mandate_count: 0,
  paper_count: 2,
  research_count: 0,
  recorded_nav_total: 200_000,
  paper_funds: [
    {
      name: "needs-review",
      universe: ["AAPL"],
      cadence: "Daily",
      broker: "paper",
      nav: 100_000,
      cash: 100_000,
      last_session: "2024-06-07",
      ledger_ok: false,
      recovery_state: "reconciliation_required",
      halted: "awaiting review",
      halt_state: "halted",
      runner: { status: "unknown", available: false, reason: null },
    },
    {
      name: "corrupt-book",
      universe: ["MSFT"],
      cadence: "Daily",
      broker: "paper",
      nav: null,
      cash: null,
      last_session: null,
      ledger_ok: false,
      recovery_state: "corrupt",
      halted: null,
      halt_state: "clear",
      runner: { status: "unknown", available: false, reason: null },
    },
  ],
  errors: [],
} satisfies HomeData;

function renderHome() {
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
    const path = new URL(String(input), window.location.origin).pathname;
    const payload = path === "/api/capabilities" ? capabilities : home;
    return {
      ok: true,
      status: 200,
      headers: new Headers(),
      json: async () => payload,
    } as Response;
  }));
  render(
    <DeskProvider>
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>
    </DeskProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("distinguishes reconciliation-required paper from corrupt ledgers", async () => {
  renderHome();

  expect(await screen.findByText("Reconciliation required")).toBeInTheDocument();
  expect(screen.getByText("Ledger corrupt")).toBeInTheDocument();
});
