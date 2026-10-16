# Rust

One Cargo project with a binary per example, using [reqwest](https://docs.rs/reqwest) (rustls, no OpenSSL) and tokio.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
cargo run --release --bin basic
cargo run --release --bin rotate
CONCURRENCY=10 N=20 cargo run --release --bin concurrent
```

No Rust toolchain? Run any example in Docker from this folder:

```sh
docker run --rm -e NODE4_USER -e NODE4_PASS -v "$PWD":/app -w /app rust:1 cargo run --release --bin basic
```

| Binary | What it shows |
|---|---|
| `basic` | one request through the rotating gateway |
| `static` | one request through a static proxy (`NODE4_PROXY=IP:4443`), checking the exit matches |
| `sticky` | one exit IP across several connections with `-session-ID` |
| `rotate` | why a default `Client` keeps one IP, and how `pool_max_idle_per_host(0)` gives a new one per request |
| `socks5` | SOCKS5 with `socks5h://` (reqwest's `socks` feature, paid plans) |
| `concurrent` | many requests capped by a `Semaphore` at 10, with backoff that retries from a new exit and never retries a 407 |

Shared code is in `src/lib.rs`: reading `NODE4_USER`, `NODE4_PASS`, `NODE4_GATEWAY` and `NODE4_PROXY`, building the proxy, and spotting a 407. Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084` or `gw-residential.node4.io:8082` to run the same examples on another product.

## Notes

- **Credentials go on the proxy, not in the URL.** `reqwest::Proxy::all("http://host:port")?.basic_auth(user, pass)` needs no percent-encoding. The `url` crate and reqwest accept the underscore in `gw-rotating_datacenter`, for HTTP and for `socks5h://`.
- **Rotation is per connection.** A `reqwest::Client` keeps idle tunnels in a pool and reuses them, so sequential requests through one client share an exit. Build the client with `.pool_max_idle_per_host(0)` to open a new connection, and get a possible new exit, for every request. Keep one client and clone it across tasks; clones share the pool.
- **407 is never retried.** For an `https://` target the 407 arrives as a connect error from the `CONNECT` step, not as a response with that status. `is_proxy_auth_error` in `src/lib.rs` walks the error chain to catch both forms.
- **SOCKS5 has no 407.** With wrong credentials, or on a plan without SOCKS5, the error reads `SOCKS error: connection not allowed`. Treat it like a 407. Use `socks5h://` so the proxy resolves hostnames; `socks5://` resolves them on your machine.
- **Concurrency.** `concurrent` holds a semaphore permit for the whole request, so no more than `CONCURRENCY` connections are open at once. Keep it at or below your plan's connection count on Rotating Unmetered; the free tier allows 10.
- `Cargo.lock` is committed so every build uses the same, tested dependency versions.
