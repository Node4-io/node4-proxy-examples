// Offline tests for the API client's retry rules. Run: node --test
import { test } from "node:test";
import assert from "node:assert/strict";
import { backoffMs, Node4Client, Node4Error, retryDelayMs } from "./node4client.mjs";

const json = (status, body, headers = {}) =>
  new Response(typeof body === "string" ? body : JSON.stringify(body), { status, headers });
const OK = () => json(200, { success: true, data: { ok: true } });

function fakeClient(responses) {
  const calls = [];
  const sleeps = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, ...init });
    const r = responses.shift();
    if (r instanceof Error) throw r;
    return r();
  };
  return { client: new Node4Client({ apiKey: "n4k_test", fetchImpl, sleep: async (ms) => { sleeps.push(ms); } }), calls, sleeps };
}

test("GET retries 5xx and dropped connections, then succeeds", async () => {
  const { client, calls, sleeps } = fakeClient([() => json(503, { error: "x" }), new TypeError("fetch failed"), OK]);
  assert.deepEqual(await client.get("/profile"), { ok: true });
  assert.equal(calls.length, 3);
  assert.equal(sleeps.length, 2);
});

test("429 waits for Retry-After, even on a write", async () => {
  const { client, calls, sleeps } = fakeClient([() => json(429, { error: "Rate limit exceeded." }, { "Retry-After": "7" }), OK]);
  await client.post("/sub-users", { label: "a" });
  assert.deepEqual([calls.length, sleeps], [2, [7000]]);
});

test("allowance 429 (resetsAt) is never retried", async () => {
  const { client, calls, sleeps } = fakeClient([() => json(429, { error: "used", resetsAt: "2026-11-01T00:00:00Z" }, { "Retry-After": "1209600" })]);
  await assert.rejects(client.post("/proxies/1202/replace"), (e) => e instanceof Node4Error && e.status === 429);
  assert.deepEqual([calls.length, sleeps], [1, []]);
});

test("Retry-After beyond the cap gives up", async () => {
  const { client, sleeps } = fakeClient([() => json(429, { error: "x" }, { "Retry-After": "600" })]);
  await assert.rejects(client.get("/usage"), Node4Error);
  assert.deepEqual(sleeps, []);
});

test("non-idempotent writes are sent once on 5xx, timeout or an HTML error page", async () => {
  for (const first of [() => json(503, { error: "x" }), new DOMException("timed out", "TimeoutError"), () => json(502, "<html>bad gateway</html>")]) {
    const { client, calls, sleeps } = fakeClient([first, OK]);
    await assert.rejects(client.post("/proxies/1202/replace"), Node4Error);
    assert.deepEqual([calls.length, sleeps], [1, []]);
  }
});

test("a purchase is retried with the same key and body", async () => {
  const { client, calls } = fakeClient([
    new TypeError("fetch failed"),
    () => json(503, { error: "x", code: "unavailable" }),
    () => json(409, { error: "x", code: "idempotency_in_flight" }),
    () => json(201, { success: true, data: { order: { id: 1 } } }, { "Idempotent-Replayed": "true" }),
  ]);
  const out = await client.post("/orders", { planId: 12, paymentMethod: "card" }, "key-123");
  assert.equal(out.order.id, 1);
  assert.equal(calls.length, 4);
  assert.deepEqual(new Set(calls.map((c) => c.headers["Idempotency-Key"])), new Set(["key-123"]));
  assert.equal(new Set(calls.map((c) => c.body)).size, 1);
});

test("purchase 500 and stop codes are not retried", async () => {
  for (const [status, code] of [[500, "checkout_error"], [409, "outcome_unknown"], [409, "duplicate_recent_purchase"], [402, "card_declined"], [422, "idempotency_key_reused"]]) {
    const { client, calls } = fakeClient([() => json(status, { error: "x", code }), OK]);
    await assert.rejects(client.post("/orders", { planId: 12 }, "k"), (e) => e.code === code);
    assert.equal(calls.length, 1);
  }
});

test("4xx is final; gives up after maxAttempts", async () => {
  for (const status of [400, 401, 403, 404, 422]) {
    const { client, calls } = fakeClient([() => json(status, { error: "x" }), OK]);
    await assert.rejects(client.get("/proxies"), Node4Error);
    assert.equal(calls.length, 1);
  }
  const { client, calls, sleeps } = fakeClient(Array(5).fill(() => json(503, { error: "x" })));
  await assert.rejects(client.get("/proxies"), Node4Error);
  assert.deepEqual([calls.length, sleeps.length], [5, 4]);
});

test("backoff grows and is capped; decision table", () => {
  const half = { rand: () => 0.5 };
  assert.equal(backoffMs(0, half), 1000);
  assert.equal(backoffMs(3, half), 8000);
  assert.equal(backoffMs(10, half), 30000);
  const d = (m, s, body = {}, key = false, h = {}) => retryDelayMs(m, s, body, new Headers(h), { idempotentPurchase: key, attempt: 0, rand: () => 0.5 });
  assert.notEqual(d("GET", 500), null);
  assert.equal(d("POST", 500, {}, true), null);
  assert.equal(d("POST", 503), null);
  assert.notEqual(d("POST", 503, {}, true), null);
  assert.equal(d("POST", null), null);
  assert.notEqual(d("POST", null, null, true), null);
  assert.equal(d("POST", 409, { code: "idempotency_in_flight" }), null);
  assert.equal(d("DELETE", 429, {}, false, { "retry-after": "5" }), 5000);
});
