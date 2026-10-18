"""Build ready-to-use gateway proxy strings with the API, instead of assembling usernames by hand.

    export NODE4_API_KEY='n4k_...'          # needs read:proxies
    python gateway_strings.py                                    # your gateway products and logins
    python gateway_strings.py rotating_datacenter --country us   # one rotating string
    python gateway_strings.py residential --country us --state ny --count 5 --format hostport > sessions.txt
    python gateway_strings.py rotating_unmetered --sticky --protocol socks5

Products: rotating_datacenter (alias of rotating_shared), rotating_unmetered, residential.
Rotating products take --country only; --state, --city and --asn are residential.
--count N (up to 100) returns N strings, each with its own sticky session.

Build the strings once and reuse them: they stay valid as long as the login does.
Output contains passwords, so treat it like a credentials file.
Guide: https://node4.io/help/building-proxy-strings-with-the-gateway-api
"""
import argparse
import sys

from node4client import Node4Client, Node4Error

FORMATS = {"url": "url", "http": "http", "socks5": "socks5", "hostport": "hostPortUserPass"}


def show_gateways(node4):
    for g in node4.get("/gateways")["gateways"]:
        t = ", ".join(k for k, v in g["targeting"].items() if v)
        print(f"{g['product']:<20} {g['host']}  http {g['ports']['http']}  socks5 {g['ports']['socks5']}"
              f"  targeting: {t or 'none'}"
              + (f"  connection limit: {g['connectionLimit']}" if g.get("connectionLimit") else ""))
        for u in g["usernames"]:
            print(f"    {u['username']:<32} {u['status']:<10} {u.get('label') or ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("product", nargs="?")
    ap.add_argument("--protocol", choices=("http", "socks5"))
    ap.add_argument("--country")
    ap.add_argument("--state")
    ap.add_argument("--city", help="lowercase, no separators: losangeles")
    ap.add_argument("--asn", type=int)
    ap.add_argument("--session", help="your own sticky session id, 1-32 letters and digits")
    ap.add_argument("--sticky", action="store_true", help="let the API mint a session id")
    ap.add_argument("--count", type=int)
    ap.add_argument("--credential-id", type=int, help="build with this login or sub-user")
    ap.add_argument("--format", choices=sorted(FORMATS), default="url")
    a = ap.parse_args()

    node4 = Node4Client()
    if not a.product:
        show_gateways(node4)
        return

    body = {"product": a.product, "protocol": a.protocol, "country": a.country, "state": a.state,
            "city": a.city, "asn": a.asn, "session": a.session, "count": a.count,
            "credentialId": a.credential_id, "sticky": True if a.sticky else None}
    body = {k: v for k, v in body.items() if v is not None}
    try:
        d = node4.post("/gateways/endpoint", body)
    except Node4Error as e:
        # 400 names the bad option, 422 lists the locations that exist, 404/409 point at the login.
        sys.exit(str(e))

    field = FORMATS[a.format]
    for e in d.get("endpoints") or [d]:
        print(e[field])
    sticky = d.get("sticky") or {}
    print(f"# {d['name']}, rotation {d['rotation']}, sticky "
          + (f"up to {sticky.get('maxSeconds')}s" if sticky.get("enabled") else "off"), file=sys.stderr)


if __name__ == "__main__":
    main()
