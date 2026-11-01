import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const port = process.env.AIHF_WEB_PORT;
if (port !== "8876") {
  throw new Error("Run browser acceptance through the owned 8876 harness.");
}
const origin = `http://127.0.0.1:${port}`;
const screenshotDir = resolve(
  process.cwd(),
  "../specs/005-web-engine-migration/screenshots",
);
const screenRoutes = [
  { path: "/", heading: "Research with a clear view of risk.", screenshot: "overview" },
  { path: "/mandates", heading: "Mandates", screenshot: "mandates" },
  { path: "/mandates/demo-quality", heading: "demo-quality", screenshot: "mandate-detail" },
  { path: "/builder", heading: "Compose a mandate", screenshot: "builder" },
  { path: "/paper", heading: "Paper funds", screenshot: "paper-list" },
  { path: "/paper/demo-quality", heading: "demo-quality", screenshot: "paper-detail" },
  { path: "/paper/demo-quality/sessions/2024-06-04", heading: "2024-06-04", screenshot: "session-report" },
  { path: "/paper/demo-quality/scorecard", heading: "demo-quality scorecard", screenshot: "scorecard" },
  { path: "/research", heading: "Research reports", screenshot: "research-list" },
  { path: "/backtests", heading: "Backtest operations", screenshot: "backtests" },
  { path: "/settings", heading: "Settings", screenshot: "settings" },
];

test.beforeEach(async ({ page }) => {
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) return route.abort();
    return route.continue();
  });
});

async function assertChartPaths(page: Page): Promise<void> {
  const chart = page.getByTestId("equity-chart");
  await expect(chart).toBeVisible();
  await expect(chart.getByText("Fund NAV", { exact: true })).toBeVisible();
  const paths = await chart.locator(".recharts-line-curve").evaluateAll((elements) =>
    elements.map((element) => element.getAttribute("d") ?? ""),
  );
  expect(paths).toHaveLength(2);
  expect(paths.every((path) => path.length > 5 && /[ML]/.test(path))).toBe(true);
}

async function assertCurrencyMetric(page: Page, label: string): Promise<void> {
  const value = page.getByText(label, { exact: true }).locator("xpath=../p[2]");
  await expect(value).toHaveText(/^\$[0-9,]+\.[0-9]{2}$/);
}

async function assertCustomMode(page: Page, mode: string): Promise<void> {
  const heading = page.getByText("Custom analyst sleeve", { exact: true });
  await expect(heading.locator("xpath=..").getByText(mode, { exact: true })).toBeVisible();
}

async function installSyntheticPaperCapabilities(page: Page): Promise<string> {
  const [capabilitiesResponse, paperResponse] = await Promise.all([
    page.request.get("/api/capabilities"),
    page.request.get("/api/paper/demo-quality"),
  ]);
  expect(capabilitiesResponse.ok()).toBe(true);
  expect(paperResponse.ok()).toBe(true);
  const capabilities = await capabilitiesResponse.json();
  const paper = await paperResponse.json();
  expect(paper.broker).toBe("paper");
  expect(paper.ledger.ok).toBe(true);
  expect(paper.halt_state).toBe("clear");
  const head = paper.last_record_hash as string;
  expect(head).toMatch(/^[a-f0-9]{64}$/);

  await page.route("**/api/capabilities", (route) =>
    route.fulfill({
      json: {
        ...capabilities,
        mode: "live",
        read_only: false,
        writes: true,
        network: true,
        enrollment_state: "enrolled",
        write_unavailable_reason: null,
        protected_names: [],
        mutation_token: "browser-paper-control-token",
      },
    }),
  );
  return head;
}

