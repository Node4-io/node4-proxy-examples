# Kotlin

Coroutines and OkHttp through a Node4 gateway: many requests with a hard cap on open connections, retries from a new exit, and sticky sessions. Needs JDK 17+ and Gradle 8.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
gradle run --args="rotate 20 10"    # 20 requests, at most 10 at once, a new exit per request
gradle run --args="sticky 3"        # 3 sessions in parallel, each holding its own exit
```

With Docker instead of a local JDK and Gradle (Git Bash on Windows: prefix with `MSYS_NO_PATHCONV=1`):

```sh
docker run --rm -v "$PWD:/w" -w /w -e NODE4_USER -e NODE4_PASS -e NODE4_GATEWAY \
  gradle:8.10-jdk21 gradle -q run --args="rotate 20 10"
```

Expected output, roughly:

```
20 requests, 0 failed, 20 distinct exits, 10 at once, 1763 ms
session gkxmu1ga -> 203.0.113.30, 203.0.113.30, 203.0.113.30 (1 distinct, expect 1)
```

| File | What it shows |
|---|---|
| `src/main/kotlin/ProxyClient.kt` | an OkHttp client for a gateway, a suspending `Call.await()`, and `fetch` with backoff that never retries a 407 |
| `src/main/kotlin/Main.kt` | `rotate`: bounded concurrency with a `Semaphore`; `sticky`: parallel sessions with `-session-ID` |

Keep the concurrency at or below your plan's limit: 10 on the free tier, your connection count on Rotating Unmetered. Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084`, `gw-residential.node4.io:8082` or a static `IP:4443` to use another product.

## Gotchas

- **HTTP/2 hides your concurrency from the gateway.** OkHttp multiplexes concurrent requests to one site over a single HTTP/2 connection: one tunnel, one exit. Without `protocols(listOf(Protocol.HTTP_1_1))`, `rotate 20 10` reported 1 distinct exit instead of 20. `proxyClient(..., keepAlive = false)` sets it, along with an empty connection pool.
- **OkHttp's own limit is 5 per host.** The default `Dispatcher` runs 5 async requests per target host and queues the rest, whatever your `Semaphore` allows. `proxyClient` raises `maxRequests` and `maxRequestsPerHost` to your concurrency.
- **407 is final.** The `proxyAuthenticator` returns `null` once it has already sent the login, so a rejected login fails at once (`Failed to authenticate with proxy` for `https://` targets) and `rotate` cancels every other request. 403, 429 and 5xx back off and retry on a new connection.
- **Underscore hostnames are fine here.** OkHttp resolves the proxy host itself and never builds a `java.net.URI` from it. The JDK `HttpClient` does, and fails; see [`../java/`](../java/).
- **Shut the client down** (`client.shutdown()` in `ProxyClient.kt`), or the JVM can sit waiting on OkHttp's idle threads before it exits.
