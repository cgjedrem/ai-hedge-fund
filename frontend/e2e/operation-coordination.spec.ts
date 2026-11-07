import { expect, test, type BrowserContext, type Page } from "@playwright/test";

import type { Operation } from "../src/lib/types";

const origin = process.env.AIHF_COORDINATION_ORIGIN ?? "http://127.0.0.1:8876";
const fund = "demo-quality";
const backtestLock = 'aihf.operation-admission.["backtest"]';
const paperLock = 'aihf.operation-admission.["paper","demo-quality"]';
type Action = "backtest" | "paper-tick" | "paper-runner-start";

declare global {
  interface Window {
    releaseReviewLock?: () => void;
  }
}

async function syntheticApi(context: BrowserContext) {
  const capabilities = await (await context.request.get(`${origin}/api/capabilities`)).json();
  const admissions: { page: Page; operation: Operation }[] = [];
  const mutations: string[] = [];
  const denied: string[] = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== origin) {
      denied.push(request.url());
      await route.abort();
      return;
    }
    const path = url.pathname;
    const method = request.method();
    if (method !== "GET") mutations.push(path);
    if (path === "/api/capabilities") {
      await route.fulfill({ json: {
        ...capabilities, mode: "live", writes: true, read_only: false, network: true,
        enrollment_state: "enrolled", write_unavailable_reason: null, mutation_token: "synthetic-browser-token",
      } });
      return;
    }
    if (path === `/api/paper/${fund}/runner` && method === "GET") {
      await route.fulfill({ json: { status: "stopped", available: false, reason: "Synthetic stopped runner." } });
      return;
    }
    if (path === "/api/operations" && method === "GET") {
      await route.fulfill({ json: { items: admissions.map((item) => item.operation) } });
      return;
    }
    if (path.endsWith("/preview") && method === "POST") {
      const body = request.postDataJSON();
      const action: Action = path === "/api/operations/preview" ? "backtest"
        : path.endsWith("/tick/preview") ? "paper-tick" : "paper-runner-start";
      const payload = action === "backtest" ? body.payload : {
        kind: action === "paper-tick" ? "manual-tick" : "runner-start",
        session: "2026-11-02",
        max_sessions: body.max_sessions,
        max_runtime_minutes: body.max_runtime_minutes,
      };
      await route.fulfill({ status: 201, json: {
        preview_id: "b".repeat(32), preview_digest: "c".repeat(64), confirmation_token: "synthetic-preview-token",
        action, subject_id: fund, expected_head: body.expected_head, due_set: ["2026-11-02"],
        capture_id: "d".repeat(32), capture_digest: "e".repeat(64), expires_at: "2099-01-01T00:00:00Z",
        payload, capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
        estimate: {
          maximum_model_calls: 4, maximum_model_calls_per_session: 4, maximum_calls: 8,
          maximum_resources: 8, maximum_cost_usd: 0, market_data_provider: "yfinance",
        },
        warnings: ["Synthetic browser fixture: no worker or provider dispatch."],
      } });
      return;
    }
    if (method === "POST" && (path === "/api/operations" || path === `/api/paper/${fund}/tick` || path === `/api/paper/${fund}/runner`)) {
      const body = request.postDataJSON();
      const action: Action = path === "/api/operations" ? "backtest" : path.endsWith("/tick") ? "paper-tick" : "paper-runner-start";
      const id = "f".repeat(32);
      const operation: Operation = {
        id, operation_id: id, request_id: body.request_id, action, subject_id: fund, fund,
        capture_id: "d".repeat(32), capture_digest: "e".repeat(64), status: "running",
        created_at: "2026-11-02T12:00:00Z", updated_at: "2026-11-02T12:00:00Z",
        payload: {}, result: null, progress: 1, provider: null, model: null, report_id: null,
        error: null, cancel_requested: false, status_url: `/api/operations/${id}`,
      };
      admissions.push({ page: request.frame().page(), operation });
      await route.fulfill({ status: 202, json: operation });
      return;
    }
    if (method === "GET" && path.startsWith("/api/operations/")) {
      const operation = admissions.find((item) => path.endsWith(item.operation.id) || path.endsWith(item.operation.request_id))?.operation;
      await route.fulfill(operation ? { json: operation } : {
        status: 404, json: { code: "not-found", detail: "Synthetic unknown request outcome." },
      });
      return;
    }
    if (method !== "GET") {
      denied.push(path);
      await route.abort();
      return;
    }
    await route.continue();
  });
  return { admissions, mutations, denied };
}

