import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const screenshotDir = resolve(process.cwd(), "../specs/004-react-web-ui/screenshots");
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
  { path: "/backtests", heading: "Backtest jobs", screenshot: "backtests" },
  { path: "/settings", heading: "Settings", screenshot: "settings" },
];

test.beforeEach(async ({ page }) => {
  const origin = `http://127.0.0.1:${process.env.AIHF_WEB_PORT ?? "8765"}`;
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

test("production routes render at desktop and narrow widths without external requests", async ({ page }) => {
  mkdirSync(screenshotDir, { recursive: true });
  const externalRequests: string[] = [];
  const baseOrigin = `http://127.0.0.1:${process.env.AIHF_WEB_PORT ?? "8765"}`;
  page.on("request", (request) => {
    if (baseOrigin && new URL(request.url()).origin !== baseOrigin) {
      externalRequests.push(request.url());
    }
  });

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");

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

test("backtest requires review, captures inputs, and requests cooperative cancellation", async ({ page }) => {
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  const settings = await (await page.request.get("/api/settings")).json();
  const mandates = await (await page.request.get("/api/mandates")).json();
  const mandateHash = mandates.items.find((item: { name: string }) => item.name === "demo-quality").mandate_hash as string;
  let submitted: Record<string, unknown> | null = null;
  let cancelRequested = false;
  let cancelCalls = 0;
  const jobId = "a".repeat(32);
  const fakeJob = () => ({
    id: jobId,
    fund: "demo-quality",
    provider: settings.data_provider,
    model: settings.model,
    status: "running",
    progress: 40,
    submitted_at: "2024-06-01T12:00:00+00:00",
    started_at: "2024-06-01T12:00:01+00:00",
    completed_at: null,
    report_id: null,
    error: null,
    cancel_requested: cancelRequested,
  });
  await page.route("**/api/capabilities", (route) =>
    route.fulfill({ json: { ...capabilities, writes: true, read_only: false, network: true, mutation_token: "browser-test-token" } }),
  );
  await page.route("**/api/backtests", async (route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 202, json: fakeJob() });
  });
  await page.route(`**/api/jobs/${jobId}`, (route) => route.fulfill({ json: fakeJob() }));
  await page.route(`**/api/jobs/${jobId}/cancel`, async (route) => {
    cancelCalls += 1;
    cancelRequested = true;
    await route.fulfill({ json: fakeJob() });
  });

  await page.goto("/backtests");
  await page.getByLabel("Ticker universe").fill("AAPL, MSFT");
  await page.getByLabel("Start date").fill("2024-06-03");
  await page.getByLabel("End date").fill("2024-06-07");
  await page.getByRole("button", { name: "Review backtest" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("Market-data provider")).toBeVisible();
  await expect(dialog.getByText("LLM model")).toBeVisible();
  await expect(dialog.getByText("Agents")).toBeVisible();
  await expect(dialog.getByText("Mandate hash")).toBeVisible();
  await expect(dialog.getByText(mandateHash, { exact: true })).toBeVisible();
  await expect(dialog.getByText("AAPL, MSFT")).toBeVisible();
  await expect(dialog.getByText("2024-06-03 → 2024-06-07")).toBeVisible();
  await expect(dialog.getByText("Write capability")).toBeVisible();
  await expect(dialog.getByText("Network capability")).toBeVisible();
  await page.getByRole("button", { name: "Review later" }).click();
  expect(submitted).toBeNull();

  await page.getByRole("button", { name: "Review backtest" }).click();
  await page.getByRole("button", { name: "Confirm and submit" }).click();
  await expect(page.getByText("running", { exact: true })).toBeVisible();
  expect(submitted).toMatchObject({
    fund: "demo-quality",
    universe: ["AAPL", "MSFT"],
    start: "2024-06-03",
    end: "2024-06-07",
    provider: settings.data_provider,
    model: settings.model,
    mandate_hash: mandateHash,
  });

  await page.getByRole("button", { name: "Request cancellation" }).click();
  await expect(page.getByText("Cancellation requested…")).toBeVisible();
  await expect(page.getByText(/in-flight provider\/session step cannot be interrupted/)).toBeVisible();
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