test("production routes render at desktop and narrow widths without external requests", async ({ page }) => {
  mkdirSync(screenshotDir, { recursive: true });
  const externalRequests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== origin) {
      externalRequests.push(request.url());
    }
  });

  await page.setViewportSize({ width: 1440, height: 1000 });

  for (const route of screenRoutes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
    await expect(page.locator("body")).not.toContainText("Internal server error.");
    if (route.screenshot === "builder") {
      await page.getByRole("button", { name: "Add custom sleeve" }).click();
      await page.getByRole("checkbox", { name: "Custom analyst buffett" }).check();
      await page.getByRole("checkbox", { name: "Custom analyst druckenmiller" }).check();
      await assertCustomMode(page, "long short");
    }
    if (route.screenshot === "paper-detail") await assertChartPaths(page);
    if (route.screenshot === "session-report") {
      await assertCurrencyMetric(page, "Trading cost");
      await assertCurrencyMetric(page, "Traded notional");
      await assertCurrencyMetric(page, "Commission");
      await assertCurrencyMetric(page, "Slippage");
      await expect(page.getByText("$0.50", { exact: true })).toBeVisible();
      await expect(page.getByText("$4.50", { exact: true })).toBeVisible();
      await expect(page.getByText("$5.00", { exact: true })).toBeVisible();
    }
    await page.screenshot({
      path: resolve(screenshotDir, `desktop-${route.screenshot}.png`),
      fullPage: true,
      animations: "disabled",
    });
  }

  await page.goto("/research");
  await expect(page.getByRole("heading", { name: "Research reports" })).toBeVisible();
  await page.getByRole("link", { name: /demo-quality/ }).click();
  await expect(page.getByRole("heading", { name: "demo-quality backtest" })).toBeVisible();
  await assertChartPaths(page);
  await page.screenshot({
    path: resolve(screenshotDir, "desktop-research-report.png"),
    fullPage: true,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of screenRoutes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
    if (route.screenshot === "paper-detail") await assertChartPaths(page);
    if (route.screenshot === "session-report") {
      await assertCurrencyMetric(page, "Trading cost");
      await assertCurrencyMetric(page, "Traded notional");
      await assertCurrencyMetric(page, "Commission");
      await assertCurrencyMetric(page, "Slippage");
    }
    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth,
    }));
    expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
    if (["overview", "paper-detail", "session-report", "settings"].includes(route.screenshot)) {
      await page.screenshot({
        path: resolve(screenshotDir, `mobile-${route.screenshot}.png`),
        fullPage: true,
        animations: "disabled",
      });
    }
    if (route.screenshot === "session-report") {
      const ordersScroller = page.getByRole("region", { name: "Executed orders table" });
      await ordersScroller.focus();
      await page.keyboard.press("ArrowRight");
      expect(await ordersScroller.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    }
  }

  await page.goto("/research");
  await page.getByRole("link", { name: /demo-quality/ }).click();
  await expect(page.getByRole("heading", { name: "demo-quality backtest" })).toBeVisible();
  await assertChartPaths(page);
  const reportDimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
  }));
  expect(reportDimensions.documentWidth).toBeLessThanOrEqual(reportDimensions.viewportWidth);
  await page.screenshot({
    path: resolve(screenshotDir, "mobile-research-report.png"),
    fullPage: true,
    animations: "disabled",
  });

  await page.keyboard.press("Control+k");
  await expect(page.getByPlaceholder("Search pages…")).toBeVisible();
  expect(externalRequests).toEqual([]);
});

