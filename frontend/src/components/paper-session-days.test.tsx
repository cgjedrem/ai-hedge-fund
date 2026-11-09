import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { PaperSessionDays } from "@/components/paper-session-days";
import type { SessionSummary } from "@/lib/types";

function session(timestamp: string, overrides: Partial<SessionSummary> = {}): SessionSummary {
  return {
    session: timestamp,
    hash: "a".repeat(64),
    nav: 100_000,
    cash: 90_000,
    rebalance: false,
    orders: 0,
    fills: 0,
    decision_as_of: null,
    ...overrides,
  };
}

function renderDays(sessions: SessionSummary[], search = "") {
  return render(
    <MemoryRouter>
      <PaperSessionDays name="grouping-fixture" sessions={sessions} search={search} />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
});

it("groups same-day minute records in the existing newest-first order with recorded snapshot summaries", () => {
  const records = [
    session("2024-06-04T09:30:00", { nav: 100_001.25, cash: 90_001.25 }),
    session("2024-06-04T09:31:00", { hash: "b".repeat(64), nav: 100_002.5, cash: 90_002.5 }),
  ];
  renderDays(records);

  expect(screen.getByRole("heading", { name: "2024-06-04", level: 3 })).toBeInTheDocument();
  const summary = screen.getByRole("region", { name: "2024-06-04 loaded day summary (group 1)" });
  expect(within(summary).getByText("2 loaded records")).toBeInTheDocument();
  expect(within(summary).getByText("NAV (first listed record)")).toBeInTheDocument();
  expect(within(summary).getByText("$100,002.50")).toBeInTheDocument();
  expect(within(summary).getByText("Cash (first listed record)")).toBeInTheDocument();
  expect(within(summary).getByText("$90,002.50")).toBeInTheDocument();
  expect(within(summary).getAllByRole("link").map((link) => link.textContent)).toEqual([
    "2024-06-04 · 09:31:00",
    "2024-06-04 · 09:30:00",
  ]);
  expect(screen.getByText(/only the records loaded on this page/)).toBeInTheDocument();
  expect(summary.textContent).not.toMatch(/PnL|return|change|%/i);
  expect(records.map((record) => record.session)).toEqual([
    "2024-06-04T09:30:00",
    "2024-06-04T09:31:00",
  ]);
});

it("keeps a record with a missing timestamp and shows an explicit error instead of dropping it", () => {
  const missing = session("2024-06-04T09:30:00", { hash: "c".repeat(64), nav: 123_456, cash: 100_001 });
  Reflect.deleteProperty(missing, "session");
  renderDays([session("2024-06-04T09:31:00"), missing]);

  expect(screen.getByRole("alert")).toHaveTextContent("Missing session timestamp.");
  expect(screen.getByRole("heading", { name: "Unrecognized session date", level: 3 })).toBeInTheDocument();
  expect(screen.getByTitle("c".repeat(64))).toBeInTheDocument();
  expect(screen.getByText("$123,456")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(4);
  expect(screen.getAllByRole("link")).toHaveLength(1);
});

it.each([
  ["2024-02-30", "Invalid recorded session date."],
  ["2025-02-29", "Invalid recorded session date."],
  ["1900-02-29", "Invalid recorded session date."],
  ["2024-13-01", "Invalid recorded session date."],
  ["2024-00-01", "Invalid recorded session date."],
  ["2024-01-00", "Invalid recorded session date."],
  ["0000-01-01", "Invalid recorded session date."],
  ["2024-06-04T24:00:00", "Invalid recorded session time."],
  ["2024-06-04T12:60:00", "Invalid recorded session time."],
  ["2024-06-04T12:00:60", "Invalid recorded session time."],
  ["2024-06-04T00:30:00+14:00", "Unrecognized session timestamp format."],
  ["2024-06-04T23:30:00-12:00", "Unrecognized session timestamp format."],
  ["2024-06-04T00:30:00Z", "Unrecognized session timestamp format."],
  ["2024-06-04T12:00:00.001", "Unrecognized session timestamp format."],
  ["2024-06-04t12:00:00", "Unrecognized session timestamp format."],
  [" 2024-06-04", "Unrecognized session timestamp format."],
  ["2024-06-04 ", "Unrecognized session timestamp format."],
  ["2024-06-04\n", "Unrecognized session timestamp format."],
  ["not-a-date", "Unrecognized session timestamp format."],
  ["<img src=x onerror=alert(1)>", "Unrecognized session timestamp format."],
])("retains malformed timestamp %s as inert text with a visible error", (timestamp, message) => {
  renderDays([session(timestamp)]);
  expect(screen.getByRole("alert")).toHaveTextContent(message);
  expect(screen.getByRole("heading", { name: "Unrecognized session date", level: 3 })).toBeInTheDocument();
  expect(screen.getByRole("link")).toHaveTextContent(timestamp.trim());
  expect(screen.getByRole("link")).toHaveAttribute("href", `/paper/grouping-fixture/sessions/${encodeURIComponent(timestamp)}`);
  expect(screen.getByTitle("a".repeat(64))).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.queryByText("NAV (first listed record)")).not.toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
});

