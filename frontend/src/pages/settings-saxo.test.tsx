import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { DeskProvider, useDesk } from "@/lib/hooks";
import { SettingsPage } from "@/pages/settings";

const settings = {
  model: "synthetic-model",
  llm_provider: "Ollama",
  endpoint: null,
  timeout_seconds: 30,
  parameters: {},
  version: 1,
  provenance: {},
  settings_error: null,
  models: [{ id: "synthetic-model", label: "Synthetic model", provider: "Ollama" }],
  providers: [],
  data_provider: "yfinance",
  data_providers: [{ id: "yfinance", label: "Yahoo Finance" }],
  active_captures: [],
  active_captures_available: true,
  network_enabled: true,
};

const capability = {
  enabled: true,
  state: "available",
  generation: 4,
  expires_at: "2026-10-31T12:00:00Z",
  actions: { discover: true, inspect: true, revoke: true },
};

function ReconnectControl() {
  const { reconnect } = useDesk();
  return <button onClick={() => void reconnect()}>Reconnect test session</button>;
}

function renderSettings(intercept?: (path: string) => Promise<Response> | undefined) {
  const requests: { path: string; init?: RequestInit }[] = [];
  let currentCapability = capability;
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    requests.push({ path, init });
    const intercepted = intercept?.(path);
    if (intercepted) return intercepted;
    let body: unknown = {};
    if (path === "/api/capabilities") {
      body = {
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
    } else if (path === "/api/settings") {
      body = settings;
    } else if (path === "/api/saxo/sim/status") {
      body = { environment: "SIM", read_only: true, capability: currentCapability };
    } else if (path === "/api/saxo/sim/accounts") {
      body = {
        environment: "SIM",
        read_only: true,
        generation: 4,
        selection_required: true,
        choices: [{ selection_id: "a".repeat(32), label: "SIM account 1", currency: "USD" }],
      };
    } else if (path === "/api/saxo/sim/inspect") {
      body = {
        environment: "SIM",
        read_only: true,
        generation: 4,
        account: { label: "SIM account 1", currency: "USD", cash_balance: 1250, positions: [] },
        fund_connected: false,
        trading_enabled: false,
      };
    } else if (path.startsWith("/api/credentials/runtime/saxo-demo-token")) {
      currentCapability = {
        ...capability,
        state: "revoked",
        generation: 5,
        actions: { discover: false, inspect: false, revoke: false },
      };
      body = { state: "revoked", generation: 5 };
    }
    return { ok: true, status: 200, headers: new Headers(), json: async () => body } as Response;
  }));
  render(<DeskProvider><ReconnectControl /><SettingsPage /></DeskProvider>);
  return requests;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

it("keeps Saxo outside provider settings and requires consent before account discovery", async () => {
  const user = userEvent.setup();
  const requests = renderSettings();

  expect(await screen.findByText("Saxo SIM account inspection")).toBeTruthy();
  expect(screen.queryByLabelText("New credential")).toBeNull();
  expect(screen.queryByLabelText(/Saxo.*token/i)).toBeNull();
  expect(requests.some((request) => request.path === "/api/saxo/sim/accounts")).toBe(false);

  await screen.findByText("available");
  const card = screen.getByText("Saxo SIM account inspection").closest("section");
  expect(card).not.toBeNull();
  const consent = within(card as HTMLElement).getByRole("checkbox", {
    name: "Authorize one explicit Saxo SIM read-only network action",
  });
  const discover = within(card as HTMLElement).getByRole("button", { name: "Discover SIM accounts" });
  expect(discover).toHaveProperty("disabled", true);
  await user.click(consent);
  await user.click(discover);

  await waitFor(() => expect(requests.some((request) => request.path === "/api/saxo/sim/accounts")).toBe(true));
  const request = requests.find((entry) => entry.path === "/api/saxo/sim/accounts");
  expect(JSON.parse(String(request?.init?.body))).toEqual({ authorize_network: true, expected_generation: 4 });
});