test("paper valuation requires an explicit quote refresh", async ({ page }) => {
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  const paper = await (await page.request.get("/api/paper/demo-quality")).json();
  const valuationRequests: { body: unknown; token: string | null }[] = [];
  const estimate = {
    status: "estimated",
    value: "123456.789",
    partial_estimate: null,
    as_of: "2026-10-29T12:00:00Z",
    provenance: "yfinance",
    expected_head: paper.last_record_hash,
    recorded_nav: String(paper.nav),
    request_id: "a".repeat(32),
    deployment: "demo-quality",
    coverage: { total: 1, quoted: 1, usable: 1, missing: 0, stale: 0, errors: 0 },
    quotes: [{
      ticker: "AAPL",
      shares: "100",
      price: "1234.56789",
      quote_time: "2026-10-29T11:59:55Z",
      observation_age_seconds: 5,
      status: "quoted",
      freshness: "unknown",
      reason: "Observation time is not an exchange print time; freshness is unverified.",
    }],
    reason: "Complete symbol coverage; provider print freshness is unverified.",
  };
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({
      json: {
        ...capabilities,
        writes: true,
        read_only: false,
        network: true,
        mutation_token: "browser-valuation-token",
      },
    }),
  );
  await page.route("**/api/paper/demo-quality/valuation", async (route) => {
    const request = route.request();
    if (request.method() !== "POST") {
      await route.continue();
      return;
    }
    valuationRequests.push({
      body: request.postDataJSON(),
      token: request.headers()["x-csrf-token"] ?? null,
    });
    await route.fulfill({ json: estimate });
  });
  await page.goto("/paper/demo-quality");
  await expect(page.getByRole("heading", { name: "demo-quality" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Refresh estimate" })).toBeEnabled();
  expect(valuationRequests).toEqual([]);

  await page.getByRole("button", { name: "Refresh estimate" }).click();
  await expect(page.getByText("Exact estimate · 123456.789")).toBeVisible();
  expect(valuationRequests).toEqual([
    {
      body: { expected_head: paper.last_record_hash },
      token: "browser-valuation-token",
    },
  ]);
});

test("manual tick review accepts once and reload restores durable progress", async ({ page }) => {
  const head = await installSyntheticPaperCapabilities(page);
  const operationId = "2".repeat(32);
  const dueSession = "2024-06-06";
  const stoppedRunner = {
    status: "stopped",
    available: false,
    reason: "No owned runner is active.",
    started_at: null,
    expires_at: null,
    sessions_completed: 0,
    max_sessions: null,
    last_session: null,
  };
  const preview = {
    preview_id: "5".repeat(32),
    preview_digest: "6".repeat(64),
    confirmation_token: "browser-manual-tick-confirmation",
    action: "paper-tick",
    subject_id: "demo-quality",
    expected_head: head,
    due_set: [dueSession],
    capture_id: "3".repeat(32),
    capture_digest: "4".repeat(64),
    expires_at: "2026-10-31T12:10:00+00:00",
    payload: { kind: "manual-tick", session: dueSession, expected_head: head },
    capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
    estimate: {
      maximum_model_calls_per_session: 4,
      maximum_calls: 3,
      maximum_resources: 4,
      maximum_cost_usd: 0,
      market_data_provider: "yfinance",
    },
    warnings: ["Synthetic browser fixture; no provider call."],
  };
  const operation = {
    operation_id: operationId,
    request_id: "browser-manual-tick",
    action: "paper-tick",
    subject_id: "demo-quality",
    capture_id: preview.capture_id,
    capture_digest: preview.capture_digest,
    status: "running",
    created_at: "2026-10-31T12:00:00+00:00",
    updated_at: "2026-10-31T12:00:01+00:00",
    payload: preview.payload,
    result: null,
    progress: 25,
    id: operationId,
    fund: "demo-quality",
    provider: null,
    model: null,
    report_id: null,
    error: null,
    cancel_requested: false,
    status_url: `/api/operations/${operationId}`,
  };
  let previewCount = 0;
  let acceptCount = 0;

  await page.route("**/api/paper/demo-quality/runner", (route) =>
    route.fulfill({ json: stoppedRunner }),
  );
  await page.route("**/api/paper/demo-quality/tick/preview", async (route) => {
    previewCount += 1;
    expect(route.request().headers()["x-csrf-token"]).toBe("browser-paper-control-token");
    expect(route.request().postDataJSON()).toEqual({ expected_head: head });
    await route.fulfill({ status: 201, json: preview });
  });
  await page.route("**/api/paper/demo-quality/tick", async (route) => {
    acceptCount += 1;
    expect(route.request().headers()["x-csrf-token"]).toBe("browser-paper-control-token");
    const body = route.request().postDataJSON() as Record<string, unknown>;
    expect(body).toMatchObject({
      preview_id: preview.preview_id,
      preview_digest: preview.preview_digest,
      confirmation_token: preview.confirmation_token,
      expected_head: head,
      due_set: [dueSession],
    });
    expect(body.request_id).toMatch(/^[a-f0-9]{32}$/);
    await route.fulfill({ status: 202, json: operation });
  });
  await page.route(`**/api/operations/${operationId}`, (route) =>
    route.fulfill({ json: operation }),
  );

  await page.goto("/paper/demo-quality");
  await expect(page.getByRole("heading", { name: "demo-quality" })).toBeVisible();
  const review = page.getByRole("button", { name: "Manual one-session tick" });
  await expect(review).toBeEnabled();
  await review.click();
  const dialog = page.getByRole("dialog", { name: "Confirm one-session paper tick" });
  await expect(dialog).toBeVisible();
  expect(previewCount).toBe(1);
  expect(acceptCount).toBe(0);

  const accept = dialog.getByRole("button", { name: "Accept one-session tick" });
  await accept.evaluate((element) => {
    const button = element as HTMLButtonElement;
    button.click();
    button.click();
  });
  await expect(page.getByText("Manual tick · running")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Paper operation progress" })).toHaveAttribute("aria-valuenow", "25");
  await expect(page.getByText(operationId)).toBeVisible();
  expect(acceptCount).toBe(1);

  await page.reload();
  await expect(page.getByText("Manual tick · running")).toBeVisible();
  await expect(page.getByRole("progressbar", { name: "Paper operation progress" })).toHaveAttribute("aria-valuenow", "25");
  expect(acceptCount).toBe(1);
  expect(previewCount).toBe(1);
  const unchangedPaper = await (await page.request.get("/api/paper/demo-quality")).json();
  expect(unchangedPaper.last_record_hash).toBe(head);
});

test("manual tick rejects stale-head acceptance without creating an operation", async ({ page }) => {
  const head = await installSyntheticPaperCapabilities(page);
  const dueSession = "2024-06-06";
  const preview = {
    preview_id: "5".repeat(32),
    preview_digest: "6".repeat(64),
    confirmation_token: "browser-stale-head-confirmation",
    action: "paper-tick",
    subject_id: "demo-quality",
    expected_head: head,
    due_set: [dueSession],
    capture_id: "3".repeat(32),
    capture_digest: "4".repeat(64),
    expires_at: "2026-10-31T12:10:00+00:00",
    payload: { kind: "manual-tick", session: dueSession, expected_head: head },
    capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
    estimate: {
      maximum_model_calls_per_session: 4,
      maximum_calls: 3,
      maximum_resources: 4,
      maximum_cost_usd: 0,
      market_data_provider: "yfinance",
    },
    warnings: ["Synthetic browser fixture; no provider call."],
  };
  let acceptCount = 0;
  await page.route("**/api/paper/demo-quality/runner", (route) =>
    route.fulfill({
      json: {
        status: "stopped",
        available: false,
        reason: "No owned runner is active.",
        started_at: null,
        expires_at: null,
        sessions_completed: 0,
        max_sessions: null,
        last_session: null,
      },
    }),
  );
  await page.route("**/api/paper/demo-quality/tick/preview", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ expected_head: head });
    await route.fulfill({ status: 201, json: preview });
  });
  await page.route("**/api/paper/demo-quality/tick", async (route) => {
    acceptCount += 1;
    const body = route.request().postDataJSON() as Record<string, unknown>;
    expect(body.expected_head).toBe(head);
    expect(body.due_set).toEqual([dueSession]);
    await route.fulfill({
      status: 409,
      json: { detail: "Ledger head changed; reload before submitting a tick." },
    });
  });

  await page.goto("/paper/demo-quality");
  await expect(page.getByRole("heading", { name: "demo-quality" })).toBeVisible();
  await page.getByRole("button", { name: "Manual one-session tick" }).click();
  const dialog = page.getByRole("dialog", { name: "Confirm one-session paper tick" });
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Accept one-session tick" }).click();
  await expect(page.getByText("Ledger head changed; reload before submitting a tick.")).toBeVisible();
  expect(acceptCount).toBe(1);
  expect(await page.evaluate(() => localStorage.getItem("aihf.paper.demo-quality.operation"))).toBeNull();
  await expect(page.getByText(/Manual tick ·/)).toHaveCount(0);
  const unchangedPaper = await (await page.request.get("/api/paper/demo-quality")).json();
  expect(unchangedPaper.last_record_hash).toBe(head);
});

