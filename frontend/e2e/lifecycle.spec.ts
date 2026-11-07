import { expect, test } from "@playwright/test";

const enabled = process.env.AIHF_WEB_LIFECYCLE_ACCEPTANCE === "1";
const origin = "http://127.0.0.1:8876";
test.skip(!enabled, "Lifecycle acceptance requires the owned synthetic writable harness.");

test.beforeEach(async ({ page }) => {
  await page.route("**/*", (route) => {
    if (new URL(route.request().url()).origin !== origin) return route.abort();
    return route.continue();
  });
});

test("lifecycle uses real API for stale review, scoped archive and stopped restore", async ({ page }) => {
  test.setTimeout(90_000);
  const external: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).origin !== origin) external.push(request.url());
  });
  await page.goto("/mandates/demo-quality");
  const capabilityResponse = await page.request.get("/api/capabilities");
  expect(capabilityResponse.ok()).toBe(true);
  const capabilities = await capabilityResponse.json();
  expect(capabilities.writes).toBe(true);
  expect(capabilities.network).toBe(false);
  const headers = { Origin: origin, "X-CSRF-Token": capabilities.mutation_token };

  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  const review = page.getByRole("dialog");
  await expect(review.getByRole("button", { name: "Confirm archive" })).toBeEnabled();
  const mandateResponse = await page.request.get("/api/mandates/demo-quality");
  const mandate = await mandateResponse.json();
  const updated = await page.request.put("/api/mandates/demo-quality", {
    headers,
    data: { expected_hash: mandate.mandate_hash, spec: { ...mandate.spec, capital: mandate.spec.capital + 1 } },
  });
  expect(updated.ok(), await updated.text()).toBe(true);
  await review.getByRole("button", { name: "Confirm archive" }).click();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await expect(page.getByText(/changed|stale|review again/i).last()).toBeVisible();
  expect((await page.request.get("/api/mandates/demo-quality")).ok()).toBe(true);

  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm archive" }).click();
  await expect(page).toHaveURL(/\/mandates$/);
  const paperBefore = await page.request.get("/api/paper/demo-quality");
  expect(paperBefore.ok()).toBe(true);
  const paper = await paperBefore.json();
  expect(paper.spec.capital).toBe(mandate.spec.capital);
  await page.getByRole("button", { name: "Review restore", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm restore" }).click();
  await expect(page.getByText("No archived template objects.")).toBeVisible();

  const reports = await (await page.request.get("/api/research")).json();
  const reportId = reports.items[0].id as string;
  await page.goto(`/research/${encodeURIComponent(reportId)}`);
  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm archive" }).click();
  await expect(page).toHaveURL(/\/research$/);
  expect((await page.request.get("/api/paper/demo-quality")).ok()).toBe(true);
  await page.getByRole("button", { name: "Review restore", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm restore" }).click();
  await expect(page.getByText("No archived research objects.")).toBeVisible();
  expect((await page.request.get(`/api/research/${encodeURIComponent(reportId)}`)).ok()).toBe(true);

  await page.goto("/paper/demo-quality");
  await page.getByRole("button", { name: "Review archive", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm archive" }).click();
  await expect(page).toHaveURL(/\/paper$/);
  expect((await page.request.get("/api/mandates/demo-quality")).ok()).toBe(true);
  await page.getByRole("button", { name: "Review restore", exact: true }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirm restore" }).click();
  await expect(page.getByText("No archived deployment objects.")).toBeVisible();
  const restored = await (await page.request.get("/api/paper/demo-quality")).json();
  expect(restored.last_record_hash).toBe(paper.last_record_hash);
  expect(restored.runner.available).toBe(false);
  expect(external).toEqual([]);
});
