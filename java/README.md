# Java

Single-file programs using only the JDK (`java.net.http.HttpClient`, `HttpURLConnection`), plus an OkHttp project in [`okhttp/`](okhttp/). JDK 21 or newer.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
java BasicHttpClient.java
java ConcurrentFetcher.java 40 10
```

No JDK installed? Run any of them with Docker (Git Bash on Windows: prefix with `MSYS_NO_PATHCONV=1`):

```sh
docker run --rm -v "$PWD:/w" -w /w -e NODE4_USER -e NODE4_PASS -e NODE4_GATEWAY -e NODE4_PROXY \
  eclipse-temurin:21 java BasicHttpClient.java
```

| File | What it shows |
|---|---|
| `BasicHttpClient.java` | one request through the rotating gateway, with the three settings HttpClient needs (below) |
| `StaticProxy.java` | a static proxy (`NODE4_PROXY=IP:4443`), checking traffic leaves from that IP |
| `StickySession.java` | one exit IP across several connections with `-session-ID` |
| `RotatePerConnection.java` | a reused `HttpClient` keeps one exit; a new client per request gets a new one |
| `Socks5.java` | SOCKS5 with `java.net.Proxy` and `HttpURLConnection` (paid plans) |
| `ConcurrentFetcher.java` | a bounded worker pool, backoff that retries from a new exit, no retry on 407 |
| `okhttp/` | OkHttp: `proxyAuthenticator`, rotation, sticky session, SOCKS5 (`mvn -q compile exec:java`) |

`ConcurrentFetcher.java [requests] [workers] [reuse]` defaults to 40 requests on 10 workers, each request on its own connection. Add `reuse` to keep one tunnel per worker. Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084`, `gw-residential.node4.io:8082` or a static `IP:4443` to run the same examples on another product.

## Gotchas

**1. Basic proxy auth is disabled for HTTPS by default.** HTTPS goes through a `CONNECT` tunnel, and the JDK ships with `jdk.http.auth.tunneling.disabledSchemes=Basic`. Every `https://` request then fails with a 407, and `HttpClient` does not even call your `Authenticator`. Clear the property before the first client is built, or on the command line:

```sh
java -Djdk.http.auth.tunneling.disabledSchemes= BasicHttpClient.java
```

The examples call `System.setProperty(...)` at the top of `main`. It applies to `HttpURLConnection` too.

**2. The gateway hostname has an underscore.** `java.net.URI` rejects `gw-rotating_datacenter.node4.io` (`getHost()` returns `null`). Passing the name in an `InetSocketAddress` is not enough: `HttpClient` builds a URI from the proxy host when it answers the 407 challenge, and fails with `URISyntaxException: Illegal character in hostname`. Resolve the gateway and pass the IP as a string:

```java
InetAddress ip = InetAddress.getByName("gw-rotating_datacenter.node4.io");
ProxySelector.of(new InetSocketAddress(ip.getHostAddress(), 8083));
```

`new InetSocketAddress(InetAddress, port)` still carries the hostname and fails the same way. Static proxies are plain IPs and are not affected. SOCKS (`Socks5.java`) and OkHttp accept the hostname as-is.

**3. The JDK re-sends rejected credentials.** On a 407 `HttpClient` asks the `Authenticator` again, up to 3 more times. A 407 means wrong credentials or a product your plan does not include, so retrying only adds failed logins. The examples set `jdk.httpclient.auth.retrylimit=0`; a rejected login then surfaces as `IOException: too many authentication attempts`, which they report as a 407.

**4. `HttpClient` ignores SOCKS proxies.** Give it a `ProxySelector` that returns a `Proxy.Type.SOCKS` proxy and it connects **directly**, from your own IP, with no error. Use `HttpURLConnection` or a `Socket` with `new Proxy(Proxy.Type.SOCKS, ...)`, or OkHttp. The SOCKS5 login comes from the default `Authenticator` (protocol `"SOCKS5"`), and the target hostname is sent to the proxy unresolved, so the proxy does the DNS lookup like `socks5h://`. A rejected SOCKS login shows up as `SocketException: SOCKS: Connection not allowed by ruleset`, not a 407.

**5. Rotation is per connection.** `HttpClient` pools and reuses connections, so one client sending many requests leaves from very few exits. Build a new client per request for a new exit (and close it; `HttpClient` is `AutoCloseable` from JDK 21), or keep one client and add `-session-ID` when you want the same exit.

**6. Check the status before the body.** Without gotcha 1 fixed, the 407 comes back as a response whose body is `null`.
