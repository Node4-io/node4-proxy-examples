// Offline tests for webhook signature checks. Run: node --test
import { test } from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import { checkDelivery, fresh, handlers, SeenEvents, sign, validSignature } from "./webhook-receiver.mjs";

const SECRET = "9b2f0c4e1a7d3b6c8e5f2a9d0c1b4e7f6a3d8c2b5e9f1a0d4c7b3e6f2a8d5c1b";
const NOW = 1792228443530;

function delivery({ event = "usage.forecast_runout", ts = NOW, id = "evt_3f9a1c0b7d2e4a6f8b1c2d3e" } = {}) {
  const body = Buffer.from(JSON.stringify({ id, event, data: { percentUsed: 76 }, timestamp: ts }));
  const sig = crypto.createHmac("sha256", Buffer.from(SECRET, "utf8")).update(body).digest("hex");
  return { body, headers: { "x-node4-signature": sig, "x-node4-event": event, "x-node4-event-id": id } };
}

test("valid signature passes, known vector matches", () => {
  const { body, headers } = delivery();
  assert.ok(validSignature(body, headers["x-node4-signature"], SECRET));
  const v = Buffer.from('{"id":"evt_test","event":"order.completed","data":{},"timestamp":0}');
  assert.equal(sign(v, "whsec-example"), crypto.createHmac("sha256", "whsec-example").update(v).digest("hex"));
});

test("tampered body, re-serialized JSON, wrong or hex-decoded secret all fail", () => {
  const { body, headers } = delivery();
  const sig = headers["x-node4-signature"];
  assert.equal(validSignature(Buffer.from(body.toString().replace("76", "77")), sig, SECRET), false);
  assert.equal(validSignature(Buffer.from(JSON.stringify(JSON.parse(body), null, 1)), sig, SECRET), false);
  assert.equal(validSignature(body, sig, "other-secret"), false);
  assert.notEqual(crypto.createHmac("sha256", Buffer.from(SECRET, "hex")).update(body).digest("hex"), sig);
});

test("missing or malformed header fails without throwing", () => {
  const { body } = delivery();
  for (const h of [undefined, "", "abc", "é".repeat(64)]) assert.equal(validSignature(body, h, SECRET), false);
});

test("fresh delivery accepted once, retry with the same id deduplicated", () => {
  const seen = new SeenEvents();
  const first = delivery();
  const retry = delivery({ ts: NOW + 1000 }); // re-signed attempt, same event id
  const [status, event] = checkDelivery(first.body, first.headers, SECRET, seen, NOW + 2000);
  assert.equal(status, 204);
  assert.equal(event.event, "usage.forecast_runout");
  assert.deepEqual(checkDelivery(retry.body, retry.headers, SECRET, seen, NOW + 3000), [200, null]);
});

test("bad signature is 401, replay outside the window is 400", () => {
  const seen = new SeenEvents();
  const d = delivery();
  assert.equal(checkDelivery(d.body, { "x-node4-signature": "0".repeat(64) }, SECRET, seen, NOW)[0], 401);
  assert.equal(checkDelivery(d.body, d.headers, SECRET, seen, NOW + 301_000)[0], 400);
  assert.equal(checkDelivery(d.body, d.headers, SECRET, seen, NOW - 301_000)[0], 400);
});

test("window edges and bad timestamps", () => {
  assert.ok(fresh(NOW, NOW + 299_000));
  assert.equal(fresh(NOW, NOW + 301_000), false);
  for (const t of [undefined, null, String(NOW), NaN]) assert.equal(fresh(t, NOW), false);
});

test("every event the guide lists has a handler", () => {
  for (const e of ["usage.forecast_runout", "usage.threshold_reached", "order.completed", "proxy.replaced", "renewal.failed"]) {
    assert.equal(typeof handlers[e], "function");
  }
});
