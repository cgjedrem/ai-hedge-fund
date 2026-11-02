import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { LifecycleActions } from "@/components/lifecycle-actions";
import { ApiError, apiPost } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => ({ ...(await importOriginal<typeof import("@/lib/api")>()), apiPost: vi.fn() }));
const refresh = vi.fn();
const reconnect = vi.fn(async () => true);
const desk = { capabilities: { writes: true, protected_names: [], deferred_actions: {} }, reconnect };
vi.mock("@/lib/hooks", () => ({ useDesk: () => desk }));
const preview = {
  preview_id: "a".repeat(32),
  preview_digest: "b".repeat(64),
  confirmation_token: "c".repeat(40),
  expected_head: "d".repeat(64),
  expires_at: "2099-01-01T00:00:00Z",
  payload: { kind: "template", identity: "synthetic", source_path: "mandates/synthetic.yaml", references: ["paper/synthetic"] },
};

beforeEach(() => {
  vi.clearAllMocks();
  desk.capabilities.writes = true;
  vi.mocked(apiPost).mockResolvedValue(preview);
});

it("reviews exact scope and references before single-use archive acceptance", async () => {
  render(<LifecycleActions kind="template" identity="synthetic" onComplete={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Review archive" }));
  expect(apiPost).toHaveBeenCalledWith("/api/lifecycle/preview", { action: "archive", kind: "template", identity: "synthetic" });
  await screen.findByText(/mandates\/synthetic.yaml/);
  expect(screen.getByText(/paper\/synthetic/)).toBeVisible();
  expect(apiPost).toHaveBeenCalledTimes(1);
  vi.mocked(apiPost).mockResolvedValue({ status: "completed" });
  fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  expect(apiPost).toHaveBeenLastCalledWith("/api/lifecycle/accept", expect.objectContaining({
    action: "archive", kind: "template", identity: "synthetic",
    preview_id: preview.preview_id, preview_digest: preview.preview_digest,
    confirmation_token: preview.confirmation_token, expected_head: preview.expected_head,
    request_id: expect.any(String),
  }));
});

it("invalidates stale confirmation and never repeats an uncertain effect automatically", async () => {
  render(<LifecycleActions kind="research" identity="synthetic-2026.json" onComplete={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Review archive" }));
  await screen.findByRole("button", { name: "Confirm archive" });
  vi.mocked(apiPost).mockRejectedValue(new Error("Object changed; review again."));
  fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
  await screen.findByText("Object changed; review again.");
  expect(screen.queryByRole("button", { name: "Confirm archive" })).not.toBeInTheDocument();
  expect(apiPost).toHaveBeenCalledTimes(2);
  expect(refresh).not.toHaveBeenCalled();
});

it("read-only capability disables review without any API mutation", () => {
  desk.capabilities.writes = false;
  render(<LifecycleActions kind="deployment" identity="synthetic" onComplete={refresh} />);
  expect(screen.getByRole("button", { name: "Review archive" })).toBeDisabled();
  expect(apiPost).not.toHaveBeenCalled();
});

it("expired preview cannot be accepted", async () => {
  vi.mocked(apiPost).mockResolvedValue({ ...preview, expires_at: "2000-01-01T00:00:00Z" });
  render(<LifecycleActions kind="template" identity="synthetic" onComplete={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Review archive" }));
  await screen.findByText(/expired/i);
  expect(screen.queryByRole("button", { name: "Confirm archive" })).not.toBeInTheDocument();
  expect(apiPost).toHaveBeenCalledTimes(1);
});

it("stale review offers Review again that re-previews and never resubmits the rejected confirmation", async () => {
  render(<LifecycleActions kind="template" identity="synthetic" onComplete={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Review archive" }));
  await screen.findByRole("button", { name: "Confirm archive" });
  vi.mocked(apiPost).mockRejectedValueOnce(new ApiError("Lifecycle object changed after review.", 409, { code: "stale-preview", retryPolicy: "review-again", subjectId: "synthetic", requestId: "req-1", currentHead: "e".repeat(64) }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Lifecycle object changed after review.");
  expect(alert).toHaveTextContent(/Nothing was submitted/);
  expect(alert).toHaveTextContent("Ref synthetic \u00b7 request req-1");
  fireEvent.click(screen.getByRole("button", { name: "Review again" }));
  await screen.findByRole("button", { name: "Confirm archive" });
  expect(apiPost).toHaveBeenCalledTimes(3);
  expect(vi.mocked(apiPost).mock.calls.map(([path]) => path)).toEqual(["/api/lifecycle/preview", "/api/lifecycle/accept", "/api/lifecycle/preview"]);
  expect(refresh).not.toHaveBeenCalled();
});

it("lost connection during acceptance requires status inspection instead of resubmission", async () => {
  render(<LifecycleActions kind="template" identity="synthetic" onComplete={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Review archive" }));
  await screen.findByRole("button", { name: "Confirm archive" });
  vi.mocked(apiPost).mockRejectedValueOnce(new ApiError("The local desk server could not be reached; the outcome is unknown.", 0, { retryPolicy: "inspect-status" }));
  fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/inspect durable status before resubmitting/i);
  fireEvent.click(screen.getByRole("button", { name: "Reconnect" }));
  expect(reconnect).toHaveBeenCalledOnce();
  expect(apiPost).toHaveBeenCalledTimes(2);
});

it("permanent denials offer no retry action", async () => {
  vi.mocked(apiPost).mockRejectedValueOnce(new ApiError("Protected roots cannot be archived.", 403, { code: "protected-root", retryPolicy: "none" }));
  render(<LifecycleActions kind="template" identity="synthetic" onComplete={refresh} />);
  fireEvent.click(screen.getByRole("button", { name: "Review archive" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent(/protected and cannot be changed/);
  expect(screen.queryByRole("button", { name: /Retry|Review again|Reconnect|Inspect status/ })).not.toBeInTheDocument();
});
