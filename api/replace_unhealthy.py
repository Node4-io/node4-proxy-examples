"""Watch static proxy health and replace addresses that have really failed, within your allowance.

    export NODE4_API_KEY='n4k_...'     # read:proxies, plus write:proxies for --replace
    python replace_unhealthy.py                 # report: Node4 health + a probe through each proxy
    python replace_unhealthy.py --replace       # also replace after 3 failed runs in a row (cron it)

Safe by default: without --replace nothing is changed. With it, a proxy is replaced only when
it has failed THRESHOLD consecutive runs, is not already queued for replacement by Node4, and
was not replaced in the last hour; at most --max-replacements per run.

The script stops as soon as the allowance is used:
- 403 "Your plan does not include IP replacements": the free tier and Shared Datacenter plans
  have no replacements, and some Premium Datacenter plans have 0. Nothing to automate.
- 429 with resetsAt: this month's replacements are used up (Retry-After can be weeks).
- replacementsUsed reaching replacementLimit in a successful answer.

A replace is never retried blindly: after a timeout the script reads GET /proxies to see
whether the address changed. The probe target is https://api.ipify.org; add your own.
Guide: https://node4.io/help/automating-ip-replacement-and-proxy-health
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

from node4client import Node4Client, Node4Error

STATE = pathlib.Path("proxy-health-state.json")
PROBE_URL = "https://api.ipify.org"


def probe(p, timeout=15):
    """True when an HTTPS request through this proxy succeeds."""
    auth = f"{urllib.parse.quote(p['username'], safe='')}:{urllib.parse.quote(p['password'], safe='')}"
    proxy = f"http://{auth}@{p['host']}:{p['port']}"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    try:
        with opener.open(PROBE_URL, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def host_changed(node4, proxy_id, old_host):
    for p in node4.get("/proxies")["proxies"]:
        if p["id"] == proxy_id:
            return p["host"] != old_host
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--replace", action="store_true", help="really replace failing proxies")
    ap.add_argument("--threshold", type=int, default=3, help="consecutive failed runs before replacing")
    ap.add_argument("--max-replacements", type=int, default=1, help="per run")
    a = ap.parse_args()

    node4 = Node4Client()
    state = json.loads(STATE.read_text()) if STATE.exists() else {"failures": {}, "replacedAt": {}}
    proxies = {p["id"]: p for p in node4.get("/proxies")["proxies"]}
    health = node4.get("/proxies/health")["proxies"]
    replaced = 0

    for h in health:
        pid, key = h["proxyId"], str(h["proxyId"])
        p = proxies.get(pid)
        if not p or p["status"] != "active" or p.get("protocol") != "http":
            continue
        ok = probe(p)
        state["failures"][key] = 0 if ok else state["failures"].get(key, 0) + 1
        fails = state["failures"][key]
        note = "queued by Node4" if h["replacementPending"] else ""
        print(f"{pid:>7} {h['host']:<16} node4:{'ok' if h['isHealthy'] else 'FAIL':<5}"
              f" probe:{'ok' if ok else 'FAIL':<5} failed runs:{fails} {note}")

        if ok or not a.replace or fails < a.threshold or h["replacementPending"]:
            continue
        if time.time() - state["replacedAt"].get(key, 0) < 3600 or replaced >= a.max_replacements:
            continue

        try:
            d = node4.post(f"/proxies/{pid}/replace")
        except Node4Error as e:
            if e.status is None:
                # No answer: it may have happened. Look, do not resend.
                print(f"{pid}: no answer; " + ("it was replaced." if host_changed(node4, pid, p["host"])
                                               else "not replaced. It will be tried on a later run."))
                continue
            if e.status == 403:
                print("Stop: this plan includes no IP replacements. Alert a person.", file=sys.stderr)
                break
            if e.status == 429 and "resetsAt" in e.body:
                print(f"Stop: replacements used up until {e.body['resetsAt']}. Alert a person.", file=sys.stderr)
                break
            print(f"{pid}: {e}")  # 409 not active / in progress, 503 unavailable (nothing used)
            continue

        replaced += 1
        state["failures"].pop(key, None)
        state["replacedAt"][key] = time.time()
        print(f"{pid}: {d['oldIp']} -> {d['newIp']}:{d['newPort']}"
              f" ({d['replacementsUsed']}/{d['replacementLimit']} used this month)")
        print("  New credentials are in this answer and in GET /proxies; update your workers.")
        if d["replacementsUsed"] is not None and d["replacementsUsed"] >= d["replacementLimit"]:
            print("Stop: that was the last replacement this month. Alert a person.", file=sys.stderr)
            break

    STATE.write_text(json.dumps(state))


if __name__ == "__main__":
    main()