test("runner browser controls accept finite bounds and request cooperative stop", async ({ page }) => {
  const head = await installSyntheticPaperCapabilities(page);
  const operationId = "7".repeat(32);
  const preview = {
    preview_id: "8".repeat(32),
    preview_digest: "9".repeat(64),
    confirmation_token: "browser-runner-confirmation",
    action: "paper-runner-start",
    subject_id: "demo-quality",
    expected_head: head,
    due_set: [],
    capture_id: "a".repeat(32),
    capture_digest: "b".repeat(64),
    expires_at: "2026-10-31T12:10:00+00:00",
    payload: {
      kind: "runner-start",
      max_sessions: 1,
      max_runtime_minutes: 60,
      max_calls: 63,
      max_resources: 130,
    },
    capture: { data_provider: "yfinance", llm_provider: "Ollama", model: "gemma3:4b" },
    estimate: {
      maximum_model_calls_per_session: 4,
      maximum_calls: 63,
      maximum_resources: 130,
      maximum_cost_usd: 0,
      market_data_provider: "yfinance",
    },
    warnings: ["Synthetic browser fixture; no provider call."],
  };
  const operation = {
    operation_id: operationId,
    request_id: "browser-runner-start",
    action: "paper-runner-start",
    subject_id: "demo-quality",
    capture_id: preview.capture_id,
    capture_digest: preview.capture_digest,
    status: "completed",
    created_at: "2026-10-31T12:00:00+00:00",
    updated_at: "2026-10-31T12:00:01+00:00",
    payload: preview.payload,
    result: { runner: { status: "running" } },
    progress: 100,
    id: operationId,
    fund: "demo-quality",
    provider: null,
    model: null,
    report_id: null,
    error: null,
    cancel_requested: false,
    status_url: `/api/operations/${operationId}`,
  };
  let currentRunner: Record<string, unknown> = {
    status: "stopped",
    available: false,
    reason: "No owned runner is active.",
    started_at: null,
    expires_at: null,
    sessions_completed: 0,
    max_sessions: null,
    last_session: null,
  };
  let startCount = 0;
  let stopCount = 0;

  await page.route("**/api/paper/demo-quality/runner", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: currentRunner });
      return;
    }
    if (route.request().method() === "POST") {
      startCount += 1;
      expect(route.request().headers()["x-csrf-token"]).toBe("browser-paper-control-token");
      const body = route.request().postDataJSON() as Record<string, unknown>;
      expect(body).toMatchObject({
        preview_id: preview.preview_id,
        preview_digest: preview.preview_digest,
        confirmation_token: preview.confirmation_token,
        expected_head: head,
        due_set: [],
        max_sessions: 1,
        max_runtime_minutes: 60,
      });
      expect(body.request_id).toMatch(/^[a-f0-9]{32}$/);
      currentRunner = {
        status: "running",
        available: true,
        reason: null,
        started_at: "2026-10-31T12:00:00+00:00",
        expires_at: "2026-10-31T13:00:00+00:00",
        sessions_completed: 0,
        max_sessions: 1,
        last_session: null,
      };
      await route.fulfill({ status: 202, json: operation });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/paper/demo-quality/runner/preview", async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe("browser-paper-control-token");
    expect(route.request().postDataJSON()).toEqual({
      expected_head: head,
      max_sessions: 1,
      max_runtime_minutes: 60,
    });
    await route.fulfill({ status: 201, json: preview });
  });
  await page.route(`**/api/operations/${operationId}`, (route) =>
    route.fulfill({ json: operation }),
  );
  await page.route("**/api/paper/demo-quality/runner/stop", async (route) => {
    stopCount += 1;
    expect(route.request().headers()["x-csrf-token"]).toBe("browser-paper-control-token");
    const body = route.request().postDataJSON() as Record<string, unknown>;
    expect(body).toEqual({});
    expect(JSON.stringify(body)).not.toContain("pid");
    currentRunner = { ...currentRunner, status: "stopping", reason: "Stop requested." };
    await route.fulfill({ json: currentRunner });
  });

  await page.goto("/paper/demo-quality");
  await expect(page.getByRole("heading", { name: "demo-quality" })).toBeVisible();
  const start = page.getByRole("button", { name: "Start runner" });
  await expect(start).toBeEnabled();
  await start.click();
  const startDialog = page.getByRole("dialog", { name: "Confirm finite runner start" });
  await expect(startDialog).toBeVisible();
  expect(startCount).toBe(0);
  await startDialog.getByRole("button", { name: "Accept finite runner" }).click();
  await expect(page.getByRole("button", { name: "Stop runner" })).toBeEnabled();
  expect(startCount).toBe(1);

  await page.getByRole("button", { name: "Stop runner" }).click();
  const stopDialog = page.getByRole("dialog", { name: "Stop owned runner for demo-quality" });
  await expect(stopDialog).toBeVisible();
  expect(stopCount).toBe(0);
  await stopDialog.getByRole("button", { name: "Request runner stop" }).click();
  await expect(page.getByText("Owned runner stop requested. An in-flight session may finish before it exits.")).toBeVisible();
  expect(stopCount).toBe(1);
  expect(await page.evaluate(() => localStorage.getItem("aihf.paper.demo-quality.operation"))).toBe(operationId);
  const unchangedPaper = await (await page.request.get("/api/paper/demo-quality")).json();
  expect(unchangedPaper.last_record_hash).toBe(head);
  const realRunner = await (await page.request.get("/api/paper/demo-quality/runner")).json();
  expect(realRunner.available).toBe(false);
});

