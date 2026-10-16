# PHP

Plain `ext-curl` examples (PHP 8.1+), plus one with Guzzle.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
php basic.php
php rotate_per_request.php
composer install && php guzzle.php
```

No PHP installed? Run it in Docker:

```sh
docker run --rm -e NODE4_USER -e NODE4_PASS -v "$PWD:/app" -w /app php:8.3-cli php basic.php
docker run --rm -v "$PWD:/app" -w /app composer:2 install     # once, for guzzle.php
```

| File | What it shows |
|---|---|
| `basic.php` | one request through the rotating gateway with `CURLOPT_PROXY` |
| `static.php` | one request through a static proxy (`NODE4_PROXY=IP:4443`), and a check that it left from that IP |
| `socks5.php` | SOCKS5 with `CURLPROXY_SOCKS5_HOSTNAME` (paid plans) |
| `sticky_session.php` | one exit IP across several connections with `-session-ID` |
| `rotate_per_request.php` | a reused handle keeps one exit; `CURLOPT_FRESH_CONNECT` + `CURLOPT_FORBID_REUSE` gets a new one per request |
| `concurrent.php` | `curl_multi` with a cap on transfers in flight, backoff that retries on a new connection, stop on 407 |
| `guzzle.php` | Guzzle over HTTP, with a sticky session, and over SOCKS5 |
| `_env.php` | reads the environment, builds proxied curl handles, detects 407 |

Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084` or `gw-residential.node4.io:8082` to run the same examples on another product.

## Gotchas

- **Rotation is per connection.** A curl handle (and Guzzle's client) keeps its connection for the next request, so the requests leave from one exit. `rotate_per_request.php` prints 1 distinct exit for the reused handle and 5 with `CURLOPT_FRESH_CONNECT` and `CURLOPT_FORBID_REUSE`.
- **Detecting 407.** For an `https://` target the 407 is the answer to CONNECT: `curl_exec` fails and `CURLINFO_HTTP_CONNECTCODE` is 407, while `CURLINFO_RESPONSE_CODE` may be 0. Check both (`is_407()` in `_env.php`). Do not retry a 407.
- **Use `CURLPROXY_SOCKS5_HOSTNAME`**, not `CURLPROXY_SOCKS5`, so the proxy resolves the target name. In Guzzle the same thing is a `socks5h://` proxy URL. A SOCKS5 server has no 407: a wrong password fails with `cannot complete SOCKS5 connection ... (2)`.
- **Credentials:** `CURLOPT_PROXYUSERNAME` and `CURLOPT_PROXYPASSWORD` take the values as-is. Guzzle takes a proxy URL, so `rawurlencode()` both parts, as `guzzle.php` does.
- **Underscore hostnames work** with ext-curl and Guzzle (tested with curl 8.14). If an old libcurl refuses the name, resolve it with `gethostbyname()` and use the IP with the same port.
- **Concurrency:** `php concurrent.php 40 10` sends 40 requests, 10 at a time. Keep the second number at or below 10 on the free tier, or your plan's connection count on Rotating Unmetered.
