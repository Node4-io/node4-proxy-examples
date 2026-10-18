// A small, dependency-free client for the Node4 REST API with safe retries (Node.js 18+).
//
//   import { Node4Client } from "./node4client.mjs";
//   const node4 = new Node4Client();            // reads NODE4_API_KEY
//   const { proxies } = await node4.get("/proxies");
//
// Retry rules (https://node4.io/help/api-errors-rate-limits-and-retries):
// - A rate-limit 429 is refused before anything runs, so it is resent after Retry-After
//   for every method. A 429 with `resetsAt` is a used-up monthly allowance: never retried.
// - GETs are retried on 500, 502, 503, non-JSON 5xx pages and dropped connections.
// - POST /orders and /topups are retried only with the SAME Idempotency-Key (502, 503,
//   timeouts, 409 idempotency_in_flight / checkout_in_progress). A purchase 500 is not.
// - Every other write is sent once: after a timeout, read the current state first.
// Limits: 60 requests per minute per key, and 300 per minute per client IP across all keys.

export const BASE = "https://node4.io/api/v1";
const IN_FLIGHT_CODES = new Set(["idempotency_in_flight", "checkout_in_progress"]);

export class Node4Error extends Error {
  constructor(status, body, method = "", path = "") {
    const b = body && typeof body === "object" ? body : {};
    super(`${method} ${path} -> ${status ?? "network error"}: ${b.error ?? (status ? `HTTP ${status}` : "no response")}` +
      (b.code ? ` [${b.code}]` : ""));
    this.status = status; // null for a network error or timeout
    this.body = b;
    this.code = b.code;
  }
}

/** Exponential backoff with jitter, in milliseconds: attempt 0 -> 0.5-1.5 s, capped at 30 s (x1.5). */
export function backoffMs(attempt, { baseMs = 1000, capMs = 30_000, rand = Math.random } = {}) {
  return Math.min(capMs, baseMs * 2 ** attempt) * (0.5 + rand());
}

/**
 * Milliseconds to wait before resending, or null when the request must not be resent.
 * `status` is null for a dropped connection; `body` is null when the answer was not JSON.
 */
export function retryDelayMs(method, status, body, headers, { idempotentPurchase, attempt, maxRetryAfterMs = 120_000, rand = Math.random }) {
  const safeToResend = method === "GET" || idempotentPurchase;
  if (status === 429) {
    if (body && "resetsAt" in body) return null; // allowance used up; Retry-After can be weeks
    const retryAfter = headers.get("retry-after");
    const wait = retryAfter !== null && Number.isFinite(Number(retryAfter)) ? Number(retryAfter) * 1000 : backoffMs(attempt, { rand });
    return wait <= maxRetryAfterMs ? wait : null;
  }
  if (status === null) return safeToResend ? backoffMs(attempt, { rand }) : null;
  if (status === 409 && idempotentPurchase && body && IN_FLIGHT_CODES.has(body.code)) return backoffMs(attempt, { baseMs: 2000, rand });
  if (status === 502 || status === 503 || (status >= 500 && body === null)) return safeToResend ? backoffMs(attempt, { rand }) : null;
  if (status === 500 && method === "GET") return backoffMs(attempt, { rand });
  return null;
}

export class Node4Client {
  constructor({ apiKey = process.env.NODE4_API_KEY, base = process.env.NODE4_API_BASE || BASE, maxAttempts = 5, timeoutMs = 60_000, fetchImpl = fetch, sleep } = {}) {
    if (!apiKey) throw new Error("Set NODE4_API_KEY (create one under Account Settings -> API & Webhooks on node4.io).");
    Object.assign(this, { apiKey, base, maxAttempts, timeoutMs, fetchImpl });
    this.sleep = sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.lastRateLimit = {};
  }

  async request(method, path, { query, body, idempotencyKey, raw = false } = {}) {
    let url = this.base + path;
    if (query) {
      const q = new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== null));
      if ([...q].length) url += `?${q}`;
    }
    const headers = { Authorization: `Bearer ${this.apiKey}`, Accept: "application/json" };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey; // same value on every attempt
    const payload = body !== undefined ? JSON.stringify(body) : undefined;

    for (let attempt = 0; ; attempt++) {
      let res = null;
      let parsed = null;
      try {
        res = await this.fetchImpl(url, { method, headers, body: payload, signal: AbortSignal.timeout(this.timeoutMs) });
      } catch {
        res = null; // dropped connection or timeout
      }
      if (res) {
        this.lastRateLimit = {
          limit: res.headers.get("ratelimit-limit"),
          remaining: res.headers.get("ratelimit-remaining"),
          resetSeconds: res.headers.get("ratelimit-reset"),
        };
        if (res.ok && raw) return Buffer.from(await res.arrayBuffer());
        const text = await res.text();
        try { parsed = text ? JSON.parse(text) : {}; } catch { parsed = null; }
        if (res.ok) return parsed && "data" in parsed ? parsed.data : parsed;
      }
      const status = res ? res.status : null;
      const delay = retryDelayMs(method, status, parsed, res ? res.headers : new Headers(), {
        idempotentPurchase: Boolean(idempotencyKey),
        attempt,
      });
      if (delay === null || attempt >= this.maxAttempts - 1) throw new Node4Error(status, parsed, method, path);
      await this.sleep(delay);
    }
  }

  get(path, query) { return this.request("GET", path, { query }); }
  post(path, body = {}, idempotencyKey) { return this.request("POST", path, { body, idempotencyKey }); }
  patch(path, body) { return this.request("PATCH", path, { body }); }
  delete(path, query) { return this.request("DELETE", path, { query }); }
}
