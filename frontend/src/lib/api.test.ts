import { afterEach, expect, it, vi } from "vitest";

import { ApiError, acceptOperation, apiDelete, apiGet, apiPost, cancelOperation, getOperation, isPreAdmissionDenial, previewOperation, setMutationToken, subscribeApiEvents, type ApiEvent } from "@/lib/api";
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

it("submits a backtest preview once through the same-origin CSRF-guarded client", async () => {
  const request = {
    action: "backtest" as const,
    subject_id: "synthetic-fund",
    expected_head: "a".repeat(64),
    payload: {
      fund: "synthetic-fund",
      universe: ["TEST"],
      start: "2026-01-01",
      end: "2026-01-02",
      provider: "fixture",
      model: "fixture",
      mandate_hash: "a".repeat(64),
    },
  };
  const response = { preview_id: "b".repeat(32), confirmation_token: "synthetic-confirmation" };
  const fake = stubFetch(201, response);
  setMutationToken("synthetic-csrf");

  expect(await previewOperation(request)).toEqual(response);
  expect(fake).toHaveBeenCalledTimes(1);
  expect(fake).toHaveBeenCalledWith("/api/operations/preview", expect.objectContaining({
    method: "POST",
    mode: "same-origin",
    credentials: "same-origin",
    cache: "no-store",
    body: JSON.stringify(request),
    headers: expect.objectContaining({
      "content-type": "application/json",
      "x-csrf-token": "synthetic-csrf",
    }),
  }));
});

it("does not retry or persist an admission when its response is lost", async () => {
  const request = {
    request_id: "synthetic-request",
    action: "backtest" as const,
    subject_id: "synthetic-fund",
    preview_id: "b".repeat(32),
    preview_digest: "c".repeat(64),
    confirmation_token: "synthetic-confirmation",
    expected_head: "a".repeat(64),
    due_set: [],
    payload: {
      fund: "synthetic-fund",
      universe: ["TEST"],
      start: "2026-01-01",
      end: "2026-01-02",
      provider: "fixture",
      model: "fixture",
      mandate_hash: "a".repeat(64),
    },
  };
  const fake = vi.fn(async () => { throw new TypeError("response lost"); });
  vi.stubGlobal("fetch", fake);
  setMutationToken("synthetic-csrf");
  window.localStorage.clear();
  window.sessionStorage.clear();

  await expect(acceptOperation(request)).rejects.toMatchObject({
    status: 0,
    retryPolicy: "inspect-status",
  });
  expect(fake).toHaveBeenCalledTimes(1);
  expect(fake).toHaveBeenCalledWith("/api/operations", expect.objectContaining({
    method: "POST",
    body: JSON.stringify(request),
    headers: expect.objectContaining({ "x-csrf-token": "synthetic-csrf" }),
  }));
  expect(window.localStorage.length).toBe(0);
  expect(window.sessionStorage.length).toBe(0);
});

it("reads only a valid durable operation ID from the local status endpoint", async () => {
  const operationId = "d".repeat(32);
  const receipt = { operation_id: operationId, status: "running" };
  const fake = stubFetch(200, receipt);

  expect(await getOperation(operationId)).toEqual(receipt);
  await expect(getOperation("../settings")).rejects.toThrow("Invalid operation ID.");
  expect(fake).toHaveBeenCalledTimes(1);
  expect(fake).toHaveBeenCalledWith(
    `/api/operations/${operationId}`,
    expect.objectContaining({ method: "GET", mode: "same-origin", credentials: "same-origin" }),
  );
});

it("does not issue a read that was already cancelled", async () => {
  const fake = vi.fn(async () => new Response("{}"));
  vi.stubGlobal("fetch", fake);
  const controller = new AbortController();
  controller.abort();
  const events: ApiEvent[] = [];
  const unsubscribe = subscribeApiEvents((event) => events.push(event));
  try {
    await expect(getOperation("a".repeat(32), { signal: controller.signal })).rejects.toMatchObject({ name: "AbortError" });
    expect(fake).not.toHaveBeenCalled();
    expect(events).not.toContain("connection-lost");
  } finally {
    unsubscribe();
  }
});