function acceptLabel(action: Action) {
  return action === "backtest" ? "Accept reviewed operation"
    : action === "paper-tick" ? "Accept one-session tick" : "Accept finite runner";
}

async function review(page: Page, action: Action) {
  await page.goto(action === "backtest" ? "/backtests" : `/paper/${fund}`);
  if (action === "backtest") await page.getByLabel("Ticker universe").fill("AAPL");
  const button = page.getByRole("button", { name: action === "backtest" ? "Review backtest"
    : action === "paper-tick" ? "Manual one-session tick" : "Start runner", exact: true });
  await expect(button).toBeEnabled();
  await button.click();
  await expect(page.getByRole("dialog").getByRole("button", { name: acceptLabel(action), exact: true })).toBeEnabled();
}

async function holdSurface(page: Page, name: string) {
  await page.evaluate((lockName) => new Promise<void>((acquired) => {
    void navigator.locks.request(lockName, async () => {
      acquired();
      await new Promise<void>((release) => { window.releaseReviewLock = release; });
    });
  }), name);
}

async function queued(page: Page, name: string) {
  return page.evaluate(async (lockName) => (await navigator.locks.query()).pending?.filter((lock) => lock.name === lockName).length ?? 0, name);
}

for (const [first, second] of [
  ["backtest", "backtest"],
  ["paper-tick", "paper-tick"],
  ["paper-runner-start", "paper-runner-start"],
  ["paper-tick", "paper-runner-start"],
] satisfies [Action, Action][]) {
  test(`native Web Locks admit only one of two tabs: ${first} / ${second}`, async ({ page, context }) => {
    test.setTimeout(90_000);
    const api = await syntheticApi(context);
    const other = await context.newPage();
    const pages = [page, other];
    const actions = [first, second];
    await test.step("review both tabs before either attempts admission", async () => {
      await Promise.all(pages.map((tab, index) => review(tab, actions[index])));
    });
    const name = first === "backtest" ? backtestLock : paperLock;
    await holdSurface(page, name);
    try {
      await Promise.all(pages.map((tab, index) =>
        tab.getByRole("dialog").getByRole("button", { name: acceptLabel(actions[index]), exact: true })
          .evaluate((button) => { if (button instanceof HTMLButtonElement) button.click(); }),
      ));
      await test.step("both native lock requests are queued without sending a mutation", async () => {
        await expect.poll(() => queued(page, name)).toBe(2);
      });
      expect(api.admissions).toHaveLength(0);
    } finally {
      await page.evaluate(() => window.releaseReviewLock?.());
    }
    await expect.poll(() => api.admissions.length).toBe(1);
    const blocked = api.admissions[0].page === page ? other : page;
    await expect(blocked.getByText(/No operation was submitted\./)).toBeVisible();
    console.log(`${first}/${second}: two native lock waiters, exactly one admitted request, other tab blocked.`);
    const mutationCount = api.mutations.length;
    await test.step("reload reads the admitted status without resubmitting", async () => {
      await Promise.all(pages.map(async (tab) => {
        const status = tab.waitForResponse((response) =>
          new URL(response.url()).pathname === `/api/operations/${api.admissions[0].operation.id}`
          && response.request().method() === "GET",
        );
        await tab.reload();
        expect((await status).status()).toBe(200);
      }));
    });
    expect(api.admissions).toHaveLength(1);
    expect(api.mutations).toHaveLength(mutationCount);
    const stored = await page.evaluate(() => [...Object.values(localStorage), ...Object.values(sessionStorage)]);
    expect(stored.join("\n")).not.toMatch(/synthetic-preview-token|synthetic-browser-token/);
    expect(api.denied).toEqual([]);
  });
}

