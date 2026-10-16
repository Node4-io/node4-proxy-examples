# curl

```sh
export NODE4_USER='your-username' NODE4_PASS='your-password'
export NODE4_PROXY='IP:4443'   # optional: one of your static proxies
bash examples.sh
```

`examples.sh` shows the rotating gateway over HTTP and SOCKS5, a sticky session, country targeting and a static proxy.

Two habits worth keeping:

- Use `socks5h://` (or `--socks5-hostname`) so DNS is resolved at the proxy and does not leak from your machine.
- One curl command that fetches several URLs reuses one connection, and therefore one exit IP. Run one URL per command if you want a new IP each time.

The script passes credentials with `-U "$NODE4_USER:$NODE4_PASS"` rather than inside the proxy URL, so a password containing `@`, `:` or `/` works without escaping.
