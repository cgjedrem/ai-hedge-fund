import { afterEach, expect, it, vi } from "vitest";

import { ApiError, apiGet, apiPost, setMutationToken, subscribeApiEvents, type ApiEvent } from "@/lib/api";
import { toActionableError } from "@/lib/errors";

function stubFetch(status: number, body: unknown) {
  const fake = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fake);
  return fake;
}

afterEach(() => {
  vi.unstubAllGlobals();
  setMutationToken(null);
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
  stubFetch(400, {
    detail: [{ loc: ["body", "<redacted>"], type: "extra_forbidden", message: "Invalid request." }],
    code: "invalid-request",
    message: "Invalid request.",
    refresh_required: false,
    retry_policy: "none",
  });

  const error = await apiGet("/api/paper/demo").catch((caught: unknown) => caught);

  expect(error).toMatchObject({ message: "Invalid request.", status: 400, code: "invalid-request" });
});

it("keeps safe identity echoes and drops hostile ones", async () => {
  stubFetch(409, {
    detail: "Mandate changed after review.",
    code: "stale-preview",
    refresh_required: true,
    retry_policy: "review-again",
    subject_id: "demo-quality",
    request_id: "<img src=x>",
    current_head: "a".repeat(64),
  });

  const error = await apiGet("/api/mandates/demo-quality").catch((caught: unknown) => caught);

  expect(error).toMatchObject({ subjectId: "demo-quality", requestId: null, currentHead: "a".repeat(64) });
  expect(toActionableError(error)).toMatchObject({ action: "review-again", reference: "demo-quality" });
});

it("maps a lost read to retry and a lost mutation to inspect-status without retrying it", async () => {
  const fake = vi.fn(async () => { throw new TypeError("Failed to fetch"); });
  vi.stubGlobal("fetch", fake);
  const events: ApiEvent[] = [];
  const unsubscribe = subscribeApiEvents((event) => events.push(event));

  const read = await apiGet("/api/paper").catch((caught: unknown) => caught);
  const write = await apiPost("/api/lifecycle/accept", { request_id: "r1" }).catch((caught: unknown) => caught);
  unsubscribe();

  expect(read).toMatchObject({ status: 0, offline: true, retryPolicy: "retry-read-only" });
  expect(write).toMatchObject({ status: 0, offline: true, retryPolicy: "inspect-status" });
  expect(toActionableError(write)).toMatchObject({ action: "reconnect", guidance: expect.stringMatching(/inspect durable status/) });
  expect(fake).toHaveBeenCalledTimes(2);
  expect(events).toEqual(["connection-lost", "connection-lost"]);
});

it("signals session renewal only for rejected mutations that require reload", async () => {
  const events: ApiEvent[] = [];
  const unsubscribe = subscribeApiEvents((event) => events.push(event));
  const denial = { detail: "A valid server-owned operator session is required.", code: "capability-denied", refresh_required: true, retry_policy: "reload" };
  const fake = stubFetch(403, denial);
  setMutationToken("t".repeat(43));

  const write = await apiPost("/api/paper/demo/halt", { reason: "x" }).catch((caught: unknown) => caught);
  stubFetch(403, { ...denial, refresh_required: false, retry_policy: "none" });
  await apiPost("/api/paper/demo/halt", { reason: "x" }).catch(() => undefined);
  unsubscribe();

  expect(fake).toHaveBeenCalledTimes(1);
  expect(write).toMatchObject({ status: 403, retryPolicy: "reload", refreshRequired: true });
  expect(toActionableError(write)).toMatchObject({ action: "review-again", guidance: expect.stringMatching(/session was renewed/) });
  expect(events).toEqual(["connection-ok", "session-expired", "connection-ok"]);
});

it("permanent faults never offer a retry action", () => {
  for (const [status, code] of [[400, "invalid-request"], [403, "protected-root"], [422, "readiness-denied"], [423, "halted"], [429, "budget-exhausted"]] as const) {
    expect(toActionableError(new ApiError("Denied.", status, { code, retryPolicy: "none" })).action).toBeNull();
  }
  expect(toActionableError(new ApiError("Busy.", 409, { code: "writer-conflict", retryPolicy: "retry-later" })).action).toBe("retry");
  expect(toActionableError(new ApiError("Corrupt.", 423, { code: "replay-corrupt", retryPolicy: "inspect-status" })).action).toBe("inspect-status");
});

it("never claims session renewal or nothing-submitted for a non-session reload conflict", () => {
  const conflict = toActionableError(new ApiError("Fund could not be halted.", 409, { code: "request-conflict", retryPolicy: "reload" }));
  expect(conflict.guidance).not.toMatch(/session was renewed|Nothing was submitted/);
  expect(conflict.guidance).toMatch(/check current status/);
  const writer = toActionableError(new ApiError("Lifecycle admission is unavailable.", 409, { code: "writer-conflict", retryPolicy: "inspect-status" }));
  expect(writer).toMatchObject({ action: "inspect-status" });
  expect(writer.guidance).not.toMatch(/Try again later/);
});

it("bounds an opted-in read so a hung request fails as unreachable instead of hanging", async () => {
  vi.useFakeTimers();
  try {
    vi.stubGlobal("fetch", vi.fn((_path: string, init: RequestInit) => new Promise((_resolve, reject) => {
      init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    const pending = apiGet("/api/capabilities", { timeoutMs: 1_000 }).catch((cause: unknown) => cause);
    await vi.advanceTimersByTimeAsync(1_000);
    expect(await pending).toMatchObject({ status: 0, retryPolicy: "retry-read-only" });
  } finally {
    vi.useRealTimers();
  }
});

it("does not let a response sent before a connection loss report recovery", async () => {
  let releaseEarly: (response: Response) => void = () => undefined;
  const ok = () => new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } });
  vi.stubGlobal("fetch", vi.fn()
    .mockImplementationOnce(() => new Promise<Response>((resolve) => { releaseEarly = resolve; }))
    .mockImplementationOnce(() => Promise.reject(new TypeError("offline")))
    .mockImplementationOnce(() => Promise.resolve(ok())));
  const events: ApiEvent[] = [];
  const unsubscribe = subscribeApiEvents((event) => events.push(event));
  try {
    const early = apiGet("/api/funds");
    await expect(apiGet("/api/funds")).rejects.toMatchObject({ status: 0 });
    releaseEarly(ok());
    await early;
    expect(events).toEqual(["connection-lost"]);
    await apiGet("/api/capabilities");
    expect(events).toEqual(["connection-lost", "connection-ok"]);
  } finally {
    unsubscribe();
  }
});