it("sends a separately identified cancellation once and reports a lost response as ambiguous", async () => {
  const operationId = "e".repeat(32);
  const receipt = {
    id: operationId, operation_id: operationId, request_id: "original-request",
    action: "backtest", subject_id: "synthetic-fund", fund: "synthetic-fund",
    capture_id: "f".repeat(32), capture_digest: "a".repeat(64),
    created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:01Z",
    status: "cancel-requested", progress: 10,
  };
  const fake = vi.fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(receipt), { status: 200 }))
    .mockRejectedValueOnce(new TypeError("response lost"));
  vi.stubGlobal("fetch", fake);
  setMutationToken("synthetic-csrf");

  expect(await cancelOperation(operationId, { request_id: "cancel-one" })).toEqual(receipt);
  await expect(cancelOperation(operationId, { request_id: "cancel-two" })).rejects.toMatchObject({
    status: 0,
    retryPolicy: "inspect-status",
  });
  await expect(cancelOperation("../settings", { request_id: "cancel-three" })).rejects.toThrow("Invalid operation ID.");
  expect(fake).toHaveBeenCalledTimes(2);
  expect(fake).toHaveBeenNthCalledWith(1, `/api/operations/${operationId}/cancel`, expect.objectContaining({
    method: "POST",
    body: JSON.stringify({ request_id: "cancel-one" }),
    headers: expect.objectContaining({ "x-csrf-token": "synthetic-csrf" }),
  }));
  expect(fake).toHaveBeenNthCalledWith(2, `/api/operations/${operationId}/cancel`, expect.objectContaining({
    body: JSON.stringify({ request_id: "cancel-two" }),
  }));
});

