import { mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

const root = process.env.AIHF_WEB_DEMO_ROOT;
const output = process.env.AIHF_PLAYWRIGHT_OUTPUT_DIR;
const screenshots = process.env.AIHF_PLAYWRIGHT_SCREENSHOT_DIR;
if (process.env.AIHF_WEB_PORT !== "8876" || !root || !output || !screenshots) {
  throw new Error("Report browser acceptance requires an owned synthetic 8876 fixture.");
}
const origin = "http://127.0.0.1:8876";
const clampedFixture = process.env.AIHF_REPORT_PARITY_FIXTURE === "clamped";
const reportPath = "/paper/demo-quality/sessions/2024-06-04";
const persistedPath = join(root, "paper", "demo-quality", "ledger", "2024-06-04.json");

test.beforeEach(async ({ context }) => {
  await context.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) return route.abort();
    return route.continue();
  });
});

test("real read-only API renders recorded clamps and downloads exact canonical JSON by keyboard", async ({ page }) => {
  const persisted = readFileSync(persistedPath);
  expect(persisted.includes(Buffer.from("\r\n"))).toBe(true);
  expect(persisted.toString("utf8").replaceAll("\r\n", "")).not.toContain("\n");
  const canonical = JSON.parse(persisted.toString("utf8"));
  const requests: { method: string; url: string }[] = [];
  page.on("request", (request) => requests.push({ method: request.method(), url: request.url() }));

  const capabilitiesResponse = await page.request.get("/api/capabilities");
  expect(capabilitiesResponse.status()).toBe(200);
  const capabilities = await capabilitiesResponse.json();
  expect(capabilities.writes).toBe(false);
  expect(capabilities.network).toBe(false);
  expect(capabilities.mutation_token).toBeNull();

  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto(reportPath);
  await expect(page.getByRole("heading", { name: "2024-06-04" })).toBeVisible();
  const proposed = page.getByRole("region", { name: "Proposed risk", exact: true });
  await expect(proposed.getByText("Max position: 25.00%", { exact: true })).toBeVisible();
  await expect(page.getByText("No executed clamps", { exact: true })).toBeVisible();
  if (clampedFixture) {
    const clamps = page.getByRole("region", { name: "Proposed risk clamps table", exact: true });
    await expect(clamps.getByText("Position limit", { exact: true })).toBeVisible();
    await expect(clamps.getByText("40.00%", { exact: true })).toBeVisible();
    await expect(clamps.getByText("25.00%", { exact: true })).toBeVisible();
    await expect(page.getByText("<img src=x onerror=alert('report-fixture')>", { exact: true })).toBeVisible();
    await expect(page.locator("img")).toHaveCount(0);
  } else {
    await expect(page.getByText("No proposed clamps", { exact: true })).toBeVisible();
  }
  const weights = page.getByRole("region", { name: "Proposed weights table", exact: true });
  await expect(weights.getByRole("columnheader", { name: "Requested weight (pre-risk)" })).toBeVisible();
  await expect(weights.getByRole("columnheader", { name: "Final weight (post-risk)" })).toBeVisible();
  if (clampedFixture) {
    await expect(weights.getByText("40.00%", { exact: true })).toBeVisible();
    await expect(weights.getByText("-12.50%", { exact: true })).toHaveCount(2);
  }

  const downloadLink = page.getByRole("link", { name: "Download canonical JSON" });
  await expect(downloadLink).toHaveAttribute("href", `/api/paper/demo-quality/sessions/2024-06-04/download?expected_hash=${canonical.hash}`);
  await page.getByRole("link", { name: "Paper fund", exact: true }).focus();
  await page.keyboard.press("Tab");
  await expect(downloadLink).toBeFocused();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.keyboard.press("Enter"),
  ]);
  expect(download.suggestedFilename()).toBe("demo-quality-2024-06-04.json");
  expect(await download.failure()).toBeNull();
  mkdirSync(output, { recursive: true });
  const downloadedPath = join(output, "canonical-session-download.json");
  await download.saveAs(downloadedPath);
  expect(readFileSync(downloadedPath)).toEqual(persisted);
  expect(readFileSync(persistedPath)).toEqual(persisted);
  expect(requests.every((request) => request.method === "GET" && new URL(request.url).origin === origin)).toBe(true);
  expect(await page.evaluate(() => ({ local: localStorage.length, session: sessionStorage.length }))).toEqual({ local: 0, session: 0 });

  const stale = await page.request.get("/api/paper/demo-quality/sessions/2024-06-04/download?expected_hash=" + "0".repeat(64));
  expect(stale.status()).toBe(409);
  expect(stale.headers()["content-disposition"]).toBeUndefined();
  expect((await stale.json()).code).toBe("stale-preview");
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: join(screenshots, "report-clamps-desktop.png"), fullPage: true, animations: "disabled" });
});

test("report weights and risk clamps remain keyboard-scrollable at 360 pixels", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 844 });
  await page.goto(reportPath);
  await expect(page.getByRole("heading", { name: "2024-06-04" })).toBeVisible();
  const weights = page.getByRole("region", { name: "Proposed weights table", exact: true });
  await weights.focus();
  await page.keyboard.press("ArrowRight");
  expect(await weights.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  if (clampedFixture) {
    const clamps = page.getByRole("region", { name: "Proposed risk clamps table", exact: true });
    await clamps.focus();
    await page.keyboard.press("ArrowRight");
    expect(await clamps.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
  }
  const dimensions = await page.evaluate(() => ({
    document: document.documentElement.scrollWidth,
    viewport: document.documentElement.clientWidth,
  }));
  expect(dimensions.document).toBeLessThanOrEqual(dimensions.viewport);
  await expect(page.getByRole("link", { name: "Download canonical JSON" })).toBeVisible();
  mkdirSync(screenshots, { recursive: true });
  await page.screenshot({ path: join(screenshots, "report-clamps-mobile.png"), fullPage: true, animations: "disabled" });
});
