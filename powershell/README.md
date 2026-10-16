# PowerShell

`Invoke-RestMethod` with `-Proxy` and `-ProxyCredential`. Works on Windows PowerShell 5.1 and PowerShell 7; SOCKS5 needs PowerShell 7.

```powershell
$env:NODE4_USER = 'your-username'
$env:NODE4_PASS = 'your-password'
.\basic.ps1
.\check-static.ps1 proxies.txt
```

If scripts are blocked, run them with `powershell -ExecutionPolicy Bypass -File .\basic.ps1`, or `Unblock-File *.ps1` once.

On macOS, Linux, or in Docker with PowerShell 7:

```sh
docker run --rm -e NODE4_USER -e NODE4_PASS -v "$PWD:/src" -w /src mcr.microsoft.com/powershell pwsh ./basic.ps1
```

| File | What it shows |
|---|---|
| `basic.ps1` | one request through the rotating gateway |
| `static.ps1` | one request through a static proxy (`NODE4_PROXY` or an argument), and a check that it left from that IP |
| `sticky.ps1` | one exit IP across several connections with `-session-ID` |
| `rotate.ps1` | what keep-alive does to rotation, and `-DisableKeepAlive` for a new exit per call |
| `socks5.ps1` | SOCKS5 with username and password (PowerShell 7, paid plans) |
| `check-static.ps1` | test a list of static proxies, 10 at a time: up, fast, leaving from its own IP |
| `api.ps1` | the REST API: status, proxy list export, usage, IP whitelist (needs `NODE4_API_KEY`; see [`api/`](../api/)) |
| `_env.ps1` | reads the environment and builds the `PSCredential` |

Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084` or `gw-residential.node4.io:8082` to run the same examples on another product.

## Gotchas

- **Rotation is per connection, and 5.1 and 7 differ.** Windows PowerShell 5.1 keeps the tunnel open between calls, so five calls in a row usually leave from one exit. PowerShell 7 opens a new connection for each call unless you pass `-WebSession`. `rotate.ps1` printed `1` then `5` distinct exits on 5.1, and `5` and `5` on 7.4. Pass `-DisableKeepAlive` when you want a new exit per call on both.
- **SOCKS5 is PowerShell 7 only.** Use `-Proxy socks5://host:1083` with `-ProxyCredential`; the target hostname is resolved by the proxy. Windows PowerShell 5.1 has no SOCKS support. A SOCKS5 server has no 407: a wrong password shows up as "An error occurred while establishing a connection to the proxy tunnel".
- **TLS on 5.1.** Older Windows PowerShell may default to TLS 1.0. `_env.ps1` adds TLS 1.2 to `[Net.ServicePointManager]::SecurityProtocol`; do the same in your own scripts.
- **407 is not retryable.** On both versions it is an exception mentioning 407 or "Proxy Authentication Required". Check the username, password and that your plan includes that product.
- **Underscore hostnames work** on 5.1 and 7 (`-Proxy http://gw-rotating_datacenter.node4.io:8083`). If something in your chain rejects the name, use `[Net.Dns]::GetHostAddresses('gw-rotating_datacenter.node4.io')` and the IP with the same port.
- **`-ProxyCredential` takes a `PSCredential`.** For session or country options build it with the full username, for example `"$env:NODE4_USER-session-abc123"` (`Get-Node4Credential` in `_env.ps1`).