it("does not report an incomplete cancellation receipt as a successful cancellation", async () => {
  const operationId = "e".repeat(32);
  const fake = stubFetch(200, { operation_id: operationId, status: "cancel-requested" });
  await expect(cancelOperation(operationId, { request_id: "cancel-incomplete" })).rejects.toMatchObject({
    status: 200,
    retryPolicy: "inspect-status",
    requestId: "cancel-incomplete",
  });
  expect(fake).toHaveBeenCalledTimes(1);
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

it("handles malformed entries in an error detail array without losing retry guidance", async () => {
  stubFetch(503, {
    detail: [null, 12, { message: 42 }, { message: "Status temporarily unavailable." }],
    code: "observation-conflict",
    retry_policy: "retry-read-only",
  });
  await expect(apiGet("/api/operations")).rejects.toMatchObject({
    message: "Status temporarily unavailable.", status: 503, retryPolicy: "retry-read-only",
  });

  const fake = stubFetch(503, { detail: [null, 12, { message: "Admission unavailable." }] });
  await expect(apiPost("/api/operations", {})).rejects.toMatchObject({
    message: "Admission unavailable.", status: 503, retryPolicy: "inspect-status",
  });
  expect(fake).toHaveBeenCalledTimes(1);
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

it("treats an unreadable successful response as an ambiguous mutation or retryable read", async () => {
  const fake = vi.fn()
    .mockResolvedValueOnce(new Response("{", { status: 202 }))
    .mockResolvedValueOnce(new Response("{", { status: 200 }))
    .mockResolvedValueOnce(new Response("{", { status: 409 }));
  vi.stubGlobal("fetch", fake);
  const events: ApiEvent[] = [];
  const unsubscribe = subscribeApiEvents((event) => events.push(event));
  try {
    const write = await apiPost("/api/operations", { request_id: "r1" }).catch((caught: unknown) => caught);
    const read = await apiGet("/api/operations").catch((caught: unknown) => caught);
    const denied = await apiPost("/api/operations", {}).catch((caught: unknown) => caught);
    expect(write).toMatchObject({ status: 202, retryPolicy: "inspect-status" });
    expect(toActionableError(write).guidance).toMatch(/inspect|status/i);
    expect(read).toMatchObject({ status: 200, retryPolicy: "retry-read-only" });
    expect(denied).toMatchObject({ status: 409, retryPolicy: "inspect-status" });
    expect(fake).toHaveBeenCalledTimes(3);
    expect(events).not.toContain("connection-lost");
  } finally {
    unsubscribe();
  }
});

it("keeps unreadable server errors safe for reads and ambiguous for mutations", async () => {
  const fake = vi.fn()
    .mockResolvedValueOnce(new Response("{", { status: 503 }))
    .mockResolvedValueOnce(new Response("null", { status: 503 }))
    .mockResolvedValueOnce(new Response("{", { status: 503 }))
    .mockResolvedValueOnce(new Response('"unexpected"', { status: 503 }))
    .mockResolvedValueOnce(new Response("[]", { status: 503 }))
    .mockResolvedValueOnce(new Response('"unexpected"', { status: 409 }))
    .mockResolvedValueOnce(new Response("{}", { status: 503 }))
    .mockResolvedValueOnce(new Response('{"error":"unavailable"}', { status: 503 }))
    .mockResolvedValueOnce(new Response('{"detail":"Existing conflict."}', { status: 409 }));
  vi.stubGlobal("fetch", fake);

  await expect(apiGet("/api/operations")).rejects.toMatchObject({ status: 503, retryPolicy: "retry-read-only" });
  await expect(apiGet("/api/operations")).rejects.toMatchObject({ status: 503, retryPolicy: "retry-read-only" });
  await expect(apiPost("/api/operations", {})).rejects.toMatchObject({ status: 503, retryPolicy: "inspect-status" });
  await expect(apiGet("/api/operations")).rejects.toMatchObject({ status: 503, retryPolicy: "retry-read-only" });
  await expect(apiGet("/api/operations")).rejects.toMatchObject({ status: 503, retryPolicy: "retry-read-only" });
  await expect(apiPost("/api/operations", {})).rejects.toMatchObject({ status: 409, retryPolicy: "inspect-status" });
  await expect(apiGet("/api/operations")).rejects.toMatchObject({ status: 503, retryPolicy: "retry-read-only" });
  await expect(apiPost("/api/operations", {})).rejects.toMatchObject({ status: 503, retryPolicy: "inspect-status" });
  await expect(apiPost("/api/operations", {})).rejects.toMatchObject({
    message: "Existing conflict.", status: 409, retryPolicy: "inspect-status",
  });
  expect(fake).toHaveBeenCalledTimes(9);
});

it("allows an explicitly empty DELETE response without accepting an empty operation receipt", async () => {
  const fake = vi.fn()
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fake);

  await expect(apiDelete("/api/settings/credentials/synthetic")).resolves.toBeUndefined();
  await expect(apiPost("/api/operations", { request_id: "r1" })).rejects.toMatchObject({
    status: 204,
    retryPolicy: "inspect-status",
  });
  expect(fake).toHaveBeenCalledTimes(2);
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

it("does not claim that budget exhaustion undoes earlier provider calls", () => {
  const error = toActionableError(new ApiError("Budget exhausted.", 429, { code: "budget-exhausted", retryPolicy: "none" }));
  expect(error.action).toBeNull();
  expect(error.guidance).toMatch(/Earlier calls may have completed/);
  expect(error.guidance).not.toMatch(/nothing was submitted/i);
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

it("surfaces a capacity denial once with its bounded retry hint and never resubmits", async () => {
  const request = {
    request_id: "capacity-request",
    action: "backtest" as const,
    subject_id: "synthetic-fund",
    preview_id: "b".repeat(32),
    preview_digest: "c".repeat(64),
    confirmation_token: "synthetic-confirmation",
    expected_head: "a".repeat(64),
    due_set: [],
    payload: {
      fund: "synthetic-fund",
      universe: ["TEST"],
      start: "2026-01-01",
      end: "2026-01-02",
      provider: "fixture",
      model: "fixture",
      mandate_hash: "a".repeat(64),
    },
  };
  const denial = {
    detail: "Operation capacity is full; this request was not accepted and nothing was started.",
    code: "capacity-denied",
    refresh_required: false,
    retry_policy: "retry-later",
    subject_id: "synthetic-fund",
    request_id: "capacity-request",
    retry_after_seconds: 30,
  };
  const fake = vi.fn(async () => new Response(JSON.stringify(denial), { status: 429, headers: { "Content-Type": "application/json", "Retry-After": "30" } }));
  vi.stubGlobal("fetch", fake);
  setMutationToken("synthetic-csrf");

  const caught = await acceptOperation(request).catch((cause: unknown) => cause);

  expect(fake).toHaveBeenCalledTimes(1);
  expect(caught).toMatchObject({ status: 429, code: "capacity-denied", retryPolicy: "retry-later", retryAfterSeconds: 30, requestId: "capacity-request" });
  expect(isPreAdmissionDenial(caught, "capacity-request")).toBe(true);
  expect(isPreAdmissionDenial(caught, "another-request")).toBe(false);
  expect(toActionableError(caught)).toMatchObject({
    action: "retry",
    guidance: expect.stringMatching(/Nothing was accepted or started.*about 30 s/),
  });
});

it("ignores out-of-bound or misplaced retry hints and uses the header only as a fallback", async () => {
  const base = { detail: "Full.", code: "capacity-denied", refresh_required: false, retry_policy: "retry-later" };
  for (const [status, body, header, expected] of [
    [429, { ...base }, "45", 45],
    [429, { ...base, retry_after_seconds: 12 }, "45", 12],
    [429, { ...base }, "0", null],
    [429, { ...base }, "301", null],
    [429, { ...base }, "Wed, 21 Oct 2026 07:28:00 GMT", null],
    [409, { ...base, code: "writer-conflict", retry_after_seconds: 30 }, "30", null],
  ] as const) {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", "Retry-After": header } })));
    const caught = await apiPost("/api/operations", {}).catch((cause: unknown) => cause) as ApiError;
    expect(caught.retryAfterSeconds).toBe(expected);
  }
});

it("does not treat an unechoed or non-capacity 429 as proof that nothing was accepted", () => {
  expect(isPreAdmissionDenial(new ApiError("Full.", 429, { code: "capacity-denied", retryPolicy: "retry-later" }), "r1")).toBe(false);
  expect(isPreAdmissionDenial(new ApiError("Budget.", 429, { code: "budget-exhausted", requestId: "r1" }), "r1")).toBe(false);
  expect(isPreAdmissionDenial(new ApiError("Unknown.", 409, { code: "ownership-unknown", requestId: "r1" }), "r1")).toBe(false);
  expect(isPreAdmissionDenial(new ApiError("Expired.", 410, { code: "expired-confirmation" }), "r1")).toBe(true);
});
