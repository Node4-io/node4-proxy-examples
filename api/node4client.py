"""A small, dependency-free client for the Node4 REST API, with safe retries.

    from node4client import Node4Client, Node4Error
    node4 = Node4Client()                      # reads NODE4_API_KEY
    proxies = node4.get("/proxies")["proxies"]

Retry rules (https://node4.io/help/api-errors-rate-limits-and-retries):

- A 429 from the rate limiter is refused before anything runs, so it is resent after
  Retry-After for every method. A 429 carrying `resetsAt` is a used-up monthly allowance
  (IP replacements), not the rate limit: it is never retried.
- GETs are retried on 502, 503, 500, non-JSON 5xx pages and dropped connections, with
  exponential backoff and jitter.
- POST /orders and POST /topups are retried only with the SAME Idempotency-Key: on 502,
  503, a dropped connection or timeout, and 409 idempotency_in_flight / checkout_in_progress.
  A purchase 500 is not retried: read the answer and check GET /orders.
- Every other write (replace a proxy, create a sub-user, create a webhook...) is sent once.
  A timeout there does not tell you whether it ran: read the current state before resending.

Limits: 60 requests per minute per key, and 300 per minute per client IP across all keys.
"""
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://node4.io/api/v1"
USER_AGENT = "node4-proxy-examples/1.0"

# 409 codes that mean "the first request with this key is still running; ask again".
IN_FLIGHT_CODES = ("idempotency_in_flight", "checkout_in_progress")


class Node4Error(Exception):
    def __init__(self, status, body, method="", path=""):
        self.status = status  # None for a network error or timeout
        self.body = body if isinstance(body, dict) else {}
        self.code = self.body.get("code")
        msg = self.body.get("error") or (f"HTTP {status}" if status else "no response")
        super().__init__(f"{method} {path} -> {status or 'network error'}: {msg}"
                         + (f" [{self.code}]" if self.code else ""))


def backoff_seconds(attempt, base=1.0, cap=30.0, rand=random.random):
    """Exponential backoff with jitter: attempt 0 -> 0.5-1.5 s, 1 -> 1-3 s, ... capped."""
    return min(cap, base * (2 ** attempt)) * (0.5 + rand())


def retry_delay(method, status, body, headers, *, idempotent_purchase, attempt,
                max_retry_after=120.0, rand=random.random):
    """Seconds to wait before resending, or None when the request must not be resent.

    `status` is None for a dropped connection or timeout. `body` is the parsed JSON body,
    or None when the answer was not JSON (an edge or gateway error page). `headers` has
    lower-case names.
    """
    body = body if isinstance(body, dict) else None
    safe_to_resend = method == "GET" or idempotent_purchase

    if status == 429:
        if body and "resetsAt" in body:
            return None  # monthly allowance used up; Retry-After can be weeks
        try:
            wait = float(headers.get("retry-after"))
        except (TypeError, ValueError):
            wait = backoff_seconds(attempt, rand=rand)
        return wait if wait <= max_retry_after else None

    if status is None:
        return backoff_seconds(attempt, rand=rand) if safe_to_resend else None
    if status == 409 and idempotent_purchase and body and body.get("code") in IN_FLIGHT_CODES:
        return backoff_seconds(attempt, base=2.0, rand=rand)
    if status in (502, 503) or (status >= 500 and body is None):
        return backoff_seconds(attempt, rand=rand) if safe_to_resend else None
    if status == 500 and method == "GET":
        return backoff_seconds(attempt, rand=rand)
    return None


class Node4Client:
    def __init__(self, api_key=None, base=None, max_attempts=5, timeout=60, sleep=time.sleep):
        self.api_key = api_key or os.environ.get("NODE4_API_KEY", "")
        if not self.api_key:
            raise SystemExit("Set NODE4_API_KEY (create one under Account Settings -> API & Webhooks on node4.io).")
        self.base = (base or os.environ.get("NODE4_API_BASE") or BASE).rstrip("/")
        self.max_attempts = max_attempts
        self.timeout = timeout
        self.sleep = sleep
        self.last_rate_limit = {}

    # The one place that touches the network; tests replace it.
    def _send(self, method, url, headers, data):
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def request(self, method, path, *, query=None, json_body=None, idempotency_key=None, raw=False):
        url = self.base + path
        if query:
            url += "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        headers = {"Authorization": f"Bearer {self.api_key}", "User-Agent": USER_AGENT,
                   "Accept": "application/json"}
        data = None
        if json_body is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(json_body).encode()
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key  # same value on every attempt

        for attempt in range(self.max_attempts):
            try:
                status, resp_headers, content = self._send(method, url, headers, data)
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                status, resp_headers, content = None, {}, b""
            resp_headers = {k.lower(): v for k, v in resp_headers.items()}
            try:
                body = json.loads(content) if content else {}
            except ValueError:
                body = None
            self.last_rate_limit = {k: v for k, v in resp_headers.items() if k.startswith("ratelimit")}

            if status is not None and 200 <= status < 300:
                if raw:
                    return content
                return body.get("data", body) if isinstance(body, dict) else content

            delay = retry_delay(method, status, body, resp_headers,
                                idempotent_purchase=bool(idempotency_key), attempt=attempt)
            if delay is None or attempt == self.max_attempts - 1:
                raise Node4Error(status, body, method, path)
            self.sleep(delay)

    def get(self, path, **query):
        return self.request("GET", path, query=query or None)

    def post(self, path, body=None, idempotency_key=None):
        return self.request("POST", path, json_body=body if body is not None else {},
                            idempotency_key=idempotency_key)

    def patch(self, path, body):
        return self.request("PATCH", path, json_body=body)

    def delete(self, path, **query):
        return self.request("DELETE", path, query=query or None)
