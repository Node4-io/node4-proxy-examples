"""A Node4 webhook receiver using only the Python standard library.

    export NODE4_WEBHOOK_SECRET='...'   # from the create-webhook response, or Copy secret in the dashboard
    python webhook_receiver.py          # listens on :8000, POST /hooks/node4

Each delivery is checked in this order:
1. X-Node4-Signature must equal the hex HMAC-SHA256 of the RAW body, keyed with the secret
   used as-is (UTF-8, not hex-decoded), compared in constant time. Otherwise 401.
2. The body's `timestamp` (send time, epoch milliseconds) must be within REPLAY_WINDOW of
   now, so a captured delivery cannot be replayed later. Otherwise 400.
3. The event `id` (same on every retry) is recorded; a repeat is answered 200 and skipped.
Then the receiver answers 204 at once and handles the event on a worker thread: Node4 waits
up to 10 seconds and retries a timeout or 5xx, so slow work must not block the answer.

Put this behind a public HTTPS URL (a reverse proxy or a tunnel). Node4 refuses internal
destinations and never follows redirects.
Guide: https://node4.io/help/receiving-node4-webhooks
"""
import hashlib
import hmac
import json
import os
import queue
import sqlite3
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PATH = "/hooks/node4"
REPLAY_WINDOW_SECONDS = 300  # retries arrive within seconds; this also allows some clock skew
MAX_BODY = 1 << 20


def sign(raw_body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def valid_signature(raw_body: bytes, header: str, secret: str) -> bool:
    if not header:
        return False
    return hmac.compare_digest(sign(raw_body, secret).encode(), header.strip().encode("utf-8", "replace"))


def fresh(timestamp_ms, now=None, window=REPLAY_WINDOW_SECONDS) -> bool:
    if not isinstance(timestamp_ms, (int, float)) or isinstance(timestamp_ms, bool):
        return False
    now = time.time() if now is None else now
    return abs(now - timestamp_ms / 1000) <= window


class SeenEvents:
    """Durable de-duplication on the event id (SQLite, so a restart does not forget)."""

    def __init__(self, path=":memory:"):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (id TEXT PRIMARY KEY, received_at REAL)")
        self.lock = threading.Lock()

    def first_time(self, event_id: str) -> bool:
        with self.lock:
            cur = self.db.execute("INSERT OR IGNORE INTO seen (id, received_at) VALUES (?, ?)",
                                  (event_id, time.time()))
            return cur.rowcount == 1


def check_delivery(raw_body: bytes, headers, secret: str, seen: SeenEvents, now=None):
    """Return (http_status, event_or_None). Pure enough to unit test without a server."""
    if not valid_signature(raw_body, headers.get("X-Node4-Signature", ""), secret):
        return 401, None
    try:
        event = json.loads(raw_body)
    except ValueError:
        return 400, None
    if not fresh(event.get("timestamp"), now):
        return 400, None
    if not isinstance(event.get("id"), str) or not seen.first_time(event["id"]):
        return 200, None  # already handled (a retry, or the same event on a second webhook)
    return 204, event


# ---- What to do with each event. Replace the prints with your own actions. ----

def on_usage_forecast_runout(d):
    print(f"{d['planName']}: at {d['paceMbPerDay']:.0f} MB/day the allowance runs out around "
          f"{d['runOutAt']} (between {d['earliestAt']} and {d['latestAt'] or 'renewal'}), "
          f"{d['percentUsed']}% used. Top up or slow the job down.")


def on_usage_threshold_reached(d):
    print(f"{d['planName']}: {d['threshold']}% threshold crossed ({d['usedMb']:.0f} of {d['limitMb']:.0f} MB)."
          + (" Metered traffic now stops until a top-up or renewal." if d["threshold"] >= 100 else ""))


def on_order_completed(d):
    print(f"order {d['orderId']} ({d.get('description')}) paid and settled; read GET /proxies for new proxies.")


def on_proxy_replaced(d):
    extra = f" after {d['downtimeMinutes']} min down" if d.get("downtimeMinutes") else ""
    print(f"proxy {d['proxyId']}: {d['oldIp']} -> {d['newIp']}:{d['newPort']} ({d['reason']}{extra}). "
          "Fetch the new credentials from GET /proxies.")


def on_renewal_failed(d):
    print(f"renewal of subscription {d['subscriptionId']} failed ({d['provider']}); service is "
          f"{d['serviceStatus']}. Pay or update the card in the dashboard.")


HANDLERS = {
    "usage.forecast_runout": on_usage_forecast_runout,
    "usage.threshold_reached": on_usage_threshold_reached,
    "order.completed": on_order_completed,
    "proxy.replaced": on_proxy_replaced,
    "renewal.failed": on_renewal_failed,
}


def handle(event):
    data = event.get("data") or {}
    if data.get("test"):  # the dashboard's Send Test button
        print("test delivery received")
        return
    fn = HANDLERS.get(event["event"])
    if fn:
        fn(data)
    else:
        print("unhandled event", event["event"])


def serve(secret, port=8000, db_path="node4_events.db"):
    sys.stdout.reconfigure(line_buffering=True)
    seen = SeenEvents(db_path)
    work = queue.Queue()

    def worker():
        while True:
            event = work.get()
            try:
                handle(event)
            except Exception as e:  # keep the worker alive; log and alert in real code
                print("handler error:", e)

    threading.Thread(target=worker, daemon=True).start()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if self.path != PATH or length > MAX_BODY:
                self.send_response(404)
                self.end_headers()
                return
            raw = self.rfile.read(length)
            status, event = check_delivery(raw, self.headers, secret, seen)
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()
            if event:
                # Recorded as seen and acknowledged: if handling can fail, make the queue durable.
                work.put(event)

    print(f"listening on :{port}{PATH}")
    ThreadingHTTPServer(("", port), Handler).serve_forever()


if __name__ == "__main__":
    secret = os.environ.get("NODE4_WEBHOOK_SECRET", "")
    if not secret:
        raise SystemExit("Set NODE4_WEBHOOK_SECRET to the webhook's secret.")
    serve(secret, int(os.environ.get("PORT", "8000")))
