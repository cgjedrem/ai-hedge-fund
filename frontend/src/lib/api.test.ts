import { afterEach, expect, it, vi } from "vitest";

import { ApiError, apiGet } from "@/lib/api";

function stubFetch(status: number, body: unknown) {
  const fake = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fake);
  return fake;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

it("exposes the common error envelope on ApiError", async () => {
  stubFetch(409, {
    detail: "Reviewed ledger head changed; review again.",
    code: "stale-preview",
    message: "Reviewed ledger head changed; review again.",
    refresh_required: true,
    retry_policy: "review-again",
  });

  const error = await apiGet("/api/paper/demo").catch((caught: unknown) => caught);

  expect(error).toBeInstanceOf(ApiError);
  expect(error).toMatchObject({
    message: "Reviewed ledger head changed; review again.",
    status: 409,
    code: "stale-preview",
    refreshRequired: true,
    retryPolicy: "review-again",
  });
});

it("treats legacy or unknown envelope values as uncoded and non-retrying", async () => {
  stubFetch(409, { detail: "Conflict.", code: "<script>", refresh_required: "yes", retry_policy: "forever" });

  const error = await apiGet("/api/paper/demo").catch((caught: unknown) => caught);

  expect(error).toMatchObject({ message: "Conflict.", status: 409, code: null, refreshRequired: false, retryPolicy: "none" });
});

it("keeps validation details generic", async () => {
  stubFetch(422, {
    detail: [{ loc: ["body", "<redacted>"], type: "extra_forbidden", message: "Invalid request." }],
    code: "invalid-request",
    message: "Invalid request.",
    refresh_required: false,
    retry_policy: "none",
  });

  const error = await apiGet("/api/paper/demo").catch((caught: unknown) => caught);

  expect(error).toMatchObject({ message: "Invalid request.", status: 422, code: "invalid-request" });
});
