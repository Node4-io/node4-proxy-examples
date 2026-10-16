"""Check a list of static proxies in parallel: is each one up, fast, and leaving from its own IP?

Usage:
    python check_static_proxies.py proxies.txt     # one IP:PORT per line (export from your Proxies page)
    NODE4_PROXY=203.0.113.10:4443 python check_static_proxies.py
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from _env import STATIC, proxy_url


def check(endpoint: str) -> tuple[str, str, float]:
    url = proxy_url(endpoint)
    start = time.monotonic()
    try:
        ip = requests.get("https://api.ipify.org", proxies={"http": url, "https": url}, timeout=20).text.strip()
        status = "OK" if ip == endpoint.split(":")[0] else f"MISMATCH exit={ip}"
    except requests.RequestException as e:
        status = f"FAIL {type(e).__name__}"
    return endpoint, status, time.monotonic() - start


def main() -> None:
    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            # Accepts IP:PORT or IP:PORT:USER:PASS lines (the API's txt export); only
            # IP:PORT is used, the credentials come from NODE4_USER / NODE4_PASS.
            endpoints = [":".join(line.strip().split(":")[:2]) for line in f if line.strip() and not line.startswith("#")]
    elif STATIC:
        endpoints = [STATIC]
    else:
        sys.exit("Pass a file of IP:PORT lines, or set NODE4_PROXY.")
    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(check, endpoints))
    for endpoint, status, secs in results:
        print(f"{endpoint:<24} {status:<28} {secs:5.2f}s")
    bad = sum(1 for _, s, _ in results if s != "OK")
    print(f"\n{len(results) - bad}/{len(results)} healthy")


if __name__ == "__main__":
    main()
