"""Retry with backoff, and a new exit on each attempt.

A 403 or 429 usually means the target refused that IP or that request rate. Retrying on
the same connection retries from the same IP, so each attempt here opens a new
connection (which can leave from a different exit) and waits a little longer.
"""
import random
import time

import requests

from _env import proxy_url

RETRY_ON = {403, 429, 500, 502, 503, 504}


def fetch(url: str, attempts: int = 4) -> requests.Response:
    proxies = {"http": proxy_url(), "https": proxy_url()}
    for attempt in range(1, attempts + 1):
        try:
            with requests.Session() as s:
                r = s.get(url, proxies=proxies, timeout=30)
            if r.status_code not in RETRY_ON:
                return r
            reason = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            reason = type(e).__name__
        if attempt == attempts:
            raise RuntimeError(f"gave up after {attempts} attempts ({reason})")
        delay = min(30, 2 ** attempt) + random.random()
        print(f"attempt {attempt}: {reason}, retrying in {delay:.1f}s")
        time.sleep(delay)
    raise AssertionError("unreachable")


if __name__ == "__main__":
    print("status:", fetch("https://api.ipify.org").status_code)
