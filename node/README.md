# Node.js

```sh
npm install
export NODE4_USER='your-username' NODE4_PASS='your-password'
node fetch-undici.mjs
```

| File | What it shows |
|---|---|
| `fetch-undici.mjs` | built-in `fetch` through an undici `ProxyAgent` (fetch ignores `HTTP_PROXY`) |
| `axios.mjs` | axios with `https-proxy-agent` and `proxy: false` |
| `socks5.mjs` | SOCKS5 with `socks-proxy-agent` and `socks5h://` (paid plans) |
| `rotate-per-request.mjs` | one agent keeps one exit; a new connection gets a new one; a session ID holds one |
| `playwright.mjs` | a browser through the proxy, credentials in the `proxy` option |
| `puppeteer.mjs` | Chrome with `--proxy-server` and `page.authenticate()` |

Playwright and Puppeteer are optional dependencies because they download a browser. Set `NODE4_GATEWAY` to run any example on another product (`gw-rotating_unmetered.node4.io:8084`, `gw-residential.node4.io:8082`, or a static `IP:4443`).
