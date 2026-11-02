import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ArchivePanel } from "@/components/archive-panel";

vi.mock("@/lib/hooks", () => ({
  useDesk: () => ({ capabilities: { writes: true, protected_names: [], deferred_actions: {} } }),
  useResource: () => ({
    loading: false,
    error: null,
    refresh: vi.fn(),
    data: { items: [
      { archive_id: "a".repeat(32), kind: "template", identity: "healthy", state: "archived", updated_at: "synthetic" },
      { archive_id: "b".repeat(32), kind: "template", identity: "early-restore", state: "archived", recovery_required: true, recovery_action: "abandon-unprepared-restore", updated_at: "synthetic" },
      { archive_id: "c".repeat(32), kind: "template", identity: "unsupported", state: "archive-unprepared", recovery_required: true, recovery_action: "manual-review", recovery_error: "Preserve both locations for offline review.", updated_at: "synthetic" },
    ] },
  }),
}));

it("keeps independent restore and explicit recovery available beside a manual-review record", () => {
  render(<ArchivePanel kind="template" onChange={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Review restore" })).toBeVisible();
  expect(screen.getByRole("button", { name: "Review recover" })).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent("Preserve both locations for offline review.");
  expect(screen.getAllByRole("button")).toHaveLength(2);
});
