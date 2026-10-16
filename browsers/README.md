# Browsers

Browser automation through Node4: Playwright, Puppeteer, Selenium with Chrome or Firefox, and a local forwarder for any browser or tool that cannot send proxy credentials.

```sh
pip install -r requirements.txt && playwright install chromium
export NODE4_USER='your-username' NODE4_PASS='your-password'
python playwright_sync.py
```

## Which tool, and how the login gets there

Browsers take the proxy address and the proxy login separately. Chrome ignores `user:pass@` in `--proxy-server`, so the credentials have to arrive some other way.

| Tool | How the username and password are passed | SOCKS5 | New IP |
|---|---|---|---|
| Playwright (Python, Node) | `proxy={"server", "username", "password"}` on the browser or on each context | No: use the HTTP port | new context with a new `-session-` ID |
| Puppeteer | `--proxy-server` or `createBrowserContext({proxyServer})`, then `page.authenticate()` | No | new context with a new session username |
| Selenium + Chrome | [local forwarder](local-forwarder/) (any Chrome), or a small extension (Chrome for Testing or Chromium only) | No | new driver with a new forwarder or session |
| Selenium + Firefox | local forwarder | No | new driver with a new forwarder or session |
| Chrome by hand, desktop apps, anything that takes only `host:port` | local forwarder | No | another forwarder port (`--sessions N`) |

Chrome does not support SOCKS5 with a username and password (Playwright stops with "Browser does not support socks5 proxy authentication"), and Firefox's proxy settings have no login fields. So browsers use the HTTP port of each product (`4443`, `8082`, `8083`, `8084`). HTTPS still works: it is tunnelled with `CONNECT`.

## One IP per browser identity

Rotation happens per connection, and a browser keeps its connections open, so one page load already leaves from one or a few exits. For a consistent identity, give each browser context its own sticky session (`USER-session-abc123`) and it holds one exit IP for up to 30 minutes. To change IP, open a new context with a new session ID. All the examples do this.

## Files

| File | What it shows |
|---|---|
| `playwright_sync.py` | three contexts, three session IDs, three exit IPs; a reload keeps the same IP |
| `playwright_async.py` | the same, running the contexts at once |
| `playwright_static.py` | one static proxy (`NODE4_PROXY=IP:4443`): every page leaves from that exact IP |
| `playwright_block_assets.py` | skip images, fonts and media to use less data on per-GB plans, with a before/after byte count |
| `selenium_chrome.py` | Selenium + Chrome through the local forwarder, one forwarder and session per browser |
| `selenium_chrome_extension.py` | Selenium + Chrome for Testing with a two-file login extension, no extra process |
| `selenium_firefox.py` | Selenium + Firefox through the local forwarder |
| `node/playwright-contexts.mjs` | Node.js Playwright, one proxy and session per context |
| `node/puppeteer-contexts.mjs` | Node.js Puppeteer, one proxy context and session per identity |
| [`local-forwarder/`](local-forwarder/) | `node4_forwarder.py`: no-login proxy on `127.0.0.1` that adds your credentials upstream, with tests |

Node.js: `cd node && npm install && npx playwright install chromium && node playwright-contexts.mjs`.

Set `NODE4_GATEWAY` to use another product: `gw-rotating_unmetered.node4.io:8084`, `gw-residential.node4.io:8082`.

## Use less data on per-GB plans

Rotating Datacenter and residential bill per GB, and a browser downloads far more than the HTML. `playwright_block_assets.py` aborts image, font and media requests before they leave the browser. On `https://en.wikipedia.org/wiki/Proxy_server` it measured 600 KB with everything and 381 KB without images and fonts, 36% less. Image-heavy pages save more and text-only pages save less, so run it on your own target: `python playwright_block_assets.py https://your-target/`.

Other savings: reuse one context for many pages so the cache works, and skip `networkidle` waits when the content you need is already there. Rotating Unmetered bills by connections, not data.

## A wrong password looks like a timeout

When the proxy rejects the login, Chromium answers the challenge again on its own, and Playwright reports a page-load timeout instead of a `407`. Puppeteer shows Chrome's error page. The examples check the credentials once before starting the browser (one `CONNECT` handshake, no page load) and stop with a clear message. A `407` means wrong credentials or a product your plan does not include; retrying will not help.

## Selenium approaches that do not work

Tested with Selenium 4.51, Chrome 155 and Firefox 154:

- **Selenium BiDi `driver.network.add_auth_handler()`** with Chrome: the browser asks for the login, but the reply (`network.continueWithAuth`) times out and the page never loads.
- **The same with Firefox** (proxy set in preferences): the session never starts. Firefox stops at its proxy login prompt before Selenium can attach a handler.
- **`driver.execute_cdp_cmd("Fetch.enable", {"handleAuthRequests": True})`**: every request pauses waiting for an answer, but `execute_cdp_cmd` cannot receive the events it would need to answer, so the page load hangs.
- **`--load-extension` with branded Google Chrome 137+**: ignored. The extension never loads and the page fails to open. Chrome for Testing and Chromium still accept it, which is what `selenium_chrome_extension.py` uses (tested on Chromium 156 and Chrome for Testing 131).
- **selenium-wire**: no longer maintained; the local forwarder does the same job without patching Selenium.

The local forwarder works with every browser and needs nothing from the browser, so it is the default here.
