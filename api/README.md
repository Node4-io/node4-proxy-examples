# REST API and webhooks

Manage your Node4 account from scripts: check that proxies are serving, export your proxy list, read usage, manage the IP whitelist, buy plans and top-ups, build gateway proxy strings, run one capped login per client, replace failing static IPs and receive signed webhooks.

1. Create an API key under **Account Settings → API & Webhooks** on [node4.io](https://node4.io). Give it only the scopes the script needs; `write:orders` spends money, so give it to one key only.
2. Set it in the environment: `export NODE4_API_KEY='n4k_...'` (PowerShell: `$env:NODE4_API_KEY = 'n4k_...'`).

The new examples use only the Python standard library (3.8+) or Node.js 18+ built-ins; nothing to install. `node4_api.py` uses `requests`. They follow the published [API reference](https://node4.io/help/proxy-management-api) and [OpenAPI document](https://node4.io/openapi.json); the signature and retry logic is covered by offline tests. Everything that changes your account is opt-in: `buy_plan` needs `--yes`, `replace_unhealthy` needs `--replace`.

| Python | Node.js | What it does | Scopes |
|---|---|---|---|
| [`node4_api.py`](node4_api.py) | [`../powershell/api.ps1`](../powershell/api.ps1) | status, proxy list export, usage, IP whitelist | `read:proxies`, `read:usage`, `read:profile`, `write:ip-whitelist` |
| [`buy_plan.py`](buy_plan.py) | [`node/buy-plan.mjs`](node/buy-plan.mjs) | buy a plan or top-up with an `Idempotency-Key`, then poll `GET /orders/{id}` | `read:subscription`, `write:orders`, `read:orders` |
| [`gateway_strings.py`](gateway_strings.py) | [`node/gateway-strings.mjs`](node/gateway-strings.mjs) | rotating and residential proxy strings from `POST /gateways/endpoint` | `read:proxies` |
| [`sub_users.py`](sub_users.py) | [`node/sub-users.mjs`](node/sub-users.mjs) | one capped login per client: create, cap, disable, delete, usage | `read:proxies`, `write:credentials`, `read:usage` |
| [`replace_unhealthy.py`](replace_unhealthy.py) | [`node/replace-unhealthy.mjs`](node/replace-unhealthy.mjs) | static proxy health and probing; replaces a failing IP only with `--replace` | `read:proxies`, `write:proxies` |
| [`webhook_receiver.py`](webhook_receiver.py) | [`node/webhook-receiver.mjs`](node/webhook-receiver.mjs) | verifies signatures, rejects replays, deduplicates, handles events | none (uses the webhook secret) |
| [`node4client.py`](node4client.py) | [`node/node4client.mjs`](node/node4client.mjs) | the shared client: auth header, JSON envelope, safe retries | |

Every successful answer is `{ "success": true, "data": ... }`; errors are `{ "error": "..." }`, and the purchase endpoints add a machine-readable `code`. Send the key as `Authorization: Bearer n4k_...` (or `X-API-Key`). The API is for servers and scripts: it sends no CORS headers.

## Account basics

```sh
pip install requests
python node4_api.py status
python node4_api.py export proxies.txt
```

| Command | Scope | What it does |
|---|---|---|
| `status` | `read:proxies` | whether the account can make proxy requests right now, and why not if it can't |
| `export FILE` | `read:proxies` | writes `host:port:username:password`, one proxy per line |
| `usage` | `read:usage` | bandwidth and requests this month |
| `whitelist` | `read:profile` | lists whitelisted IPs |
| `whitelist-add IP [LABEL]` | `write:ip-whitelist` | whitelists a public IPv4 address |
| `whitelist-remove ID` | `write:ip-whitelist` | removes an entry by id |

The same calls with curl:

```sh
curl -H "Authorization: Bearer $NODE4_API_KEY" https://node4.io/api/v1/status
curl -H "Authorization: Bearer $NODE4_API_KEY" "https://node4.io/api/v1/proxies/list?format=txt"
curl -H "Authorization: Bearer $NODE4_API_KEY" -H "Content-Type: application/json" \
     -d '{"ipAddress":"198.51.100.7","label":"build server"}' https://node4.io/api/v1/ip-whitelist
```

`/proxies/list` also takes `format=csv`, and for `txt` a `fields` list and `separator` to match the order your tool expects, for example `?format=txt&fields=username,password,host,port&separator=:`. Whitelist entries must be single public IPv4 addresses; private ranges, IPv6 and CIDR blocks are refused. Guide: [getting started with the Node4 API](https://node4.io/help/getting-started-with-the-node4-api).

## Buying plans and top-ups

```sh
python buy_plan.py                                    # plans on sale
python buy_plan.py --plan dc-10 --payment card        # dry run
python buy_plan.py --plan dc-10 --payment card --yes  # buys, then polls the order
python buy_plan.py --topup topup_50gb --yes           # top-ups are paid with Bitcoin
python buy_plan.py --plan shared-25 --country IT_ES   # Premium and Shared plans take a country; IT_ES is Shared only
```

Nothing is bought without `--yes`. `POST /orders` and `POST /topups` require an `Idempotency-Key` header. The script generates one per purchase and prints it **before** sending. If the run is interrupted or times out, rerun the same command with `--idempotency-key <key>`: the server replays the first answer (`Idempotent-Replayed: true`) and does not charge again. Keys are remembered for 24 hours; the same key with a different body is `422 idempotency_key_reused`.

`card` charges the account's default saved card and usually comes back `delivered` at once. `bitcoin` returns a `checkoutUrl` to pay, applies any account credit, and the order stays `awaiting_payment` until the invoice is paid; the script polls `GET /orders/{id}` every 30 seconds until `provisioning.status` is `delivered`, `not_delivered` or `revoked`. `outcome_unknown`, `payment_unconfirmed`, `duplicate_recent_purchase` and `payment_held` mean the earlier purchase may have gone through: the script stops and tells you to check `GET /orders` instead of buying again. Subscribe to the `order.completed` webhook to avoid polling. Guide: [buying plans and top-ups with the API](https://node4.io/help/buying-plans-and-top-ups-with-the-api).

## Errors, rate limits and retries

Each key may make 60 requests per minute, and all requests from one client IP share 300 per minute across every key. Responses carry `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` (seconds from now) and the older `X-RateLimit-*` headers (`X-RateLimit-Reset` is a Unix timestamp). A `429` carries `Retry-After` in seconds.

[`node4client.py`](node4client.py) and [`node/node4client.mjs`](node/node4client.mjs) apply these rules, and the offline tests check each one:

| Answer | Retried? |
|---|---|
| `429` from the rate limiter (per key or per IP) | Yes, after `Retry-After`, for every method: the request was refused before it ran |
| `429` with `resetsAt` (IP replacement allowance used up) | No. `Retry-After` can be weeks; stop the job |
| `500`, `502`, `503`, a non-JSON error page or a dropped connection on a `GET` | Yes, exponential backoff with jitter |
| The same on `POST /orders` or `POST /topups` | Only with the **same** `Idempotency-Key` and body; not on a purchase `500` |
| `409 idempotency_in_flight` or `checkout_in_progress` on a purchase | Yes, same key, after a short wait |
| Any other write after a timeout or `5xx` (replace, create sub-user, create webhook) | No. Read the current state (`GET /proxies`, `GET /sub-users`, `GET /webhooks`) first |
| Any other `4xx` | No. Fix the request |

Guide: [API errors, rate limits and retries](https://node4.io/help/api-errors-rate-limits-and-retries).

## Gateway proxy strings

```sh
python gateway_strings.py                                     # products, ports, logins, targeting
python gateway_strings.py rotating_datacenter --country us
python gateway_strings.py residential --country us --state ny --count 20 --format hostport > sessions.txt
```

`POST /gateways/endpoint` returns `http://`, `socks5://` and `host:port:user:pass` forms, checked against your plan and the exits that exist. Products are `rotating_datacenter` (also accepted as `rotating_shared`), `rotating_unmetered` and `residential`. Rotating products take `country` only; `state`, `city` and `asn` are residential. `--count` (up to 100) gives each string its own sticky session for parallel workers. Without a session the gateway picks an exit per connection, not per request. Build strings once and reuse them. For Rotating Unmetered, `GET /connections/live` and `GET /connections/history` show open connections against your limit. Guide: [building proxy strings with the gateway API](https://node4.io/help/building-proxy-strings-with-the-gateway-api).

## Sub-users for clients

```sh
python sub_users.py create acme-corp --cap-gb 50
python sub_users.py list
python sub_users.py usage 412
python sub_users.py disable 412
python sub_users.py connect 412 residential --country us
```

Each sub-user is a separate proxy login with its own label, status and monthly cap (at least 1 GB, per UTC calendar month). It works on every product the account holds. Changes reach live traffic within about 2 minutes, and a client at full speed can go slightly past its cap. Writes are never retried automatically, because a retried create makes a second login. Guide: [managing sub-users for clients](https://node4.io/help/managing-sub-users-for-clients-with-the-api).

## IP replacement and proxy health

```sh
python replace_unhealthy.py             # report only
python replace_unhealthy.py --replace   # from cron, every 10 minutes or so
```

The script reads `GET /proxies/health`, probes each active static proxy through itself, and keeps a failure count in `proxy-health-state.json`. With `--replace` it calls `POST /proxies/{id}/replace` only after 3 failed runs in a row, never for a proxy Node4 has already queued (`replacementPending`), never twice within an hour, and at most once per run by default.

Replacements come from a monthly allowance set by the plan. **Shared Datacenter plans and the free tier include none**, and only some Premium Datacenter plans have more than zero. The script stops and asks for a person on `403` (no replacements on this plan), on `429` with `resetsAt` (used up until that date), or when `replacementsUsed` reaches `replacementLimit`. A replace that times out is not resent: the script checks `GET /proxies` to see whether the address changed. Guide: [automating IP replacement and proxy health](https://node4.io/help/automating-ip-replacement-and-proxy-health).

## Webhooks

```sh
export NODE4_WEBHOOK_SECRET='...'   # returned once by POST /webhooks; Copy secret in the dashboard shows it again
python webhook_receiver.py          # or: node node/webhook-receiver.mjs
```

Register an endpoint (scope `write:webhooks`), or use **Create Webhook** in the dashboard:

```sh
curl -X POST -H "Authorization: Bearer $NODE4_API_KEY" -H "Content-Type: application/json" \
  -d '{"name":"ops","url":"https://ops.example.com/hooks/node4","events":["usage.forecast_runout","usage.threshold_reached","order.completed","proxy.replaced","renewal.failed"]}' \
  https://node4.io/api/v1/webhooks
```

Each delivery is a POST with a JSON body `{ "id", "event", "data", "timestamp" }` and these headers:

| Header | Value |
|---|---|
| `X-Node4-Signature` | hex HMAC-SHA256 of the raw body, keyed with the webhook secret as a UTF-8 string |
| `X-Node4-Event` | the event name |
| `X-Node4-Event-Id` | the event id (`evt_...`), the same as `id` in the body and the same on every retry |
| `X-Node4-Delivery` | this attempt only; different on every retry, so never deduplicate on it |

The receivers verify the signature over the **raw** bytes before parsing (re-serialized JSON fails), compare in constant time, refuse a body whose `timestamp` (send time, epoch milliseconds) is more than 5 minutes from now, skip event ids they have already seen, answer `204` at once and do the work afterwards. Node4 waits up to 10 seconds; a `5xx`, a timeout or a dropped connection is retried (3 attempts in all), a `3xx` or `4xx` is final, and redirects are never followed. After 10 consecutive failed events the webhook is switched off until you turn it back on in the dashboard.

| Event | Sent when |
|---|---|
| `usage.forecast_runout` | at your recent pace a metered allowance is estimated to run out within 5 days and before renewal (`runOutAt`, `earliestAt`, `latestAt`); once per billing period, not while auto top-up can still top up |
| `usage.threshold_reached` | usage crossed 80% or 100% of the allowance (`threshold`) |
| `order.completed` | a paid order settled |
| `proxy.replaced` | a static proxy moved to a new IP (`reason` `manual`, `support` or `auto`); read new credentials from `GET /proxies` |
| `renewal.failed` | a renewal payment failed (`provider` `card`, `paypal` or `btcpay`; `serviceStatus`) |

`bandwidth_threshold.warning` / `.exceeded` fire for the same crossings as `usage.threshold_reached`; subscribe to one family, not both. The dashboard's **Send Test** posts a signed `bandwidth_threshold.warning` with `data.test: true`, which the receivers log and skip. Check a verifier by hand:

```sh
printf '%s' '{"id":"evt_test","event":"order.completed","data":{},"timestamp":0}' \
  | openssl dgst -sha256 -hmac "$NODE4_WEBHOOK_SECRET" -hex
```

Guide: [receiving Node4 webhooks](https://node4.io/help/receiving-node4-webhooks). Invoices, credit, auto top-up and usage alert switches: [automating billing with the API](https://node4.io/help/automating-billing-with-the-api).

## Tests

Offline, no key or network needed; CI runs both:

```sh
python -m unittest -v test_api_examples.py
cd node && node --test node4client.test.mjs webhook-receiver.test.mjs
```

## Reference

- Public API reference: [node4.io/help/proxy-management-api](https://node4.io/help/proxy-management-api)
- OpenAPI 3.1 document with every endpoint, scope and webhook payload: [node4.io/openapi.json](https://node4.io/openapi.json)
- In-dashboard API docs (signed in): [node4.io/api-docs](https://node4.io/api-docs)
- Keeping keys safe: [API key security](https://node4.io/help/api-key-security)
