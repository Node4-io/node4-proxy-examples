# Patterns

Short answers to the questions that come up once the first request works.

## Static or rotating?

| You need | Use |
|---|---|
| The same IP every time: logins, a partner API that whitelists your IP, a fixed set of addresses you manage | **Static** datacenter proxies (dedicated, or shared at a lower price per IP) |
| A different IP per connection without managing a list | **Rotating** gateway |
| A rotating IP held for a short flow | Rotating gateway with `-session-ID` in the username |
| Targets that refuse datacenter IP ranges, or countries outside the US, Italy and Spain | **Residential** |

Not sure whether a target accepts datacenter addresses? [Block replay](https://node4.io/tools/block-replay) fetches a URL from both kinds of address and compares the answers.

## Rotation is per connection

The gateway picks an exit when a connection opens: each HTTPS `CONNECT` tunnel, each SOCKS5 connection, and each plain-HTTP request. Every request sent down an open tunnel leaves from the same exit, and HTTP clients keep tunnels open by default.

- More exits: disable keep-alive or create a new client per request (`python/rotate_per_request.py`, `node/rotate-per-request.mjs`, `go -fresh`).
- Fewer exits: reuse one client, or add `-session-ID` to hold an exit across connections.
- A new exit can repeat an address you had earlier.

## Sizing concurrency

On **Rotating Unmetered** you buy a number of connections that can be open at once. When that many are open, the next one is refused and the open ones keep running. A tunnel holds its slot for as long as your client keeps it open, so:

1. Count connections, not requests per second. A pool of 50 keep-alive connections uses 50 slots even when idle.
2. Cap your client at your plan's count (`CONCURRENCY` in `python/async_aiohttp.py`, `-workers` in `go/`, `CONCURRENT_REQUESTS` in Scrapy).
3. Close idle connections you no longer need.

On per-GB plans (Rotating Datacenter, residential) concurrency is not billed; data is. The [proxy calculator](https://node4.io/tools/proxy-calculator) compares the two from your own volume and response sizes.

## Retries

- `403` or `429` from the target: back off, then retry on a **new connection** so the retry can leave from a different exit (`python/retries.py`). Retrying down the same tunnel retries from the same IP.
- `407` from the proxy: wrong username or password, or the plan does not include that product or port. Retrying will not help. See [fixing 407](https://node4.io/help/fixing-407-proxy-authentication-required).
- Timeouts: retry with backoff; if one static IP keeps timing out, check it with `python/check_static_proxies.py` and refresh it from the dashboard.

## Credentials in code

- Read credentials from the environment, as every example here does. Never commit them.
- Percent-encode the username and password when building a proxy URL; a password containing `@`, `:` or `/` otherwise breaks the URL.
- On a server with a fixed IP, [IP whitelisting](https://node4.io/help/authentication) removes credentials from your code entirely: connections from a whitelisted IP need no username or password.
