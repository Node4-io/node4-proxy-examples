# Java: OkHttp

OkHttp 4 through a Node4 gateway: one request, rotation, a sticky session, and SOCKS5. Needs JDK 17+ and Maven.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
mvn -q compile exec:java                      # HTTP proxy
mvn -q exec:java -Dexec.args=socks            # SOCKS5 (paid plans)
```

With Docker instead of a local JDK and Maven (Git Bash on Windows: prefix with `MSYS_NO_PATHCONV=1`):

```sh
docker run --rm -v "$PWD:/w" -w /w -e NODE4_USER -e NODE4_PASS -e NODE4_GATEWAY \
  maven:3-eclipse-temurin-21 mvn -q compile exec:java
```

Expected output, roughly:

```
one request        -> 203.0.113.41
shared client, 5   -> 1 distinct exit(s)
no pool, 5         -> 5 distinct exit(s)
session c8c0425f, 3 -> 1 distinct exit(s) (expect 1)
```

## Notes

- OkHttp resolves the proxy host itself, so the underscore in `gw-rotating_datacenter` is fine, and `proxyAuthenticator` is asked before the `CONNECT` is sent, so none of the JDK `HttpClient` workarounds in [`../README.md`](../README.md) apply.
- Return `null` from `proxyAuthenticator` when the request already carried `Proxy-Authorization`. Otherwise OkHttp keeps re-sending a rejected login. For `https://` targets a 407 then surfaces as `IOException: Failed to authenticate with proxy`.
- A shared `OkHttpClient` pools connections, so it keeps one exit. `new ConnectionPool(0, ...)` closes each tunnel after use. Also limit the client to `Protocol.HTTP_1_1` when requests run in parallel: over HTTP/2, OkHttp multiplexes concurrent requests to one site onto a single connection, which is one tunnel and one exit.
- SOCKS5 uses `Proxy.Type.SOCKS` with an unresolved address (the proxy resolves hostnames) and takes the login from `java.net.Authenticator.setDefault`.
- OkHttp's dispatcher allows 5 concurrent async requests per host by default. If you use `enqueue` to go wider, raise `maxRequestsPerHost` (see [`../../kotlin/`](../../kotlin/)).