test("builder preserves canonical library models, weights, params, and blend policy", async ({ page }) => {
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  const catalog = await (await page.request.get("/api/catalog")).json();
  let submittedSpec: Record<string, unknown> | null = null;
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({ json: { ...capabilities, writes: true, read_only: false, mutation_token: "browser-test-token" } }),
  );
  await page.route("**/api/mandates", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const body = route.request().postDataJSON() as { spec: Record<string, unknown> };
    submittedSpec = body.spec;
    await route.fulfill({
      status: 201,
      json: {
        name: "canonical-builder-check",
        strategies: [],
        cadence: "weekly",
        capital: 100000,
        benchmark: "SPY",
        approval_required: true,
        broker: "paper",
        spec: body.spec,
      },
    });
  });

  await page.goto("/builder");
  await page.getByLabel("Mandate name").fill("canonical-builder-check");
  await page.getByLabel("Library strategy").first().click();
  await page.getByRole("option", { name: "Deep Value" }).click();
  await expect(page.getByRole("checkbox", { name: /graham/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Add library sleeve" }).click();
  await page.getByLabel("Library strategy").nth(1).click();
  await page.getByRole("option", { name: "Contrarian Value" }).click();
  await page.getByRole("button", { name: "Add custom sleeve" }).click();
  await page.getByRole("checkbox", { name: "Custom analyst buffett" }).check();
  await page.getByRole("checkbox", { name: "Custom analyst druckenmiller" }).check();
  await assertCustomMode(page, "long short");
  await page.getByRole("button", { name: "Save new mandate" }).click();
  await expect(page.getByText("Mandate saved")).toBeVisible();

  expect(submittedSpec).not.toBeNull();
  const configured = (submittedSpec as { strategies: { name: string; models: unknown[]; blend: unknown }[] }).strategies;
  for (const name of ["deep-value", "contrarian-value"]) {
    const library = catalog.strategies.find((strategy: { name: string }) => strategy.name === name);
    const saved = configured.find((strategy) => strategy.name === name);
    expect(saved).toBeDefined();
    expect(saved?.models).toEqual(library.models);
    expect(saved?.blend).toEqual(library.blend);
  }
  const deepValue = configured.find((strategy) => strategy.name === "deep-value");
  const contrarian = configured.find((strategy) => strategy.name === "contrarian-value");
  expect(deepValue?.models.find((model) => (model as { name: string }).name === "graham")).toMatchObject({ name: "graham", weight: 2 });
  expect(contrarian?.models.find((model) => (model as { name: string }).name === "burry")).toMatchObject({ name: "burry", weight: 2 });
  const custom = configured.find((strategy) => strategy.name === "custom");
  expect(custom?.models).toEqual([
    { name: "buffett", weight: 1, params: {} },
    { name: "druckenmiller", weight: 1, params: {} },
  ]);
  expect(custom?.blend).toMatchObject({ mode: "long_short", method: "conviction_weighted", gross_target: 1 });
});

test("backtest requires a server preview, durable acceptance, and boundary cancellation", async ({ page }) => {
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  const settings = await (await page.request.get("/api/settings")).json();
  const mandates = await (await page.request.get("/api/mandates")).json();
  const mandateHash = mandates.items.find((item: { name: string }) => item.name === "demo-quality").mandate_hash as string;
  let previewRequest: Record<string, unknown> | null = null;
  let acceptedRequest: Record<string, unknown> | null = null;
  let cancelRequested = false;
  let cancelCalls = 0;
  let previewCount = 0;
  const operationId = "a".repeat(32);
  const previewResponse = () => {
    previewCount += 1;
    const body = previewRequest as { payload: Record<string, unknown> };
    return {
      preview_id: String(previewCount).padStart(32, "0"),
      preview_digest: "d".repeat(64),
      confirmation_token: `synthetic-confirmation-${previewCount}`,
      action: "backtest",
      subject_id: "demo-quality",
      expected_head: mandateHash,
      due_set: [],
      capture_id: "c".repeat(32),
      capture_digest: "e".repeat(64),
      expires_at: "2026-10-31T12:10:00+00:00",
      payload: body.payload,
      capture: { model: settings.model },
      estimate: {
        maximum_model_calls: 24,
        maximum_cost_usd: 0,
        market_data_provider: settings.data_provider,
      },
      warnings: ["Synthetic browser fixture; no provider call."],
    };
  };
  const fakeOperation = () => ({
    operation_id: operationId,
    request_id: "browser-backtest",
    action: "backtest",
    subject_id: "demo-quality",
    capture_id: "c".repeat(32),
    capture_digest: "e".repeat(64),
    status: cancelRequested ? "cancel-requested" : "running",
    created_at: "2026-10-31T12:00:00+00:00",
    updated_at: "2026-10-31T12:00:01+00:00",
    payload: acceptedRequest?.payload,
    result: null,
    progress: 40,
    id: operationId,
    fund: "demo-quality",
    provider: settings.data_provider,
    model: settings.model,
    report_id: null,
    error: null,
    cancel_requested: cancelRequested,
    status_url: `/api/operations/${operationId}`,
  });
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({ json: { ...capabilities, writes: true, read_only: false, network: true, mutation_token: "browser-test-token" } }),
  );
  await page.route("**/api/operations/preview", async (route) => {
    previewRequest = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 201, json: previewResponse() });
  });
  await page.route("**/api/operations", async (route) => {
    if (route.request().method() === "POST") {
      acceptedRequest = route.request().postDataJSON() as Record<string, unknown>;
      await route.fulfill({ status: 202, json: fakeOperation() });
      return;
    }
    await route.fulfill({ json: { items: acceptedRequest ? [fakeOperation()] : [] } });
  });
  await page.route(`**/api/operations/${operationId}`, (route) =>
    route.fulfill({ json: fakeOperation() }),
  );
  await page.route(`**/api/operations/${operationId}/cancel`, async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe("browser-test-token");
    const body = route.request().postDataJSON() as { request_id?: string };
    expect(body.request_id).toMatch(/^[a-f0-9]{32}$/);
    cancelCalls += 1;
    cancelRequested = true;
    await route.fulfill({ json: fakeOperation() });
  });

  await page.goto("/backtests");
  await page.getByLabel("Ticker universe").fill("AAPL, MSFT");
  await page.getByLabel("Start date").fill("2024-06-03");
  await page.getByLabel("End date").fill("2024-06-07");
  await page.getByRole("button", { name: "Review backtest" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Market-data provider")).toBeVisible();
  await expect(dialog.getByText("LLM model")).toBeVisible();
  await expect(dialog.getByText("Reviewed head")).toBeVisible();
  await expect(dialog.getByText("Preview digest")).toBeVisible();
  await expect(dialog.getByText("Max model calls")).toBeVisible();
  await expect(dialog.getByText(mandateHash, { exact: true })).toBeVisible();
  await expect(dialog.getByText("AAPL, MSFT")).toBeVisible();
  await expect(dialog.getByText("2024-06-03 → 2024-06-07")).toBeVisible();
  await expect(dialog.getByText("Write capability")).toBeVisible();
  await expect(dialog.getByText("Network capability")).toBeVisible();
  expect(previewRequest).toMatchObject({
    action: "backtest",
    subject_id: "demo-quality",
    expected_head: mandateHash,
    payload: {
      fund: "demo-quality",
      universe: ["AAPL", "MSFT"],
      provider: settings.data_provider,
      model: settings.model,
      mandate_hash: mandateHash,
    },
  });
  await page.getByRole("button", { name: "Review later" }).click();
  expect(acceptedRequest).toBeNull();

  await page.getByRole("button", { name: "Review backtest" }).click();
  await page.getByRole("button", { name: "Accept reviewed operation" }).click();
  await expect(
    page.getByRole("region", { name: "Scrollable data table" }).getByText("running", { exact: true }),
  ).toBeVisible();
  expect(acceptedRequest).toMatchObject({
    action: "backtest",
    subject_id: "demo-quality",
    expected_head: mandateHash,
    payload: {
      fund: "demo-quality",
      universe: ["AAPL", "MSFT"],
      start: "2024-06-03",
      end: "2024-06-07",
      provider: settings.data_provider,
      model: settings.model,
      mandate_hash: mandateHash,
    },
  });
  expect(acceptedRequest?.request_id).toMatch(/^[a-f0-9]{32}$/);
  expect(acceptedRequest?.preview_id).toBe("00000000000000000000000000000002");
  expect(acceptedRequest?.confirmation_token).toBe("synthetic-confirmation-2");

  await page.getByRole("button", { name: "Request cancellation" }).click();
  await expect(page.getByText("Cancellation requested…")).toBeVisible();
  await expect(page.getByText(/in-flight model or data step cannot be interrupted/)).toBeVisible();
  expect(cancelCalls).toBe(1);
});

