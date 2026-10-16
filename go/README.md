# Go

A concurrent worker pool through a Node4 gateway, using only the standard library.

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
go run . -workers 20 -n 40          # new connection per request: many exits
go run . -workers 2 -n 10 -fresh=false   # reused connections: few exits
```

| Flag | Default | Meaning |
|---|---|---|
| `-workers` | 20 | concurrent connections; keep at or below your plan's limit on Rotating Unmetered |
| `-n` | 40 | requests to send |
| `-fresh` | true | disable keep-alive so each request opens its own connection |
| `-url` | `https://api.ipify.org` | what to fetch |

The proxy is set with `http.Transport{Proxy: http.ProxyURL(...)}`. `url.UserPassword` percent-encodes the credentials for you. Set `NODE4_GATEWAY` to use another product.
