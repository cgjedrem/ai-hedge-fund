import { expect, test, type Page, type Request } from "@playwright/test";

const enabled = process.env.AIHF_WEB_LIFECYCLE_ACCEPTANCE === "1";
const origin = "http://127.0.0.1:8876";
test.skip(!enabled, "Recovery acceptance requires the owned synthetic writable harness.");
test.describe.configure({ mode: "serial" });

// The route hook is only an external-network guard; every API response below comes from the real synthetic server.
test.beforeEach(async ({ page }) => {
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) return route.abort();
    return route.continue();
  });
});

function recordApi(page: Page): Request[] {
  const requests: Request[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin !== origin) throw new Error(`External request attempted: ${request.url()}`);
    if (url.pathname.startsWith("/api/")) requests.push(request);
  });
  return requests;
}

const posts = (requests: Request[], path: string) =>
  requests.filter((request) => request.method() === "POST" && new URL(request.url()).pathname === path);

async function archiveCount(page: Page): Promise<number> {
  const response = await page.request.get("/api/lifecycle/archives");
  expect(response.ok(), await response.text()).toBe(true);
  return (await response.json()).items.length;
}

test("stale lifecycle review shows a real 409 and Review again requests a fresh review without resubmitting", async ({ page }) => {
  const requests = recordApi(page);
  await page.goto("/mandates/demo-quality");
  const capabilities = await (await page.request.get("/api/capabilities")).json();
  expect(capabilities.writes).toBe(true);
  expect(capabilities.network).toBe(false);
  const archivesBefore = await archiveCount(page);

  const previewResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/lifecycle/preview"
    && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  const initialPreview = await previewResponse;
  expect(initialPreview.status(), await initialPreview.text()).toBe(200);
  const review = page.getByRole("dialog");
  await expect(review.getByRole("button", { name: "Confirm archive" })).toBeEnabled();
  const mandate = await (await page.request.get("/api/mandates/demo-quality")).json();
  const changed = await page.request.put("/api/mandates/demo-quality", {
    headers: { Origin: origin, "X-CSRF-Token": capabilities.mutation_token },
    data: { expected_hash: mandate.mandate_hash, spec: { ...mandate.spec, capital: mandate.spec.capital + 7 } },
  });
  expect(changed.ok(), await changed.text()).toBe(true);
  const acceptResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/lifecycle/accept");
  await review.getByRole("button", { name: "Confirm archive" }).click();
  const rejected = await acceptResponse;
  expect(rejected.status()).toBe(409);
  const envelope = await rejected.json();
  expect(envelope).toMatchObject({ code: "stale-preview", refresh_required: true, retry_policy: "review-again" });
  expect(typeof envelope.request_id).toBe("string");

  const notice = page.getByRole("alert").filter({ hasText: "Nothing was submitted" });
  await expect(notice).toBeVisible();
  await expect(notice).toContainText(`request ${envelope.request_id}`);
  await notice.getByRole("button", { name: "Review again" }).click();
  const fresh = page.getByRole("dialog");
  await expect(fresh.getByRole("button", { name: "Confirm archive" })).toBeEnabled();
  await fresh.getByRole("button", { name: "Cancel" }).click();

  expect(posts(requests, "/api/lifecycle/accept")).toHaveLength(1);
  expect(posts(requests, "/api/lifecycle/preview")).toHaveLength(2);
  expect(await archiveCount(page)).toBe(archivesBefore);
});

test("a lost operator session is renewed by read-only reload and the rejected request is never auto-resubmitted", async ({ page, context }) => {
  const requests = recordApi(page);
  await page.goto("/mandates/demo-quality");
  await expect(page.getByRole("button", { name: "Review archive", exact: true })).toBeEnabled();
  const archivesBefore = await archiveCount(page);
  await context.clearCookies();

  const previewResponse = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/lifecycle/preview");
  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  const denied = await previewResponse;
  expect(denied.status()).toBe(403);
  expect(await denied.json()).toMatchObject({ code: "capability-denied", refresh_required: true, retry_policy: "reload" });
  await expect(page.getByText(/Operator session was renewed\. The rejected request was not submitted/)).toBeVisible();
  await expect.poll(() => requests.filter((request) => new URL(request.url()).pathname === "/api/capabilities").length).toBeGreaterThan(1);
  expect(posts(requests, "/api/lifecycle/preview")).toHaveLength(1);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByRole("button", { name: "Dismiss" }).click();
  await page.getByRole("alert").filter({ hasText: "Nothing was submitted" }).getByRole("button", { name: "Review again" }).click();
  const review = page.getByRole("dialog");
  await expect(review.getByRole("button", { name: "Confirm archive" })).toBeEnabled();
  await review.getByRole("button", { name: "Cancel" }).click();
  expect(posts(requests, "/api/lifecycle/preview")).toHaveLength(2);
  expect(posts(requests, "/api/lifecycle/accept")).toHaveLength(0);
  expect(await archiveCount(page)).toBe(archivesBefore);
});

test("losing the local server connection shows a reconnect banner and Reconnect reloads real data", async ({ page, context }) => {
  const requests = recordApi(page);
  await page.goto("/mandates");
  await expect(page.getByRole("link", { name: "demo-quality" }).first()).toBeVisible();
  await context.setOffline(true);
  await page.getByRole("link", { name: /^Paper funds/ }).first().click();

  const banner = page.getByRole("alert").filter({ has: page.getByRole("button", { name: "Reconnect" }) });
  await expect(banner).toBeVisible();
  const capabilityChecks = () => requests.filter((request) => new URL(request.url()).pathname === "/api/capabilities").length;
  const checksBefore = capabilityChecks();
  await banner.getByRole("button", { name: "Reconnect" }).click();
  await expect.poll(capabilityChecks).toBeGreaterThan(checksBefore);
  await expect(banner).toContainText("Connection to the local desk was lost");
  await expect(banner.getByRole("button", { name: "Reconnect" })).toBeEnabled();

  await context.setOffline(false);
  // A successful background read may restore the connection before the operator clicks; either path must recover.
  await banner.getByRole("button", { name: "Reconnect" }).click({ timeout: 3_000 }).catch(() => undefined);
  await expect(page.getByText("Connection to the local desk was lost")).toHaveCount(0);
  await expect(page.getByRole("link", { name: "demo-quality" }).first()).toBeVisible();
  expect(requests.filter((request) => request.method() !== "GET")).toEqual([]);
});
