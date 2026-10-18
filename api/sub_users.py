"""Give each client its own capped proxy login (a sub-user) and read its usage for invoicing.

    export NODE4_API_KEY='n4k_...'
    python sub_users.py list                          # read:proxies
    python sub_users.py create acme-corp --cap-gb 50  # write:credentials; prints the login once
    python sub_users.py usage 412                     # read:usage, this UTC month
    python sub_users.py cap 412 100                   # raise the monthly cap to 100 GB ("none" removes it)
    python sub_users.py disable 412                   # keeps the login and its counter
    python sub_users.py enable 412
    python sub_users.py delete 412 --permanent        # frees the slot for good
    python sub_users.py connect 412 residential --country us   # gateway string for that client

Writes are sent once and never retried automatically: a retried create can make a second
login. If a write times out, run `list` to see whether it happened.
Changes reach live traffic within about 2 minutes, and a cap can overrun slightly.
Guide: https://node4.io/help/managing-sub-users-for-clients-with-the-api
"""
import argparse
import sys

from node4client import Node4Client, Node4Error

GB = 1024  # the API counts in MB


def fmt_cap(mb):
    return "no cap" if mb is None else f"{mb / GB:.0f} GB"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("create")
    c.add_argument("label")
    c.add_argument("--cap-gb", type=int, help="monthly cap in GB, at least 1")
    for name in ("usage", "disable", "enable"):
        sub.add_parser(name).add_argument("id", type=int)
    cap = sub.add_parser("cap")
    cap.add_argument("id", type=int)
    cap.add_argument("gb", help='whole GB, or "none"')
    d = sub.add_parser("delete")
    d.add_argument("id", type=int)
    d.add_argument("--permanent", action="store_true")
    cn = sub.add_parser("connect")
    cn.add_argument("id", type=int)
    cn.add_argument("product")
    cn.add_argument("--country")
    a = ap.parse_args()

    node4 = Node4Client()
    try:
        if a.cmd == "list":
            data = node4.get("/sub-users")
            plan = data["plan"]
            print(f"{plan['used']} of {plan['maxSubUsers']} sub-users, {plan['active']} active")
            for s in data["subUsers"]:
                used = s["usage"]["bandwidthUsedMb"] or 0
                print(f"{s['id']:>6}  {(s['label'] or s['username']):<24} {s['status']:<10}"
                      f" {used / GB:>8.2f} GB / {fmt_cap(s['limits']['bandwidthLimitMb'])}")
        elif a.cmd == "create":
            body = {"label": a.label, "bandwidthLimitMb": a.cap_gb * GB if a.cap_gb else None}
            s = node4.post("/sub-users", body)
            print(f"created {s['id']}: {s['username']} / {s['password']}  ({fmt_cap(s['limits']['bandwidthLimitMb'])})")
            print("Store the password now; send it to the client over a private channel.")
        elif a.cmd == "usage":
            p = node4.get(f"/sub-users/{a.id}/usage")["period"]
            print(f"{p['start'][:10]} to {p['end'][:10]}: {p['bandwidthUsedMb'] / GB:.2f} GB"
                  f" of {fmt_cap(p['bandwidthLimitMb'])}")
        elif a.cmd == "cap":
            mb = None if a.gb.lower() == "none" else int(a.gb) * GB
            s = node4.patch(f"/sub-users/{a.id}", {"bandwidthLimitMb": mb})
            print(f"{s['id']}: cap {fmt_cap((s.get('limits') or {}).get('bandwidthLimitMb'))}, status {s.get('status')}")
        elif a.cmd in ("disable", "enable"):
            s = node4.patch(f"/sub-users/{a.id}", {"status": "disabled" if a.cmd == "disable" else "active"})
            print(f"{s['id']}: {s.get('status')}")
        elif a.cmd == "delete":
            r = node4.delete(f"/sub-users/{a.id}", permanent="true" if a.permanent else None)
            print(r)
        elif a.cmd == "connect":
            body = {"product": a.product, "credentialId": a.id}
            if a.country:
                body["country"] = a.country
            print(node4.post("/gateways/endpoint", body)["url"])
    except Node4Error as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
