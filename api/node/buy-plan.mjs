// Buy a Node4 plan or top-up safely: one Idempotency-Key per purchase, then poll GET /orders/{id}.
//
//   export NODE4_API_KEY='n4k_...'
//   node buy-plan.mjs                                       # list plans on sale (read:subscription)
//   node buy-plan.mjs --plan dc-10 --payment card           # dry run
//   node buy-plan.mjs --plan dc-10 --payment card --yes     # buys (write:orders), then polls
//   node buy-plan.mjs --topup topup_50gb --yes              # top-up, paid with Bitcoin
//   node buy-plan.mjs --order 9301                          # poll an existing order (read:orders)
//
// Nothing is bought without --yes. The Idempotency-Key is printed before the purchase is sent:
// if the run is interrupted, rerun the same command with --idempotency-key <key> and the server
// replays the first answer instead of charging again.
// Guide: https://node4.io/help/buying-plans-and-top-ups-with-the-api
import { randomUUID } from "node:crypto";
import { parseArgs } from "node:util";
import { Node4Client, Node4Error } from "./node4client.mjs";

const FINAL = new Set(["delivered", "not_delivered", "revoked"]);
const STOP_CODES = new Set(["outcome_unknown", "payment_unconfirmed", "duplicate_recent_purchase", "payment_held"]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const { values: a } = parseArgs({
  options: {
    plan: { type: "string" }, topup: { type: "string" }, payment: { type: "string", default: "bitcoin" },
    country: { type: "string" }, "discount-code": { type: "string" }, "idempotency-key": { type: "string" },
    order: { type: "string" }, interval: { type: "string", default: "30" }, "max-wait": { type: "string", default: "1800" },
    yes: { type: "boolean", default: false },
  },
});

const node4 = new Node4Client();

async function waitForOrder(id) {
  const deadline = Date.now() + Number(a["max-wait"]) * 1000;
  let last;
  for (;;) {
    const { order } = await node4.get(`/orders/${id}`);
    const { status, message } = order.provisioning;
    if (status !== last) console.log(`order ${id}: ${status}${message ? ` (${message})` : ""}`);
    last = status;
    if (FINAL.has(status)) return order;
    if (Date.now() > deadline) throw new Error(`Still ${status}. Check again later with --order ${id}.`);
    await sleep(Number(a.interval) * 1000); // 30 s stays far inside the 60/min key limit
  }
}

if (a.order) {
  console.log("delivered:", (await waitForOrder(a.order)).delivered);
  process.exit(0);
}

if (!a.plan && !a.topup) {
  for (const p of (await node4.get("/plans")).plans) {
    const countries = (p.countries ?? []).map((c) => c.code).join(",");
    console.log(`${String(p.id).padStart(6)}  ${p.slug.padEnd(24)} ${p.name.padEnd(36)} ${p.billingCycle}${countries ? `  countries: ${countries}` : ""}`);
  }
  process.exit(0);
}

let path, body, what;
if (a.topup) {
  [path, body, what] = ["/topups", { addonId: a.topup, paymentMethod: "bitcoin" }, `top-up ${a.topup} (Bitcoin)`];
} else {
  const plan = (await node4.get("/plans")).plans.find((p) => p.slug === a.plan || String(p.id) === a.plan);
  if (!plan) throw new Error(`No plan on sale matches ${a.plan}. Run without arguments to list them.`);
  if (!["card", "bitcoin"].includes(a.payment)) throw new Error("--payment is card or bitcoin");
  [path, body, what] = ["/orders", { planId: plan.id, paymentMethod: a.payment }, `${plan.name} (plan ${plan.id}) by ${a.payment}`];
  if (a.country) body.country = a.country;
}
if (a["discount-code"]) body.discountCode = a["discount-code"];

if (!a.yes) {
  console.log(`Dry run. Would POST ${path} ${JSON.stringify(body)}: ${what}. Add --yes to buy.`);
  process.exit(0);
}

const key = a["idempotency-key"] ?? randomUUID();
console.log(`Idempotency-Key: ${key}  (if interrupted, rerun with --idempotency-key ${key})`);
let data;
try {
  data = await node4.post(path, body, key);
} catch (e) {
  if (!(e instanceof Node4Error)) throw e;
  console.error(e.message);
  if (STOP_CODES.has(e.code)) {
    console.error(`Stop: check GET /orders${e.body.orderId ? `/${e.body.orderId}` : ""} before buying again; never switch keys for this purchase.` +
      (e.body.checkoutUrl ? ` Pay at ${e.body.checkoutUrl}` : ""));
  } else if (e.status === null || e.status >= 500) {
    console.error(`Outcome unclear. Rerun with --idempotency-key ${key} (same body) or check GET /orders.`);
  } else {
    console.error("Nothing was charged. Fix the cause, then buy again (a new key is generated).");
  }
  process.exit(1);
}
if (data.checkoutUrl) console.log("Pay this Bitcoin invoice:", data.checkoutUrl);
console.log("delivered:", (await waitForOrder(data.order.id)).delivered);
