import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

import { expect, test } from "@playwright/test";

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

test("production routes render at desktop and narrow widths without external requests", async ({ page }) => {
  mkdirSync(screenshotDir, { recursive: true });
  const externalRequests: string[] = [];
  const baseOrigin = "http://127.0.0.1:8765";
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
  await page.screenshot({
    path: resolve(screenshotDir, "desktop-research-report.png"),
    fullPage: true,
    animations: "disabled",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  for (const route of screenRoutes) {
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
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
  }

  await page.goto("/research");
  await page.getByRole("link", { name: /demo-quality/ }).click();
  await expect(page.getByRole("heading", { name: "demo-quality backtest" })).toBeVisible();
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
