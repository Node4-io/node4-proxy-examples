# C# / .NET

`HttpClient` with a `WebProxy` and `NetworkCredential`, no packages. One console project, one file per example. Needs the .NET 8 SDK (the code also runs on .NET 6 and 7 if you change `TargetFramework`).

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
dotnet run -- basic
dotnet run -- rotate
NODE4_PROXY=203.0.113.10:4443 dotnet run -- static
```

No SDK installed? Run it in Docker:

```sh
docker run --rm -e NODE4_USER -e NODE4_PASS -v "$PWD:/src" -w /src mcr.microsoft.com/dotnet/sdk:8.0 dotnet run -- basic
```

| Command | File | What it shows |
|---|---|---|
| `basic` | `Basic.cs` | one request through the rotating gateway |
| `static [IP:4443]` | `StaticProxy.cs` | one request through a static proxy, and a check that it left from that IP |
| `sticky` | `Sticky.cs` | one exit IP across several connections with `-session-ID` |
| `rotate` | `Rotate.cs` | a reused `HttpClient` keeps one exit; `PooledConnectionLifetime = Zero` or `Connection: close` gets a new one per request |
| `socks5 [IP:4443]` | `Socks5.cs` | SOCKS5 with username and password (paid plans) |
| `concurrent [n] [workers]` | `Concurrent.cs` | `SemaphoreSlim`-capped requests with backoff that retries on a new connection and stops on 407 |
| | `Env.cs` | reads the environment, builds the `WebProxy` and `HttpClient` |

Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084` or `gw-residential.node4.io:8082` to run the same commands on another product.

## Gotchas

- **Rotation is per connection.** `HttpClient` pools connections, and every request sent down a pooled tunnel leaves from the same exit. `rotate` prints 1 distinct exit for the reused client and 5 for the other two loops. Do not create a new `HttpClient` per request to get rotation: set `PooledConnectionLifetime = TimeSpan.Zero` on the handler, or `request.Headers.ConnectionClose = true` on the requests that need a new exit.
- **407 has two shapes.** For an `https://` target it arrives as an `HttpRequestException` from the CONNECT step; for `http://` as a response with status 407. `Concurrent.cs` handles both and stops instead of retrying.
- **SOCKS5 needs .NET 6 or later.** Use `socks5://host:port` as the `WebProxy` address and put the login in `Credentials`. .NET sends the target hostname to the proxy, so it behaves like `socks5h://` elsewhere. A SOCKS5 server has no 407: a wrong password shows up as a proxy tunnel error instead.
- **Credentials go in `NetworkCredential`**, not in the proxy URL, so passwords with `@`, `:` or `/` need no escaping.
- **Underscore hostnames work.** `new Uri("http://gw-rotating_datacenter.node4.io:8083")` parses and connects on .NET 8 (HTTP and SOCKS5) and on .NET Framework (Windows PowerShell 5.1 uses it). If an older runtime rejects the name, resolve it with `Dns.GetHostAddresses` and use the IP with the same port.
- **Concurrency:** `MaxConnectionsPerServer` caps the tunnels the handler opens, the semaphore caps requests in flight. Keep both at or below 10 on the free tier, or your plan's connection count on Rotating Unmetered.