for (const action of ["backtest", "paper-tick", "paper-runner-start"] satisfies Action[]) {
  test(`cancelling a native lock wait saves no identity: ${action}`, async ({ page, context }) => {
    test.setTimeout(90_000);
    const api = await syntheticApi(context);
    await review(page, action);
    const name = action === "backtest" ? backtestLock : paperLock;
    await holdSurface(page, name);
    try {
      await page.getByRole("dialog").getByRole("button", { name: acceptLabel(action), exact: true }).click();
      await expect.poll(() => queued(page, name)).toBe(1);
      await page.getByRole("dialog").getByRole("button", { name: action === "backtest" ? "Review later" : "Cancel", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect.poll(() => queued(page, name)).toBe(0);
    } finally {
      await page.evaluate(() => window.releaseReviewLock?.());
    }
    expect(api.admissions).toHaveLength(0);
    expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith("aihf.pending-operation.")))).toEqual([]);
    const mutations = api.mutations.length;
    const capabilities = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/capabilities");
    await page.reload();
    await capabilities;
    expect(api.admissions).toHaveLength(0);
    expect(api.mutations).toHaveLength(mutations);
    expect(api.denied).toEqual([]);
  });

  test(`a saved monitor written by another tab during the native lock wait blocks ${action}`, async ({ page, context }) => {
    test.setTimeout(90_000);
    const api = await syntheticApi(context);
    const other = await context.newPage();
    await other.goto("/");
    await review(page, action);
    const name = action === "backtest" ? backtestLock : paperLock;
    await holdSurface(page, name);
    try {
      await page.getByRole("dialog").getByRole("button", { name: acceptLabel(action), exact: true }).click();
      await expect.poll(() => queued(page, name)).toBe(1);
      await other.evaluate((savedAction) => {
        localStorage.setItem("aihf.operation-identity.other-tab", JSON.stringify({
          requestId: "other-tab", action: savedAction, subjectId: "demo-quality", operationId: "a".repeat(32),
        }));
      }, action === "backtest" ? "backtest" : action === "paper-tick" ? "paper-runner-start" : "paper-tick");
    } finally {
      await page.evaluate(() => window.releaseReviewLock?.());
    }
    await expect(page.getByText(/No operation was submitted\./)).toBeVisible();
    expect(api.admissions).toHaveLength(0);
    expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith("aihf.pending-operation.")))).toEqual([]);
    expect(await page.evaluate(() => localStorage.getItem("aihf.operation-identity.other-tab"))).not.toBeNull();
    expect(api.denied).toEqual([]);
  });
}

test("a storage exception releases the native lock and permits a fresh reviewed attempt", async ({ page, context }) => {
  test.setTimeout(90_000);
  const api = await syntheticApi(context);
  await review(page, "backtest");
  await page.evaluate(() => {
    const setItem = Storage.prototype.setItem;
    let fail = true;
    Storage.prototype.setItem = function (key, value) {
      if (fail && key.startsWith("aihf.pending-operation.")) {
        fail = false;
        throw new DOMException("Synthetic storage denial");
      }
      setItem.call(this, key, value);
    };
  });
  await page.getByRole("dialog").getByRole("button", { name: acceptLabel("backtest"), exact: true }).click();
  await expect(page.getByText(/No operation was submitted\./)).toBeVisible();
  expect(api.admissions).toHaveLength(0);
  await expect.poll(() => page.evaluate(async (name) => (await navigator.locks.query()).held?.filter((lock) => lock.name === name).length ?? 0, backtestLock)).toBe(0);
  await page.getByRole("button", { name: "Retry browser storage", exact: true }).click();
  await page.getByRole("button", { name: "Review backtest", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: acceptLabel("backtest"), exact: true }).click();
  await expect.poll(() => api.admissions.length).toBe(1);
  expect(api.denied).toEqual([]);
});

test("unsupported browsers fail closed before any reviewed mutation", async ({ page, context }) => {
  const api = await syntheticApi(context);
  await context.addInitScript(() => Object.defineProperty(navigator, "locks", { configurable: true, value: undefined }));
  await page.goto("/backtests");
  await expect(page.getByText(/^Cross-tab operation coordination is unavailable\./)).toBeVisible();
  await expect(page.getByRole("button", { name: "Review backtest", exact: true })).toBeDisabled();
  expect(api.admissions).toHaveLength(0);
  expect(api.mutations).toEqual([]);
  expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => key.startsWith("aihf.pending-operation.")))).toEqual([]);
  expect(api.denied).toEqual([]);
});
