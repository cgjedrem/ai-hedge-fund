import { expect, test, type Request } from "@playwright/test";

const enabled = process.env.AIHF_WEB_LIFECYCLE_ACCEPTANCE === "1";
const origin = "http://127.0.0.1:8876";
const storageKey = "aihf.backtests.selected-operation";

test.skip(!enabled, "Operation recovery requires the owned synthetic writable harness.");

test("real operation receipts survive reload without resubmitting or storing confirmation tokens", async ({ page }) => {
  test.setTimeout(90_000);
  const requests: Request[] = [];
  const external: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin !== origin) external.push(request.url());
    else if (url.pathname.startsWith("/api/")) requests.push(request);
  });
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) return route.abort();
    return route.continue();
  });

  await page.goto("/mandates/demo-quality");
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  expect(capabilities.writes).toBe(true);
  expect(capabilities.network).toBe(false);

  const previewResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/lifecycle/preview"
    && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  const preview = await previewResponse;
  expect(preview.ok()).toBe(true);
  const confirmationToken = (await preview.json()).confirmation_token as string;
  expect(typeof confirmationToken).toBe("string");
  expect(confirmationToken.length).toBeGreaterThan(0);

  const archiveResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/lifecycle/accept"
    && response.request().method() === "POST",
  );
  await page.getByRole("dialog").getByRole("button", { name: "Confirm archive" }).click();
  const archived = await archiveResponse;
  expect(archived.status()).toBe(202);
  const archiveReceipt = await archived.json();
  const archiveId = archiveReceipt.id as string;
  const archiveRequestId = archiveReceipt.request_id as string;
  expect(archiveId).toMatch(/^[a-f0-9]{32}$/);
  expect(archiveRequestId).toMatch(/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/);
  const requestLookup = await page.request.get(`/api/operations/by-request/${encodeURIComponent(archiveRequestId)}`);
  expect(requestLookup.status()).toBe(200);
  expect(await requestLookup.json()).toMatchObject({
    id: archiveId,
    request_id: archiveRequestId,
    action: "lifecycle-archive",
    subject_id: "demo-quality",
  });
  await expect(page).toHaveURL(/\/mandates$/);

  await page.getByRole("button", { name: "Review restore", exact: true }).click();
  const restoreResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/lifecycle/accept"
    && response.request().method() === "POST",
  );
  await page.getByRole("dialog").getByRole("button", { name: "Confirm restore" }).click();
  const restored = await restoreResponse;
  expect(restored.status()).toBe(202);
  const restoreId = (await restored.json()).id as string;
  expect(restoreId).toMatch(/^[a-f0-9]{32}$/);
  expect(restoreId).not.toBe(archiveId);
  await expect(page.getByText("No archived template objects.")).toBeVisible();

  await page.goto("/backtests");
  const selectedStatus = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `/api/operations/${archiveId}`
    && response.request().method() === "GET",
  );
  await page.getByRole("button", { name: `Monitor operation ${archiveId}` }).click();
  const selectedResponse = await selectedStatus;
  expect(selectedResponse.status(), await selectedResponse.text()).toBe(200);
  expect(await selectedResponse.json()).toMatchObject({ id: archiveId, action: "lifecycle-archive" });
  await expect(page.getByText(archiveId, { exact: true })).toBeVisible();
  await expect(page.getByText("Action · lifecycle-archive", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(archiveId);
  const storedToken = await page.evaluate((token) => {
    const values = [...Object.values(localStorage), ...Object.values(sessionStorage)];
    return values.some((value) => value.includes(token));
  }, confirmationToken);
  expect(storedToken).toBe(false);

  const mutationCount = requests.filter((request) => request.method() !== "GET").length;
  const statusResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `/api/operations/${archiveId}`
    && response.request().method() === "GET",
  );
  await page.reload();
  expect((await statusResponse).status()).toBe(200);
  await expect(page.getByText(archiveId, { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: `Monitor operation ${archiveId}` })).toHaveAttribute("aria-pressed", "true");
  await page.waitForLoadState("networkidle");
  expect(requests.filter((request) => request.method() !== "GET")).toHaveLength(mutationCount);
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(archiveId);

  const missingId = "f".repeat(32);
  await page.evaluate(({ key, id }) => localStorage.setItem(key, id), { key: storageKey, id: missingId });
  const missingResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `/api/operations/${missingId}`
    && response.request().method() === "GET",
  );
  await page.reload();
  expect((await missingResponse).status()).toBe(404);
  await expect(page.getByRole("button", { name: "Forget operation" })).toBeVisible();
  await page.waitForLoadState("networkidle");
  expect(await page.evaluate((key) => localStorage.getItem(key), storageKey)).toBe(missingId);
  expect(requests.filter((request) => request.method() !== "GET")).toHaveLength(mutationCount);

  const paperKey = "aihf.paper.demo-quality.operation";
  await page.evaluate(({ key, id }) => localStorage.setItem(key, id), { key: paperKey, id: archiveId });
  const paperStatusResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `/api/operations/${archiveId}`
    && response.request().method() === "GET",
  );
  await page.goto("/paper/demo-quality");
  expect((await paperStatusResponse).status()).toBe(200);
  await expect(page.getByText(/remembered operation is not a paper tick or runner start/i)).toBeVisible();
  await expect(page.getByText("Runner start · completed")).toHaveCount(0);
  expect(await page.evaluate((key) => localStorage.getItem(key), paperKey)).toBe(archiveId);
  await page.getByRole("button", { name: "Forget operation" }).click();
  expect(await page.evaluate((key) => localStorage.getItem(key), paperKey)).toBeNull();

  await page.goto("/backtests");
  const pendingKey = `aihf.pending-operation.${archiveRequestId}`;
  await page.evaluate(({ key, requestId }) => {
    localStorage.setItem(key, JSON.stringify({
      requestId,
      action: "backtest",
      subjectId: "demo-quality",
    }));
  }, { key: pendingKey, requestId: archiveRequestId });
  const requestStatus = page.waitForResponse((response) =>
    new URL(response.url()).pathname === `/api/operations/by-request/${encodeURIComponent(archiveRequestId)}`
    && response.request().method() === "GET",
  );
  await page.reload();
  expect((await requestStatus).status()).toBe(200);
  await expect(page.getByText(/operation status identity is inconsistent/i)).toBeVisible();
  expect(await page.evaluate((key) => localStorage.getItem(key), pendingKey)).not.toBeNull();
  await page.getByRole("button", { name: "Forget pending request" }).click();
  expect(await page.evaluate((key) => localStorage.getItem(key), pendingKey)).toBeNull();
  expect(requests.filter((request) => request.method() !== "GET")).toHaveLength(mutationCount);
  expect(external).toEqual([]);
});
