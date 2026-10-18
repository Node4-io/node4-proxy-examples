// Watch static proxy health and replace addresses that have really failed, within your allowance.
//
//   export NODE4_API_KEY='n4k_...'     # read:proxies, plus write:proxies for --replace
//   node replace-unhealthy.mjs              # report only: Node4 health + a probe through each proxy
//   node replace-unhealthy.mjs --replace    # also replace after 3 failed runs in a row (cron it)
//
// Without --replace nothing changes. With it, a proxy is replaced only after --threshold failed
// runs, when Node4 has not already queued a replacement, not within an hour of the last one,
// and at most --max-replacements per run. It stops as soon as the allowance is used:
// 403 (the free tier and Shared Datacenter plans have no replacements; some Premium Datacenter
// plans have 0), 429 with resetsAt (used up this month), or replacementsUsed reaching
// replacementLimit. A replace is never resent blindly: after a timeout, GET /proxies shows
// whether the address changed.
// Guide: https://node4.io/help/automating-ip-replacement-and-proxy-health
import http from "node:http";
import tls from "node:tls";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { parseArgs } from "node:util";
import { Node4Client, Node4Error } from "./node4client.mjs";

const STATE = "proxy-health-state.json";
const { values: a } = parseArgs({
  options: {
    replace: { type: "boolean", default: false },
    threshold: { type: "string", default: "3" },
    "max-replacements": { type: "string", default: "1" },
  },
});

/** GET https://api.ipify.org through an HTTP proxy (CONNECT tunnel, then TLS). Resolves true on 200. */
function probe(p, timeoutMs = 15_000) {
  return new Promise((resolve) => {
    const done = (ok) => { clearTimeout(timer); resolve(ok); };
    const timer = setTimeout(() => { req.destroy(); done(false); }, timeoutMs);
    const auth = Buffer.from(`${p.username}:${p.password}`).toString("base64");
    const req = http.request({ host: p.host, port: p.port, method: "CONNECT", path: "api.ipify.org:443",
      headers: { Host: "api.ipify.org:443", "Proxy-Authorization": `Basic ${auth}` } });
    req.on("connect", (res, socket) => {
      socket.on("error", () => done(false));
      if (res.statusCode !== 200) { socket.destroy(); return done(false); }
      const s = tls.connect({ socket, servername: "api.ipify.org" }, () => {
        s.write("GET / HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n");
      });
      let head = "";
      s.on("data", (c) => {
        head += c;
        if (head.includes("\r\n")) { s.destroy(); done(/^HTTP\/1\.[01] 200 /.test(head)); } // the status line is enough
      });
      s.on("end", () => done(false));
      s.on("error", () => done(false));
    });
    req.on("error", () => done(false));
    req.end();
  });
}

const node4 = new Node4Client();
const state = existsSync(STATE) ? JSON.parse(readFileSync(STATE, "utf8")) : { failures: {}, replacedAt: {} };
const proxies = new Map((await node4.get("/proxies")).proxies.map((p) => [p.id, p]));
const { proxies: health } = await node4.get("/proxies/health");
let replaced = 0;

for (const h of health) {
  const p = proxies.get(h.proxyId);
  if (!p || p.status !== "active" || p.protocol !== "http") continue;
  const key = String(h.proxyId);
  const ok = await probe(p);
  state.failures[key] = ok ? 0 : (state.failures[key] ?? 0) + 1;
  console.log(`${key.padStart(7)} ${h.host.padEnd(16)} node4:${h.isHealthy ? "ok  " : "FAIL"} probe:${ok ? "ok  " : "FAIL"}` +
    ` failed runs:${state.failures[key]}${h.replacementPending ? " queued by Node4" : ""}`);

  if (ok || !a.replace || state.failures[key] < Number(a.threshold) || h.replacementPending) continue;
  if (Date.now() - (state.replacedAt[key] ?? 0) < 3_600_000 || replaced >= Number(a["max-replacements"])) continue;

  let d;
  try {
    d = await node4.post(`/proxies/${h.proxyId}/replace`);
  } catch (e) {
    if (!(e instanceof Node4Error)) throw e;
    if (e.status === null) {
      const now = (await node4.get("/proxies")).proxies.find((x) => x.id === h.proxyId);
      console.log(`${key}: no answer; ${now && now.host !== p.host ? "it was replaced." : "not replaced, will try on a later run."}`);
      continue;
    }
    if (e.status === 403) { console.error("Stop: this plan includes no IP replacements. Alert a person."); break; }
    if (e.status === 429 && e.body.resetsAt) { console.error(`Stop: replacements used up until ${e.body.resetsAt}. Alert a person.`); break; }
    console.log(`${key}: ${e.message}`); // 409 not active / in progress, 503 unavailable (nothing used)
    continue;
  }
  replaced++;
  delete state.failures[key];
  state.replacedAt[key] = Date.now();
  console.log(`${key}: ${d.oldIp} -> ${d.newIp}:${d.newPort} (${d.replacementsUsed}/${d.replacementLimit} used this month)`);
  if (d.replacementsUsed !== null && d.replacementsUsed >= d.replacementLimit) {
    console.error("Stop: that was the last replacement this month. Alert a person.");
    break;
  }
}

writeFileSync(STATE, JSON.stringify(state));
