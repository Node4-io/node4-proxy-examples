// A Node4 webhook receiver on Node's built-in http module (Node.js 18+, no dependencies).
//
//   export NODE4_WEBHOOK_SECRET='...'   # from the create-webhook response, or Copy secret in the dashboard
//   node webhook-receiver.mjs           # listens on :8000, POST /hooks/node4
//
// Each delivery is checked in this order:
// 1. X-Node4-Signature must equal the hex HMAC-SHA256 of the RAW body, keyed with the secret
//    used as-is (UTF-8, not hex-decoded), compared in constant time. Otherwise 401.
// 2. The body's `timestamp` (send time, epoch ms) must be within 5 minutes of now, so a captured
//    delivery cannot be replayed later. Otherwise 400.
// 3. The event `id` (the same on every retry) is recorded; a repeat is answered 200 and skipped.
// Then it answers 204 at once and handles the event afterwards: Node4 waits up to 10 seconds
// and retries a timeout or 5xx. Put it behind a public HTTPS URL; redirects are not followed.
// Guide: https://node4.io/help/receiving-node4-webhooks
import crypto from "node:crypto";
import http from "node:http";
import { pathToFileURL } from "node:url";

export const PATH = "/hooks/node4";
export const REPLAY_WINDOW_MS = 5 * 60 * 1000;
const MAX_BODY = 1 << 20;

export function sign(rawBody, secret) {
  return crypto.createHmac("sha256", secret).update(rawBody).digest("hex");
}

export function validSignature(rawBody, header, secret) {
  const a = Buffer.from(sign(rawBody, secret), "utf8");
  const b = Buffer.from(String(header ?? "").trim(), "utf8");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export function fresh(timestampMs, now = Date.now(), windowMs = REPLAY_WINDOW_MS) {
  return typeof timestampMs === "number" && Number.isFinite(timestampMs) && Math.abs(now - timestampMs) <= windowMs;
}

/** In-memory de-duplication. Use a table with a unique key in production so restarts remember. */
export class SeenEvents {
  #ids = new Map();
  firstTime(id) {
    if (this.#ids.has(id)) return false;
    this.#ids.set(id, Date.now());
    if (this.#ids.size > 100_000) this.#ids.delete(this.#ids.keys().next().value);
    return true;
  }
}

/** Returns [httpStatus, eventOrNull]. Pure enough to unit test without a server. */
export function checkDelivery(rawBody, headers, secret, seen, now = Date.now()) {
  if (!validSignature(rawBody, headers["x-node4-signature"], secret)) return [401, null];
  let event;
  try { event = JSON.parse(rawBody.toString("utf8")); } catch { return [400, null]; }
  if (!fresh(event.timestamp, now)) return [400, null];
  if (typeof event.id !== "string" || !seen.firstTime(event.id)) return [200, null];
  return [204, event];
}

// ---- What to do with each event. Replace the logs with your own actions. ----
export const handlers = {
  "usage.forecast_runout": (d) => console.log(`${d.planName}: at ${Math.round(d.paceMbPerDay)} MB/day the allowance runs out around ` +
    `${d.runOutAt} (between ${d.earliestAt} and ${d.latestAt ?? "renewal"}), ${d.percentUsed}% used. Top up or slow the job down.`),
  "usage.threshold_reached": (d) => console.log(`${d.planName}: ${d.threshold}% threshold crossed (${Math.round(d.usedMb)} of ${Math.round(d.limitMb)} MB).` +
    (d.threshold >= 100 ? " Metered traffic now stops until a top-up or renewal." : "")),
  "order.completed": (d) => console.log(`order ${d.orderId} (${d.description}) paid and settled; read GET /proxies for new proxies.`),
  "proxy.replaced": (d) => console.log(`proxy ${d.proxyId}: ${d.oldIp} -> ${d.newIp}:${d.newPort} (${d.reason}` +
    `${d.downtimeMinutes ? ` after ${d.downtimeMinutes} min down` : ""}). Fetch the new credentials from GET /proxies.`),
  "renewal.failed": (d) => console.log(`renewal of subscription ${d.subscriptionId} failed (${d.provider}); service is ${d.serviceStatus}. ` +
    "Pay or update the card in the dashboard."),
};

export function handle(event) {
  if (event.data?.test) return console.log("test delivery received"); // the dashboard's Send Test button
  (handlers[event.event] ?? (() => console.log("unhandled event", event.event)))(event.data ?? {});
}

export function createServer(secret, seen = new SeenEvents()) {
  return http.createServer((req, res) => {
    if (req.method !== "POST" || req.url !== PATH) { res.writeHead(404).end(); return; }
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_BODY) { res.writeHead(413).end(); req.destroy(); } else chunks.push(c);
    });
    req.on("end", () => {
      const [status, event] = checkDelivery(Buffer.concat(chunks), req.headers, secret, seen);
      res.writeHead(status).end();
      if (event) setImmediate(() => { try { handle(event); } catch (e) { console.error("handler error:", e); } });
    });
  });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  const secret = process.env.NODE4_WEBHOOK_SECRET;
  if (!secret) { console.error("Set NODE4_WEBHOOK_SECRET to the webhook's secret."); process.exit(1); }
  const port = Number(process.env.PORT ?? 8000);
  createServer(secret).listen(port, () => console.log(`listening on :${port}${PATH}`));
}
