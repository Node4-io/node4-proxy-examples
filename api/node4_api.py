"""Manage a Node4 account from code with the REST API.

    export NODE4_API_KEY='n4k_...'   # Account Settings -> API & Webhooks on https://node4.io
    python node4_api.py status
    python node4_api.py export proxies.txt          # host:port:user:pass, one per line
    python node4_api.py usage
    python node4_api.py whitelist                    # list whitelisted IPs
    python node4_api.py whitelist-add 198.51.100.7 "build server"
    python node4_api.py whitelist-remove 123         # by id from the list

Reference: https://node4.io/help/proxy-management-api (OpenAPI spec at https://node4.io/openapi.json).
Each call needs a matching permission on the key: read:proxies, read:usage, read:profile
(listing the whitelist) or write:ip-whitelist. The API allows 60 requests per minute per key,
and 300 per minute from one client IP across all keys. A 429 carries Retry-After in seconds.
More examples (purchases, gateway strings, sub-users, webhooks, IP replacement) are in this folder.
"""
import os
import sys
import time

import requests

BASE = "https://node4.io/api/v1"
KEY = os.environ.get("NODE4_API_KEY", "")
if not KEY:
    sys.exit("Set NODE4_API_KEY (create one under Account Settings -> API & Webhooks on node4.io).")

session = requests.Session()
session.headers["Authorization"] = f"Bearer {KEY}"


def call(method: str, path: str, **kwargs):
    r = session.request(method, BASE + path, timeout=30, **kwargs)
    if r.status_code == 429:
        # A rate-limited request never ran, so resending it once after Retry-After is safe.
        wait = int(r.headers.get("Retry-After") or 60)
        if wait > 120:
            sys.exit(f"Rate limited for {wait}s: {r.json().get('error')}")
        print(f"rate limited, waiting {wait}s", file=sys.stderr)
        time.sleep(wait)
        r = session.request(method, BASE + path, timeout=30, **kwargs)
    if not r.ok:
        sys.exit(f"{method} {path} -> HTTP {r.status_code}: {r.text[:300]}")
    return r


def status() -> None:
    d = call("GET", "/status").json()["data"]
    print(d["message"])
    bw = d.get("bandwidth") or {}
    if bw.get("limited") and bw.get("usedMb") is not None:
        print(f"bandwidth: {bw['usedMb']:.0f} of {bw['limitMb']:.0f} MB used")
    print("active proxies:", (d.get("proxies") or {}).get("active"))


def export(path: str) -> None:
    text = call("GET", "/proxies/list", params={"format": "txt"}).text
    with open(path, "w", newline="\n") as f:
        f.write(text + "\n")
    print(f"wrote {len(text.splitlines())} proxies to {path}")


def usage() -> None:
    bw = call("GET", "/usage", params={"limit": 1}).json()["data"]["bandwidth"]
    print(f"this month: {bw['totalFormatted']} in {bw['totalRequests']} requests")


def whitelist() -> None:
    ips = call("GET", "/ip-whitelist").json()["data"]["ips"]
    for ip in ips:
        print(ip.get("id"), ip.get("ipAddress"), ip.get("label") or "")
    print(f"{len(ips)} whitelisted")


def whitelist_add(ip: str, label: str | None = None) -> None:
    # Public IPv4 only: proxy endpoints are IPv4, so IPv6, private ranges and CIDR blocks are refused.
    d = call("POST", "/ip-whitelist", json={"ipAddress": ip, "label": label}).json()["data"]
    print("added", d.get("id"), d.get("ipAddress"))


def whitelist_remove(entry_id: str) -> None:
    call("DELETE", f"/ip-whitelist/{int(entry_id)}")
    print("removed", entry_id)


COMMANDS = {
    "status": status,
    "export": export,
    "usage": usage,
    "whitelist": whitelist,
    "whitelist-add": whitelist_add,
    "whitelist-remove": whitelist_remove,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]](*sys.argv[2:])
