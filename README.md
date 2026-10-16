# Node4 proxy examples

Working code for using [Node4](https://node4.io) proxies from curl, Python, Node.js, Go and Scrapy: HTTP and SOCKS5, sticky sessions, rotation, retries and concurrency. Every example reads its credentials from environment variables and runs as-is.

Node4 sells dedicated and shared datacenter proxies on IP blocks it owns in the United States, Italy and Spain, rotating datacenter gateways (billed per GB, or by concurrent connections with no data cap), and residential proxies in 170+ countries. There is a free tier with no card required. Prices are on [node4.io/pricing](https://node4.io/pricing).

## Try it in 30 seconds

[Sign up](https://node4.io/sign-up), then copy your username and password from the **Proxies** page.

On the **free tier** you get 3 static shared proxies over HTTP(S). Test one of them (the IP is on your Proxies page):

```sh
export NODE4_USER='your-username'
export NODE4_PASS='your-password'
curl -sS -U "$NODE4_USER:$NODE4_PASS" -x http://YOUR-PROXY-IP:4443 https://api.ipify.org
```

With a **rotating plan**, use the gateway instead. Each new connection can leave from a different IP:

```sh
curl -sS -U "$NODE4_USER:$NODE4_PASS" -x http://gw-rotating_datacenter.node4.io:8083 https://api.ipify.org
```

On Windows PowerShell, set the variables with `$env:NODE4_USER = 'your-username'` and `$env:NODE4_PASS = 'your-password'`.

## Endpoints

The **port selects the product**. The username and password are the same for every product on your account.

| Product | HTTP | SOCKS5 |
|---|---|---|
| Dedicated or shared datacenter (static) | `IP:4443` | `IP:1443` |
| Rotating Datacenter (per GB) | `gw-rotating_datacenter.node4.io:8083` | `gw-rotating_datacenter.node4.io:1083` |
| Rotating Unmetered (per connection, no data cap) | `gw-rotating_unmetered.node4.io:8084` | `gw-rotating_unmetered.node4.io:1084` |
| Residential | `gw-residential.node4.io:8082` | `gw-residential.node4.io:1082` |

Static proxies are individual IPs listed on your **Proxies** page. Traffic leaves from the exact IP you connect to. SOCKS5 is on paid plans; the free tier is HTTP(S) only.

Use `socks5h://` (not `socks5://`) so hostnames are resolved by the proxy, not your machine.

## Options in the username

Rotating and residential gateways read options from the **username**. The host and port do not change.

| Goal | Username | Applies to |
|---|---|---|
| Hold one exit IP (sticky session) | `USER-session-abc123` | rotating (up to 30 min from first use), residential (best effort, up to 30 min) |
| Pick a country | `USER-country-us` | rotating (countries the pool has: us, it, es), residential (170+) |
| Country and state, city or ASN | `USER-country-us-state-tx`, `USER-country-us-city-losangeles`, `USER-country-de-asn-3320` | residential |

Session IDs are up to 32 letters and digits that you choose. A new ID gives you a new exit.

## How rotation actually works

Rotation happens **per connection, not per request**. An HTTPS request travels inside a `CONNECT` tunnel, and every request sent down that tunnel leaves from the same IP. Modern HTTP clients keep connections alive by default, so a script that makes 100 requests through one client may use only a handful of exit IPs.

- Want a new IP for each request? Open a new connection each time (see `python/rotate_per_request.py` and `node/rotate-per-request.mjs`).
- Want one IP for a short flow? Reuse one connection, or add a `-session-` ID to hold it across connections.

More detail: [IP rotation guide](https://node4.io/help/ip-rotation-guide).

## What is in here

| Folder | Contents |
|---|---|
| [`curl/`](curl/) | HTTP, SOCKS5, sticky sessions, targeting, checking your exit IP |
| [`python/`](python/) | requests, httpx, aiohttp, SOCKS5, sticky sessions, per-request rotation, retries, a static proxy checker |
| [`node/`](node/) | fetch/undici, axios, SOCKS5, Puppeteer, Playwright |
| [`go/`](go/) | net/http with a proxy and a concurrent worker pool |
| [`scrapy/`](scrapy/) | a minimal spider and settings that route every request through Node4 |
| [`patterns/`](patterns/) | sizing concurrency, sticky vs rotating, retry and backoff |

## Environment variables

| Variable | Used by | Example |
|---|---|---|
| `NODE4_USER`, `NODE4_PASS` | everything | from your Proxies page |
| `NODE4_GATEWAY` | rotating and residential examples | `gw-rotating_datacenter.node4.io:8083` (default) |
| `NODE4_PROXY` | static examples | `203.0.113.10:4443` |

Concurrency defaults in the examples stay at or below 10 connections, the free tier's limit. On Rotating Unmetered, raise them to your plan's connection count.

Copy `.env.example` to `.env` if you prefer a file. Never commit real credentials.

## Hostnames with underscores

The gateway hostnames contain an underscore (`gw-rotating_datacenter`). curl, Python, Node.js, Go and browsers accept them. A few strict parsers do not (Java's `java.net.URI`, some SOCKS libraries). If yours rejects the name, resolve it first and connect to the IP with the same port.

## Help

- Setup guides: [node4.io/help](https://node4.io/help)
- Which product fits your job: [choosing the right proxy type](https://node4.io/help/choosing-the-right-proxy-type)
- Getting `407 Proxy Authentication Required`: [fixing 407](https://node4.io/help/fixing-407-proxy-authentication-required)
- REST API for managing proxies: [API reference](https://node4.io/help/proxy-management-api)
- Support: support@node4.io

Issues and pull requests for new languages and libraries are welcome.

## License

MIT. See [LICENSE](LICENSE).
