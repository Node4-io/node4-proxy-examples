"""Buy a Node4 plan (or a top-up) safely: one Idempotency-Key per purchase, then poll the order.

    export NODE4_API_KEY='n4k_...'
    python buy_plan.py                                        # list plans on sale (read:subscription)
    python buy_plan.py --plan dc-10 --payment card            # dry run: shows what would be bought
    python buy_plan.py --plan dc-10 --payment card --yes      # buys (write:orders), then polls
    python buy_plan.py --topup topup_50gb --yes               # bandwidth top-up, paid with Bitcoin
    python buy_plan.py --plan shared-25 --country IT_ES       # Shared plan split between Italy and Spain (dry run)
    python buy_plan.py --order 9301                           # poll an existing order (read:orders)

Nothing is bought without --yes. Before the purchase is sent, the script prints its
Idempotency-Key. If the run is interrupted or times out, rerun the SAME command with
--idempotency-key <that key>: the server replays the first answer and never charges twice.
Never retry a purchase with a new key until GET /orders shows it did not go through.

Guide: https://node4.io/help/buying-plans-and-top-ups-with-the-api
"""
import argparse
import sys
import time
import uuid

from node4client import Node4Client, Node4Error

FINAL_STATES = ("delivered", "not_delivered", "revoked")
# Answers that mean "the earlier purchase may have gone through: look, do not buy again".
STOP_CODES = ("outcome_unknown", "payment_unconfirmed", "duplicate_recent_purchase", "payment_held")


def list_plans(node4):
    for p in node4.get("/plans")["plans"]:
        countries = ",".join(c["code"] for c in p.get("countries") or [])
        print(f"{p['id']:>6}  {p['slug']:<24} {p['name']:<36} {p['billingCycle']}"
              + (f"  countries: {countries}" if countries else ""))


def find_plan(node4, wanted):
    for p in node4.get("/plans")["plans"]:
        if wanted in (p["slug"], str(p["id"])):
            return p
    sys.exit(f"No plan on sale matches {wanted!r}. Run without arguments to list them.")


def wait_for_order(node4, order_id, interval, max_wait):
    deadline = time.time() + max_wait
    last = None
    while True:
        order = node4.get(f"/orders/{order_id}")["order"]
        state = order["provisioning"]["status"]
        if state != last:
            print(f"order {order_id}: {state}" + (f" ({order['provisioning']['message']})"
                                                  if order["provisioning"].get("message") else ""))
            last = state
        if state in FINAL_STATES:
            return order
        if time.time() > deadline:
            sys.exit(f"Still {state} after {max_wait}s. Check again later with --order {order_id}.")
        time.sleep(interval)  # 30 s keeps polling far inside the 60/min key limit


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", help="plan slug or id from the plan list")
    ap.add_argument("--topup", help="add-on id such as topup_50gb or ip_5 (Bitcoin only)")
    ap.add_argument("--payment", choices=("card", "bitcoin"), default="bitcoin")
    ap.add_argument("--country", help="for plans with countrySelectable: a code from the plan's countries list, such as US, IT or ES (Shared plans also offer IT_ES, an even Italy/Spain split)")
    ap.add_argument("--discount-code")
    ap.add_argument("--idempotency-key", help="resend an interrupted purchase with its original key")
    ap.add_argument("--order", type=int, help="only poll this order id")
    ap.add_argument("--interval", type=int, default=30)
    ap.add_argument("--max-wait", type=int, default=1800)
    ap.add_argument("--yes", action="store_true", help="really buy (spends money)")
    a = ap.parse_args()

    node4 = Node4Client()
    if a.order:
        order = wait_for_order(node4, a.order, a.interval, a.max_wait)
        print("delivered:", order.get("delivered"))
        return
    if not a.plan and not a.topup:
        list_plans(node4)
        return

    if a.topup:
        path, body = "/topups", {"addonId": a.topup, "paymentMethod": "bitcoin"}
        what = f"top-up {a.topup} (Bitcoin)"
    else:
        plan = find_plan(node4, a.plan)
        path, body = "/orders", {"planId": plan["id"], "paymentMethod": a.payment}
        if a.country:
            body["country"] = a.country
        what = f"{plan['name']} (plan {plan['id']}) by {a.payment}"
    if a.discount_code:
        body["discountCode"] = a.discount_code

    if not a.yes:
        print(f"Dry run. Would POST {path} {body}: {what}. Add --yes to buy.")
        return

    key = a.idempotency_key or str(uuid.uuid4())
    print(f"Idempotency-Key: {key}  (if interrupted, rerun with --idempotency-key {key})", flush=True)
    try:
        data = node4.post(path, body, idempotency_key=key)
    except Node4Error as e:
        print(e, file=sys.stderr)
        if e.code in STOP_CODES:
            order_id = e.body.get("orderId")
            sys.exit("Stop: check GET /orders" + (f"/{order_id}" if order_id else "")
                     + " before buying again, and never switch to a new key for this purchase."
                     + (f" Pay at {e.body['checkoutUrl']}" if e.body.get("checkoutUrl") else ""))
        if e.status is None or (e.status or 0) >= 500:
            sys.exit(f"Outcome unclear. Rerun with --idempotency-key {key} (same body) or check GET /orders.")
        sys.exit("Nothing was charged. Fix the cause, then buy again (a new key is generated).")

    order = data["order"]
    if data.get("checkoutUrl"):
        print("Pay this Bitcoin invoice:", data["checkoutUrl"])
    order = wait_for_order(node4, order["id"], a.interval, a.max_wait)
    print("delivered:", order.get("delivered"))


if __name__ == "__main__":
    main()
