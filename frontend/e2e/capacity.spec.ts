import { execFileSync } from "node:child_process";
import { expect, test, type Request } from "@playwright/test";

const enabled = process.env.AIHF_WEB_CAPACITY_ACCEPTANCE === "1";
const origin = "http://127.0.0.1:8876";
const storageKey = "aihf.backtests.selected-operation";

test.skip(!enabled, "Capacity acceptance requires the owned synthetic writable harness.");

function holder(...args: string[]): { operation_id: string; status: string } {
  const python = process.env.AIHF_E2E_PYTHON;
  const root = process.env.AIHF_WEB_DEMO_ROOT;
  if (!python || !root) throw new Error("Owned harness interpreter and demo root are required.");
  const output = execFileSync(
    python,
    ["-m", "hedge_fund.test_support.capacity_holder", ...args.slice(0, 1), "--root", root, ...args.slice(1)],
    { env: process.env, encoding: "utf8", timeout: 60_000 },
  );
  return JSON.parse(output.trim().split(/\r?\n/).at(-1) ?? "{}");
}

test("real capacity denial is unaccepted and observation recovers after a lost connection", async ({ page, context }) => {
  test.setTimeout(120_000);
  const requests: Request[] = [];
  const external: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin !== origin) external.push(request.url());
    else if (url.pathname.startsWith("/api/")) requests.push(request);
  });
  // External-network guard only; every /api call reaches the real server.
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) return route.abort();
    return route.continue();
  });

  await page.goto("/backtests");
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  expect(capabilities.writes).toBe(true);
  // Capability only: the owned test child guard still refuses every non-loopback connection.
  expect(capabilities.network).toBe(true);
  await page.waitForLoadState("networkidle");

  // Another process sharing the root takes the only durable backtest slot after this page loaded.
  const held = holder("hold");
  expect(held.status).toBe("accepted");
  expect(held.operation_id).toMatch(/^[a-f0-9]{32}$/);
  let released = false;
  try {
    await page.getByLabel("Ticker universe").fill("AAPL, MSFT");
    await page.getByLabel("Start date").fill("2024-06-03");
    await page.getByLabel("End date").fill("2024-06-07");
    await page.getByRole("button", { name: "Review backtest" }).click();
    await expect(page.getByRole("button", { name: "Accept reviewed operation" })).toBeVisible();

    const acceptResponse = page.waitForResponse((response) =>
      new URL(response.url()).pathname === "/api/operations" && response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "Accept reviewed operation" }).click();
    const denied = await acceptResponse;
    expect(denied.status()).toBe(429);
    expect(denied.headers()["retry-after"]).toBe("30");
    const body = await denied.json();
    const sent = JSON.parse(denied.request().postData() ?? "{}");
    expect(body).toMatchObject({
      code: "capacity-denied",
      retry_policy: "retry-later",
      retry_after_seconds: 30,
      request_id: sent.request_id,
    });
    await expect(page.getByText(/Nothing was accepted or started/)).toBeVisible();
    await expect(page.getByText(/Suggested wait: about 30 s\./)).toBeVisible();

    const accepts = requests.filter((request) =>
      request.method() === "POST" && new URL(request.url()).pathname === "/api/operations",
    );
    expect(accepts).toHaveLength(1);
    const lookup = await page.request.get(`/api/operations/by-request/${encodeURIComponent(sent.request_id)}`);
    expect(lookup.status()).toBe(404);
    const leftover = await page.evaluate((requestId) =>
      Object.entries(localStorage).some(([key, value]) =>
        (key.startsWith("aihf.pending-operation.") || key.startsWith("aihf.operation-identity."))
        && (key.includes(requestId) || value.includes(requestId)),
      ), sent.request_id);
    expect(leftover).toBe(false);

    // Observe the held operation, lose the connection, settle it out of band, then recover.
    const mutations = requests.filter((request) => request.method() !== "GET").length;
    await page.evaluate(({ key, id }) => localStorage.setItem(key, id), { key: storageKey, id: held.operation_id });
    await page.reload();
    const monitor = page.locator('[aria-live="polite"]').filter({ hasText: held.operation_id });
    await expect(page.getByText(held.operation_id, { exact: true })).toBeVisible();
    await expect(monitor.getByText("accepted", { exact: true })).toBeVisible();

    await context.setOffline(true);
    await expect(page.getByRole("button", { name: "Inspect status" })).toBeVisible({ timeout: 30_000 });
    expect(holder("release", "--operation", held.operation_id).status).toBe("interrupted");
    released = true;
    await context.setOffline(false);

    const recovered = page.waitForResponse((response) =>
      new URL(response.url()).pathname === `/api/operations/${held.operation_id}`
      && response.request().method() === "GET" && response.status() === 200,
    );
    await page.getByRole("button", { name: "Inspect status" }).click();
    expect(await (await recovered).json()).toMatchObject({ id: held.operation_id, status: "interrupted" });
    await expect(monitor.getByText("interrupted", { exact: true })).toBeVisible();
    await page.waitForLoadState("networkidle");
    expect(requests.filter((request) => request.method() !== "GET")).toHaveLength(mutations);
    expect(external).toEqual([]);
  } finally {
    if (!released) {
      try {
        holder("release", "--operation", held.operation_id);
      } catch (error) {
        // Never mask the original failure; the owned root is discarded with the run.
        console.error("capacity holder release failed", error);
      }
    }
  }
});