it.each([null, "", undefined])("reports absent timestamp %s explicitly without losing its numeric record", (timestamp) => {
  const record = session("2024-06-04");
  Object.defineProperty(record, "session", { value: timestamp });
  renderDays([record]);
  expect(screen.getByRole("alert")).toHaveTextContent("Missing session timestamp.");
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

it("reports a non-string timestamp without crashing or creating a report identity", () => {
  const record = session("2024-06-04");
  Object.defineProperty(record, "session", { value: 123 });
  renderDays([record]);
  expect(screen.getByRole("alert")).toHaveTextContent("Session timestamp is not a string.");
  expect(screen.getByText("123")).toBeInTheDocument();
  expect(screen.getAllByRole("row")).toHaveLength(2);
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

it("announces timestamp errors once while retaining consecutive malformed records and an accessible whitespace identity", () => {
  const missing = session("2024-06-04");
  Reflect.deleteProperty(missing, "session");
  renderDays([
    missing,
    session("2024-02-30", { hash: "b".repeat(64) }),
    session(" ", { hash: "c".repeat(64) }),
  ]);
  expect(screen.getAllByRole("alert")).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent("3 affected records remain visible");
  expect(screen.getAllByRole("row")).toHaveLength(6);
  expect(screen.getByRole("link", { name: 'Recorded session " "' })).toHaveAttribute("href", "/paper/grouping-fixture/sessions/%20");
});

it("retains same-minute records with distinct hashes without merging or changing their order", () => {
  renderDays([
    session("2024-06-04T09:30:00", { hash: "a".repeat(64) }),
    session("2024-06-04T09:30:00", { hash: "b".repeat(64) }),
  ]);
  expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(1);
  expect(screen.getByText("2 loaded records")).toBeInTheDocument();
  expect(screen.getAllByRole("link")).toHaveLength(2);
  const table = screen.getByRole("region", { name: "2024-06-04 session records (group 1)" });
  expect(within(table).getAllByRole("row").slice(1).map((row) => row.querySelector("[title]")?.getAttribute("title"))).toEqual([
    "b".repeat(64),
    "a".repeat(64),
  ]);
});

it("preserves recorded New York dates across midnight regardless of the browser timezone", () => {
  vi.stubEnv("TZ", "Pacific/Honolulu");
  renderDays([
    session("2024-03-09T23:59:00"),
    session("2024-03-10T00:00:00", { hash: "b".repeat(64) }),
  ]);
  expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual([
    "2024-03-10",
    "2024-03-09",
  ]);
  expect(screen.getAllByRole("link").map((link) => link.querySelector("time")?.getAttribute("datetime"))).toEqual([
    "2024-03-10T00:00:00",
    "2024-03-09T23:59:00",
  ]);
  expect(screen.getByText(/New York wall-clock time without timezone conversion/)).toBeInTheDocument();
});

it("groups adjacent daily records and keeps nonadjacent runs of the same day in place", () => {
  renderDays([
    session("2024-06-04T09:30:00"),
    session("2024-06-05", { hash: "b".repeat(64) }),
    session("2024-06-04T09:31:00", { hash: "c".repeat(64) }),
  ]);
  expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual([
    "2024-06-04",
    "2024-06-05",
    "2024-06-04",
  ]);
  expect(screen.getAllByRole("link").map((link) => link.textContent)).toEqual([
    "2024-06-04 · 09:31:00",
    "2024-06-05",
    "2024-06-04 · 09:30:00",
  ]);
  expect(screen.getByRole("region", { name: "2024-06-04 session records (group 1)" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "2024-06-04 session records (group 3)" })).toBeInTheDocument();
});

it.each(["0001-01-01", "2000-02-29", "2024-02-29", "2024-03-10T03:00:00"])("accepts canonical calendar timestamp %s unchanged", (timestamp) => {
  renderDays([session(timestamp)]);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("heading", { name: timestamp.slice(0, 10), level: 3 })).toBeInTheDocument();
  expect(screen.getByRole("link").querySelector("time")).toHaveAttribute("datetime", timestamp);
});

it("keeps day tables and report links keyboard accessible", async () => {
  const user = userEvent.setup();
  renderDays([session("2024-06-04T09:30:00"), session("2024-06-05", { hash: "b".repeat(64) })]);
  const table = screen.getByRole("region", { name: "2024-06-05 session records (group 1)" });
  table.focus();
  await user.keyboard("{ArrowRight}");
  expect(table.scrollLeft).toBe(80);
  await user.tab();
  expect(screen.getByRole("link", { name: "2024-06-05" })).toHaveFocus();
  expect(within(table).getByRole("columnheader", { name: "Session" })).toHaveAttribute("scope", "col");
});

it("distinguishes an empty searched page from an unfiltered page without inventing day summaries", () => {
  const view = renderDays([]);
  expect(screen.getByRole("heading", { name: "No verified sessions" })).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  view.unmount();
  renderDays([], "<img src=x>");
  expect(screen.getByRole("heading", { name: "No matching verified sessions" })).toBeInTheDocument();
  expect(screen.getByText("No session records on this page match the current search.")).toBeInTheDocument();
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});