it("requires a fresh consent for the selected account inspection and renders only typed read-only results", async () => {
  const user = userEvent.setup();
  const requests = renderSettings();
  const card = await screen.findByText("Saxo SIM account inspection").then((node) => node.closest("section") as HTMLElement);
  await within(card).findByText("available");
  const consent = within(card).getByRole("checkbox", {
    name: "Authorize one explicit Saxo SIM read-only network action",
  });

  await user.click(consent);
  await user.click(within(card).getByRole("button", { name: "Discover SIM accounts" }));
  const select = await within(card).findByLabelText("Choose one account to inspect");
  await user.selectOptions(select, "a".repeat(32));
  expect(within(card).getByRole("button", { name: "Inspect selected account" })).toHaveProperty("disabled", true);
  await user.click(consent);
  await user.click(within(card).getByRole("button", { name: "Inspect selected account" }));

  expect(await within(card).findByText(/Cash balance: 1250/)).toBeTruthy();
  const request = requests.find((entry) => entry.path === "/api/saxo/sim/inspect");
  expect(JSON.parse(String(request?.init?.body))).toEqual({
    authorize_network: true,
    expected_generation: 4,
    selection_id: "a".repeat(32),
  });
  expect(screen.queryByText(/trading enabled/i)).toBeNull();
  expect(within(card).getByText(/trading disabled/i)).toBeTruthy();
});

it("clears uninspected choices on revoke without persisting browser state", async () => {
  const user = userEvent.setup();
  const requests = renderSettings();
  const card = await screen.findByText("Saxo SIM account inspection").then((node) => node.closest("section") as HTMLElement);
  await within(card).findByText("available");
  await user.click(within(card).getByRole("checkbox", {
    name: "Authorize one explicit Saxo SIM read-only network action",
  }));
  await user.click(within(card).getByRole("button", { name: "Discover SIM accounts" }));
  expect(await within(card).findByLabelText("Choose one account to inspect")).toBeTruthy();

  await user.click(within(card).getByRole("button", { name: "Revoke inspection access" }));

  await within(card).findByText("revoked");
  expect(within(card).queryByLabelText("Choose one account to inspect")).toBeNull();
  expect(requests.some((request) => request.path.startsWith("/api/credentials/runtime/saxo-demo-token?expected_generation=4"))).toBe(true);
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});

it.each([
  ["accounts", "cancel"], ["inspect", "cancel"], ["accounts", "revoke"],
  ["inspect", "revoke"], ["accounts", "restart"], ["inspect", "restart"],
])("does not restore stale %s results after %s", async (action, invalidation) => {
  const user = userEvent.setup();
  let finish!: (value: Response) => void;
  const delayed = new Promise<Response>((resolve) => { finish = resolve; });
  renderSettings((path) => path === `/api/saxo/sim/${action}` ? delayed : undefined);
  const card = await screen.findByText("Saxo SIM account inspection").then((node) => node.closest("section") as HTMLElement);
  await within(card).findByText("available");
  const consent = within(card).getByRole("checkbox", {
    name: "Authorize one explicit Saxo SIM read-only network action",
  });
  await user.click(consent);
  await user.click(within(card).getByRole("button", { name: "Discover SIM accounts" }));
  if (action === "inspect") {
    await user.selectOptions(await within(card).findByLabelText("Choose one account to inspect"), "a".repeat(32));
    await user.click(consent);
    await user.click(within(card).getByRole("button", { name: "Inspect selected account" }));
  }
  if (invalidation === "restart") {
    await user.click(screen.getByRole("button", { name: "Reconnect test session" }));
  } else {
    await user.click(within(card).getByRole("button", {
      name: invalidation === "cancel" ? "Cancel inspection" : "Revoke inspection access",
    }));
  }
  await waitFor(() => expect(within(card).queryByLabelText("Choose one account to inspect")).toBeNull());
  await act(async () => {
    finish({
      ok: true, status: 200, headers: new Headers(),
      json: async () => action === "accounts"
        ? { environment: "SIM", read_only: true, generation: 4, selection_required: true,
            choices: [{ selection_id: "b".repeat(32), label: "Stale account", currency: "USD" }] }
        : { environment: "SIM", read_only: true, generation: 4,
            account: { label: "Stale account", currency: "USD", cash_balance: 9999, positions: [] },
            fund_connected: false, trading_enabled: false },
    } as Response);
  });
  expect(within(card).queryByLabelText("Choose one account to inspect")).toBeNull();
  expect(within(card).queryByText(/9999/)).toBeNull();
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});
