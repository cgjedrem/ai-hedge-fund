import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import type { PaperSessionsCollection, PaperSnapshot, RunnerState, SessionSummary } from "@/lib/types";
import { PaperDetailPage } from "@/pages/paper";

const runner: RunnerState = { status: "stopped", available: false, reason: "Read-only synthetic fixture." };
const newer: SessionSummary = {
  session: "2024-06-05T00:01:00",
  hash: "b".repeat(64),
  nav: 101_000.25,
  cash: 90_000.25,
  rebalance: false,
  orders: 0,
  fills: 0,
  decision_as_of: null,
};
const older: SessionSummary = { ...newer, session: "2024-06-05T00:00:00", hash: "a".repeat(64), nav: 100_999.5 };
const previousDay: SessionSummary = { ...newer, session: "2024-06-04T23:59:00", hash: "c".repeat(64) };
const snapshot: PaperSnapshot = {
  name: "grouping-fixture",
  spec: { name: "grouping-fixture", approval_required: false },
  universe: ["AAPL"],
  broker: "paper",
  created: "2024-06-01T00:00:00+00:00",
  cadence: "minute",
  last_session: newer.session,
  last_record_hash: newer.hash,
  nav: newer.nav,
  cash: newer.cash,
  positions: [],
  curve: [],
  sessions: [older, newer],
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
    expected_head: newer.hash,
    recorded_nav: null,
    coverage: { total: 0, quoted: 0, usable: 0, missing: 0, stale: 0, errors: 0 },
    quotes: [],
    reason: "Network disabled.",
  },
  scorecard: null,
  scorecard_error: null,
};

function collection(items: SessionSummary[], overrides: Partial<PaperSessionsCollection> = {}): PaperSessionsCollection {
  return { items, errors: [], next_cursor: null, limit: 50, total: items.length, search: "", ledger: { ok: true, error: null }, ...overrides };
}

function renderPaper(getPage: (query: URLSearchParams) => PaperSessionsCollection | Promise<PaperSessionsCollection>) {
  const requests: { path: string; method: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    requests.push({ path, method: init?.method ?? "GET" });
    let payload: PaperSnapshot | RunnerState | PaperSessionsCollection;
    if (path === "/api/paper/grouping-fixture") payload = snapshot;
    else if (path === "/api/paper/grouping-fixture/runner") payload = runner;
    else if (path.startsWith("/api/paper/grouping-fixture/sessions?")) {
      payload = await getPage(new URL(path, "http://127.0.0.1").searchParams);
    } else throw new Error(`Unexpected API request: ${path}`);
    return new Response(JSON.stringify(payload), { status: 200, headers: { "Content-Type": "application/json" } });
  }));
  render(
    <MemoryRouter initialEntries={["/paper/grouping-fixture"]}>
      <Routes><Route path="/paper/:name" element={<PaperDetailPage />} /></Routes>
    </MemoryRouter>,
  );
  return requests;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

it("preserves page cursors, first-listed recorded summaries and search reset across a split day", async () => {
  const user = userEvent.setup();
  const requests = renderPaper((query) => {
    const search = query.get("search") ?? "";
    if (search === "absent") return collection([], { search });
    if (query.has("cursor")) return collection([previousDay, older], { total: 3, search });
    return collection([newer], { next_cursor: newer.session, total: 3, search });
  });
  await screen.findByRole("heading", { name: "2024-06-05", level: 3 });
  const first = screen.getByRole("region", { name: "2024-06-05 loaded day summary (group 1)" });
  expect(within(first).getByText("1 loaded record")).toBeInTheDocument();
  expect(within(first).getByText("$101,000.25")).toBeInTheDocument();

  await user.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("link", { name: "2024-06-05 · 00:00:00" });
  expect(screen.getByText("Page 2")).toBeInTheDocument();
  expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toContain("2024-06-04");
  const second = screen.getByRole("region", { name: "2024-06-05 loaded day summary (group 1)" });
  expect(within(second).getByText("$100,999.50")).toBeInTheDocument();
  expect(requests.filter((item) => item.path.includes("/sessions?")).at(-1)?.path).toBe(
    "/api/paper/grouping-fixture/sessions?limit=50&cursor=2024-06-05T00%3A01%3A00",
  );

  await user.click(screen.getByRole("button", { name: "Previous" }));
  await screen.findByRole("link", { name: "2024-06-05 · 00:01:00" });
  expect(screen.getByText("Page 1")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Next" }));
  await screen.findByRole("link", { name: "2024-06-05 · 00:00:00" });
  await user.type(screen.getByRole("searchbox", { name: "Search sessions or hashes" }), "a".repeat(12));
  await user.click(screen.getByRole("button", { name: "Search" }));
  await screen.findByRole("link", { name: "2024-06-05 · 00:01:00" });
  expect(screen.getByText("Page 1")).toBeInTheDocument();
  expect(screen.getByText(/matching "aaaaaaaaaaaa"/)).toBeInTheDocument();
  const searched = requests.filter((item) => item.path.includes("/sessions?")).at(-1);
  expect(searched?.path).toBe("/api/paper/grouping-fixture/sessions?limit=50&search=aaaaaaaaaaaa");
  expect(requests.every((request) => request.method === "GET")).toBe(true);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});

it("shows loading rather than an empty ledger before the session page is known", async () => {
  let resolvePage: ((value: PaperSessionsCollection) => void) | undefined;
  const page = new Promise<PaperSessionsCollection>((resolve) => { resolvePage = resolve; });
  renderPaper(() => page);
  await screen.findByRole("heading", { name: "grouping-fixture" });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Loading session history"));
  expect(screen.queryByRole("heading", { name: "No verified sessions" })).not.toBeInTheDocument();
  resolvePage?.(collection([newer]));
  await screen.findByRole("heading", { name: "2024-06-05", level: 3 });
});

it("does not turn an unverifiable session ledger into a successful empty page", async () => {
  renderPaper(() => collection([], {
    errors: [{ id: "ledger", error: "Synthetic ledger verification failed." }],
    ledger: { ok: false, error: "Synthetic ledger verification failed." },
  }));
  await screen.findByText("Synthetic ledger verification failed.");
  expect(screen.queryByRole("heading", { name: "No verified sessions" })).not.toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Unrecognized session date" })).not.toBeInTheDocument();
});
