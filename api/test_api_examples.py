"""Offline tests: webhook signature checks and the API client's retry rules. No network, no keys.

    python -m unittest -v test_api_examples.py
"""
import hashlib
import hmac
import json
import os
import unittest
import urllib.error

os.environ.setdefault("NODE4_API_KEY", "n4k_test_not_a_real_key")

import webhook_receiver as wr  # noqa: E402
from node4client import Node4Client, Node4Error, backoff_seconds, retry_delay  # noqa: E402

SECRET = "9b2f0c4e1a7d3b6c8e5f2a9d0c1b4e7f6a3d8c2b5e9f1a0d4c7b3e6f2a8d5c1b"
NOW = 1792228443.530  # seconds


def delivery(event="usage.forecast_runout", ts_ms=int(NOW * 1000), event_id="evt_3f9a1c0b7d2e4a6f8b1c2d3e"):
    body = json.dumps({"id": event_id, "event": event, "data": {"percentUsed": 76}, "timestamp": ts_ms},
                      separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, {"X-Node4-Signature": sig, "X-Node4-Event": event, "X-Node4-Event-Id": event_id}


class WebhookSignature(unittest.TestCase):
    def test_valid_signature(self):
        body, h = delivery()
        self.assertTrue(wr.valid_signature(body, h["X-Node4-Signature"], SECRET))

    def test_known_vector(self):
        body = b'{"id":"evt_test","event":"order.completed","data":{},"timestamp":0}'
        expected = hmac.new(b"whsec-example", body, hashlib.sha256).hexdigest()
        self.assertEqual(wr.sign(body, "whsec-example"), expected)

    def test_tampered_body_fails(self):
        body, h = delivery()
        self.assertFalse(wr.valid_signature(body.replace(b"76", b"77"), h["X-Node4-Signature"], SECRET))

    def test_reserialized_json_fails(self):
        body, h = delivery()
        respaced = json.dumps(json.loads(body)).encode()  # default separators add spaces
        self.assertNotEqual(body, respaced)
        self.assertFalse(wr.valid_signature(respaced, h["X-Node4-Signature"], SECRET))

    def test_wrong_or_hex_decoded_secret_fails(self):
        body, h = delivery()
        self.assertFalse(wr.valid_signature(body, h["X-Node4-Signature"], "other-secret"))
        wrong = hmac.new(bytes.fromhex(SECRET), body, hashlib.sha256).hexdigest()
        self.assertNotEqual(wrong, h["X-Node4-Signature"])

    def test_missing_or_garbage_header_fails(self):
        body, _ = delivery()
        for header in ("", None, "abc", "é" * 64):
            self.assertFalse(wr.valid_signature(body, header, SECRET))


class WebhookDelivery(unittest.TestCase):
    def setUp(self):
        self.seen = wr.SeenEvents()

    def test_fresh_delivery_accepted_once(self):
        body, h = delivery()
        status, event = wr.check_delivery(body, h, SECRET, self.seen, now=NOW + 2)
        self.assertEqual(status, 204)
        self.assertEqual(event["event"], "usage.forecast_runout")
        self.assertEqual(wr.check_delivery(body, h, SECRET, self.seen, now=NOW + 3), (200, None))

    def test_retry_with_same_id_is_deduplicated(self):
        b1, h1 = delivery(ts_ms=int(NOW * 1000))
        b2, h2 = delivery(ts_ms=int(NOW * 1000) + 1000)  # re-signed attempt, same event id
        self.assertEqual(wr.check_delivery(b1, h1, SECRET, self.seen, now=NOW)[0], 204)
        self.assertEqual(wr.check_delivery(b2, h2, SECRET, self.seen, now=NOW + 1)[0], 200)

    def test_bad_signature_is_401(self):
        body, h = delivery()
        h["X-Node4-Signature"] = "0" * 64
        self.assertEqual(wr.check_delivery(body, h, SECRET, self.seen, now=NOW)[0], 401)

    def test_replay_outside_window_is_400(self):
        body, h = delivery()
        self.assertEqual(wr.check_delivery(body, h, SECRET, self.seen, now=NOW + 301)[0], 400)
        self.assertEqual(wr.check_delivery(body, h, SECRET, self.seen, now=NOW - 301)[0], 400)

    def test_window_edges(self):
        ts = int(NOW * 1000)
        self.assertTrue(wr.fresh(ts, now=NOW + 299))
        self.assertFalse(wr.fresh(ts, now=NOW + 301))
        self.assertFalse(wr.fresh(None, now=NOW))
        self.assertFalse(wr.fresh(True, now=NOW))
        self.assertFalse(wr.fresh(str(ts), now=NOW))

    def test_every_handled_event_has_a_handler(self):
        for name in ("usage.forecast_runout", "usage.threshold_reached", "order.completed",
                     "proxy.replaced", "renewal.failed"):
            self.assertIn(name, wr.HANDLERS)


def fake_client(responses):
    """A client whose transport replays `responses`: (status, headers, body) or an exception."""
    sleeps, calls = [], []
    c = Node4Client(api_key="n4k_test", sleep=sleeps.append, max_attempts=5)

    def send(method, url, headers, data):
        calls.append((method, url, dict(headers), data))
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        status, hdrs, body = r
        return status, hdrs, body if isinstance(body, bytes) else json.dumps(body).encode()

    c._send = send
    return c, sleeps, calls


OK = (200, {}, {"success": True, "data": {"ok": True}})


class Retries(unittest.TestCase):
    def test_get_retries_5xx_then_succeeds(self):
        c, sleeps, calls = fake_client([(503, {}, {"error": "x"}), (502, {}, {"error": "x"}), OK])
        self.assertEqual(c.get("/profile"), {"ok": True})
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(sleeps), 2)

    def test_get_retries_dropped_connection(self):
        c, _, calls = fake_client([urllib.error.URLError("reset"), OK])
        self.assertEqual(c.get("/proxies"), {"ok": True})
        self.assertEqual(len(calls), 2)

    def test_429_waits_for_retry_after(self):
        c, sleeps, _ = fake_client([(429, {"Retry-After": "7"}, {"error": "Rate limit exceeded.",
                                                                 "retryAfterSeconds": 7}), OK])
        c.get("/usage")
        self.assertEqual(sleeps, [7.0])

    def test_rate_limit_429_is_resent_even_for_a_write(self):
        # Refused before any handler ran, so resending cannot repeat an action.
        c, sleeps, calls = fake_client([(429, {"retry-after": "3"}, {"error": "Too many requests from this IP."}), OK])
        c.post("/sub-users", {"label": "a"})
        self.assertEqual((len(calls), sleeps), (2, [3.0]))

    def test_allowance_429_is_never_retried(self):
        c, sleeps, calls = fake_client([(429, {"Retry-After": "1209600"},
                                         {"error": "used", "replacementLimit": 1, "resetsAt": "2026-11-01T00:00:00Z"})])
        with self.assertRaises(Node4Error) as cm:
            c.post("/proxies/1202/replace")
        self.assertEqual((cm.exception.status, len(calls), sleeps), (429, 1, []))

    def test_retry_after_longer_than_cap_gives_up(self):
        c, sleeps, _ = fake_client([(429, {"Retry-After": "600"}, {"error": "x"})])
        with self.assertRaises(Node4Error):
            c.get("/usage")
        self.assertEqual(sleeps, [])

    def test_non_idempotent_write_is_not_retried_on_5xx_or_timeout(self):
        for first in ((503, {}, {"error": "x"}), TimeoutError("timed out"), (502, {}, b"<html>bad gateway</html>")):
            c, sleeps, calls = fake_client([first, OK])
            with self.assertRaises(Node4Error):
                c.post("/proxies/1202/replace")
            self.assertEqual((len(calls), sleeps), (1, []))

    def test_purchase_retries_with_the_same_key(self):
        c, _, calls = fake_client([TimeoutError("timed out"), (503, {}, {"error": "x", "code": "unavailable"}),
                                   (409, {}, {"error": "x", "code": "idempotency_in_flight"}),
                                   (201, {"Idempotent-Replayed": "true"}, {"success": True, "data": {"order": {"id": 1}}})])
        out = c.post("/orders", {"planId": 12, "paymentMethod": "card"}, idempotency_key="key-123")
        self.assertEqual(out["order"]["id"], 1)
        keys = {call[2]["Idempotency-Key"] for call in calls}
        bodies = {call[3] for call in calls}
        self.assertEqual((len(calls), keys, len(bodies)), (4, {"key-123"}, 1))

    def test_purchase_500_and_stop_codes_are_not_retried(self):
        for resp in ((500, {}, {"error": "x", "code": "checkout_error"}),
                     (409, {}, {"error": "x", "code": "outcome_unknown"}),
                     (409, {}, {"error": "x", "code": "duplicate_recent_purchase", "orderId": 9}),
                     (402, {}, {"error": "x", "code": "card_declined"}),
                     (422, {}, {"error": "x", "code": "idempotency_key_reused"})):
            c, sleeps, calls = fake_client([resp, OK])
            with self.assertRaises(Node4Error) as cm:
                c.post("/orders", {"planId": 12}, idempotency_key="k")
            self.assertEqual((len(calls), sleeps, cm.exception.code), (1, [], resp[2]["code"]))

    def test_4xx_is_final(self):
        for status in (400, 401, 403, 404, 422):
            c, _, calls = fake_client([(status, {}, {"error": "x"}), OK])
            with self.assertRaises(Node4Error):
                c.get("/proxies")
            self.assertEqual(len(calls), 1)

    def test_gives_up_after_max_attempts(self):
        c, sleeps, calls = fake_client([(503, {}, {"error": "x"})] * 5)
        with self.assertRaises(Node4Error):
            c.get("/proxies")
        self.assertEqual((len(calls), len(sleeps)), (5, 4))

    def test_backoff_grows_and_is_capped(self):
        self.assertEqual(backoff_seconds(0, rand=lambda: 0.5), 1.0)
        self.assertEqual(backoff_seconds(3, rand=lambda: 0.5), 8.0)
        self.assertEqual(backoff_seconds(10, rand=lambda: 0.5), 30.0)
        self.assertLessEqual(backoff_seconds(10, rand=lambda: 0.999), 45.0)

    def test_retry_delay_table(self):
        d = lambda m, s, b=None, h=None, key=False: retry_delay(m, s, b if b is not None else {}, h or {},
                                                               idempotent_purchase=key, attempt=0, rand=lambda: 0.5)
        self.assertIsNotNone(d("GET", 500))
        self.assertIsNone(d("POST", 500, key=True))
        self.assertIsNone(d("POST", 503))
        self.assertIsNotNone(d("POST", 503, key=True))
        self.assertIsNone(d("POST", None))
        self.assertIsNotNone(d("POST", None, key=True))
        self.assertIsNone(d("POST", 409, {"code": "idempotency_in_flight"}))  # no key: not a purchase retry
        self.assertEqual(d("DELETE", 429, h={"retry-after": "5"}), 5.0)


if __name__ == "__main__":
    unittest.main()
