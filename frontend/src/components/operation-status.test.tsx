import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { nothingDueLabel, operationStatusLabel, PaperOperationStatus, runnerStatusLabel } from "@/components/operation-status";
import type { Operation, OperationStatus } from "@/lib/types";

const operationId = "d".repeat(32);

function operation(overrides: Partial<Operation> = {}): Operation {
  return {
    operation_id: operationId,
    id: operationId,
    request_id: "synthetic-request",
    action: "paper-tick",
    subject_id: "synthetic-fund",
    fund: "synthetic-fund",
    capture_id: "b".repeat(32),
    capture_digest: "c".repeat(64),
    status: "running",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:01Z",
    payload: {},
    result: null,
    progress: 40,
    provider: null,
    model: null,
    report_id: null,
    error: null,
    cancel_requested: false,
    status_url: `/api/operations/${operationId}`,
    ...overrides,
  };
}

afterEach(cleanup);

it.each([
  ["starting", "Runner starting"],
  ["running", "Runner running"],
  ["stopping", "Runner stopping"],
  ["stopped", "Runner stopped"],
  ["completed", "Runner completed"],
  ["failed", "Runner error"],
  ["unknown", "Runner unverified"],
])("labels runner state %s as %s", (status, label) => {
  expect(runnerStatusLabel({ status })).toBe(label);
});

it("never presents a missing or unrecognised runner state as verified", () => {
  expect(runnerStatusLabel(null)).toBe("Runner unavailable");
  expect(runnerStatusLabel(undefined)).toBe("Runner unavailable");
  expect(runnerStatusLabel({ status: "adopted" })).toBe("Runner unverified");
  expect(runnerStatusLabel({ status: "constructor" })).toBe("Runner unverified");
  expect(runnerStatusLabel({ status: "__proto__" })).toBe("Runner unverified");
});

it.each([
  ["accepted", "accepted"],
  ["running", "running"],
  ["cancel-requested", "stopping"],
  ["completed", "completed"],
  ["failed", "error"],
  ["interrupted", "interrupted"],
  ["cancelled", "cancelled"],
] as const)("labels operation status %s as %s", (status, label) => {
  expect(operationStatusLabel(status)).toBe(label);
});

it("does not invent a label for an unknown operation status", () => {
  expect(operationStatusLabel("toString" as OperationStatus)).toBe("unverified");
});

it("labels an empty reviewed due-set as nothing due and leaves a real due-set alone", () => {
  expect(nothingDueLabel([])).toMatch(/^Nothing due now/);
  expect(nothingDueLabel(["2024-06-04"])).toBeNull();
});

it("renders the action, label, bounded progress and inert error text", () => {
  render(
    <PaperOperationStatus
      operation={operation({ status: "failed", progress: 140, error: "<img src=x onerror=alert(1)> provider denied" })}
    />,
  );

  expect(screen.getByText("Manual tick · error")).toBeInTheDocument();
  expect(screen.getByText("100%")).toBeInTheDocument();
  expect(screen.getByRole("progressbar", { name: "Paper operation progress" })).toHaveAttribute("aria-valuenow", "100");
  expect(screen.getByText("<img src=x onerror=alert(1)> provider denied")).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  expect(screen.getByText(operationId)).toBeInTheDocument();
});

it("labels a runner start that is being cancelled as stopping", () => {
  render(<PaperOperationStatus operation={operation({ action: "paper-runner-start", status: "cancel-requested", progress: -5 })} />);

  expect(screen.getByText("Runner start · stopping")).toBeInTheDocument();
  expect(screen.getByText("0%")).toBeInTheDocument();
});