test("deep links reload for .json reports and dotted fund names", async ({ page }) => {
  const paperResponse = await page.request.get("/api/paper/demo-quality");
  const paper = await paperResponse.json();
  const researchResponse = await page.request.get("/api/research");
  const research = await researchResponse.json();
  const reportId = research.items[0].id as string;
  const reportPath = `/research/${encodeURIComponent(reportId)}`;
  paper.name = "demo.quality";
  await page.route("**/api/paper/demo.quality", (route) => route.fulfill({ json: paper }));

  expect(reportId.endsWith(".json")).toBe(true);
  await page.goto(reportPath);
  await expect(page.getByRole("heading", { name: "demo-quality backtest" })).toBeVisible();
  expect(await page.evaluate(() => document.contentType)).toBe("text/html");
  await page.reload();
  await expect(page.getByRole("heading", { name: "demo-quality backtest" })).toBeVisible();

  await page.goto("/paper/demo.quality");
  await expect(page.getByRole("heading", { name: "demo.quality" })).toBeVisible();
  expect(await page.evaluate(() => document.contentType)).toBe("text/html");
  await page.reload();
  await expect(page.getByRole("heading", { name: "demo.quality" })).toBeVisible();
});

test("ungated and halted decisions never present enabled verdict actions", async ({ page }) => {
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  const response = await page.request.get("/api/paper/demo-quality");
  const paper = await response.json();
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({ json: { ...capabilities, writes: true, read_only: false, mutation_token: "browser-test-token" } }),
  );
  await page.route("**/api/paper/demo-quality", (route) => route.fulfill({ json: paper }));

  paper.spec.approval_required = false;
  await page.goto("/paper/demo-quality");
  await expect(page.getByText("Approval not required", { exact: true })).toBeVisible();
  await expect(page.getByText(/This mandate does not require approval/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reject" })).toBeDisabled();

  paper.spec.approval_required = true;
  paper.halted = "test pause";
  paper.halt_state = "halted";
  paper.ledger.ok = false;
  paper.ledger.error = "Ledger verification failed (LedgerError).";
  await page.reload();
  await expect(page.getByText("Halted", { exact: true }).last()).toBeVisible();
  await expect(page.getByText("Halted funds cannot accept a verdict.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Reject" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Resume" })).toBeDisabled();
});

test("restores a running durable operation after navigation and reload", async ({ page }) => {
  const operationId = "c".repeat(32);
  let cancelRequested = false;
  const operation = () => ({
    operation_id: operationId,
    request_id: "restored-backtest",
    action: "backtest",
    subject_id: "demo-quality",
    capture_id: "d".repeat(32),
    capture_digest: "e".repeat(64),
    status: cancelRequested ? "cancel-requested" : "running",
    created_at: "2026-10-31T12:00:00+00:00",
    updated_at: "2026-10-31T12:00:01+00:00",
    payload: {
      fund: "demo-quality",
      universe: ["AAPL"],
      start: "2026-10-01",
      end: "2026-10-30",
      provider: "yfinance",
      model: "provider/model",
      mandate_hash: "a".repeat(64),
    },
    result: null,
    progress: 40,
    id: operationId,
    fund: "demo-quality",
    provider: "yfinance",
    model: "provider/model",
    report_id: null,
    error: null,
    cancel_requested: cancelRequested,
    status_url: `/api/operations/${operationId}`,
  });

  await page.route("**/api/capabilities", (route) =>
    route.fulfill({
      json: {
        mode: "demo",
        read_only: false,
        writes: true,
        network: true,
        protected_names: [],
        mutation_token: "browser-test-token",
        deferred_actions: {},
      },
    }),
  );
  await page.route("**/api/operations", (route) => route.fulfill({ json: { items: [operation()] } }));
  await page.route(`**/api/operations/${operationId}`, (route) => route.fulfill({ json: operation() }));
  await page.route(`**/api/operations/${operationId}/cancel`, async (route) => {
    expect(route.request().headers()["x-csrf-token"]).toBe("browser-test-token");
    const body = route.request().postDataJSON() as { request_id?: string };
    expect(body.request_id).toMatch(/^[a-f0-9]{32}$/);
    cancelRequested = true;
    await route.fulfill({ json: operation() });
  });

  await page.goto("/backtests");
  await expect(page.getByText(operationId)).toBeVisible();
  await expect(page.getByText("40%", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Request cancellation" }).click();
  await expect(page.getByRole("button", { name: "Cancellation requested…" })).toBeVisible();

  const primaryNavigation = page.getByRole("navigation", { name: "Primary navigation" });
  await primaryNavigation.getByRole("link", { name: "Research" }).click();
  await expect(page.getByRole("heading", { name: "Research reports" })).toBeVisible();
  await primaryNavigation.getByRole("link", { name: "Backtests" }).click();
  await expect(page.getByText(operationId)).toBeVisible();

  await page.reload();
  await expect(page.getByText(operationId)).toBeVisible();
  await expect(page.getByText("40%", { exact: true }).first()).toBeVisible();
});
