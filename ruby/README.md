# Ruby

The Net::HTTP examples use only the standard library. `faraday_example.rb` and `socks5.rb` need the gems in the `Gemfile`.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
ruby basic.rb

bundle install                       # only for the gem examples
bundle exec ruby faraday_example.rb
```

No Ruby installed? Run any example in Docker from this folder:

```sh
docker run --rm -e NODE4_USER -e NODE4_PASS -v "$PWD":/app -w /app ruby:3.3 ruby basic.rb
docker run --rm -e NODE4_USER -e NODE4_PASS -v "$PWD":/app -w /app ruby:3.3 sh -c "bundle install --quiet && bundle exec ruby socks5.rb"
```

| File | What it shows |
|---|---|
| `basic.rb` | one request through the rotating gateway with `Net::HTTP` |
| `static.rb` | one request through a static proxy (`NODE4_PROXY=IP:4443`), checking the exit matches |
| `sticky_session.rb` | one exit IP across several connections with `-session-ID` |
| `rotate_per_request.rb` | why requests inside one `Net::HTTP#start` block keep one IP, and how to get a new one per request |
| `concurrent.rb` | a pool of 10 threads, with backoff that retries from a new exit and never retries a 407 |
| `faraday_example.rb` | Faraday with the default adapter (new exit per request) and `net_http_persistent` (one exit) |
| `socks5.rb` | SOCKS5 with the `socksify` gem, hostname resolved by the proxy (paid plans) |
| `_env.rb` | shared settings: reads `NODE4_USER`, `NODE4_PASS`, `NODE4_GATEWAY`, `NODE4_PROXY` |

`concurrent.rb` reads `CONCURRENCY` (default 10), `N` (default 20) and `URL`. Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084` or `gw-residential.node4.io:8082` to run the same examples on another product.

## Notes

- **Proxy arguments, not a proxy URL.** `Net::HTTP.new(host, port, proxy_host, proxy_port, user, pass)` takes the proxy as separate arguments, so the underscore in `gw-rotating_datacenter` and special characters in your password need no escaping. Faraday takes a URL: percent-encode the username and password (`ERB::Util.url_encode`), as `faraday_example.rb` does. Ruby's `URI` accepts the underscore in the hostname.
- **Rotation is per connection.** `Net::HTTP#request` outside a `start` block opens and closes its own connection, so each call can leave from a new exit. Everything inside one `start` block shares a tunnel and one exit. Faraday's default adapter opens a connection per request; `net_http_persistent` keeps it.
- **407 is never retried.** For an `https://` target, `Net::HTTP` raises `Net::HTTPClientException` with message `407 ...` from the `CONNECT` step instead of returning a response. `_env.rb` and `concurrent.rb` turn that into a clear message and stop.
- **SOCKS5 has no 407.** With wrong credentials, or on a plan without SOCKS5, the connection is refused (`SOCKSError::NotAllowed`, "connection not allowed by ruleset"). Treat it like a 407. `socksify` sends the target hostname to the proxy, so you get `socks5h` behaviour without extra setup.
- **Threads are fine here.** Ruby releases the interpreter lock while waiting on the network, so a thread pool gives real concurrency for proxy work. Keep `CONCURRENCY` at or below your plan's connection count on Rotating Unmetered; the free tier allows 10.
