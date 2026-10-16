"""Playwright: skip images, fonts and media to use less data on per-GB plans.

Loads one page twice, each in a fresh context (empty cache): once normally, once with
images, fonts and media aborted before they are requested. Prints the bytes each load
pulled through the proxy and the difference.

Rotating Datacenter and residential bill per GB, so on image-heavy pages this is the
biggest single saving. Rotating Unmetered bills by connections, not data.

    python playwright_block_assets.py [URL]

The byte counts are response headers plus bodies as received (compressed). TLS and
connection overhead add a little on top of both numbers.
"""
import sys

from playwright.sync_api import sync_playwright

from _env import GATEWAY, check_credentials, new_session_id, playwright_proxy, session_user

URL = sys.argv[1] if len(sys.argv) > 1 else "https://en.wikipedia.org/wiki/Proxy_server"
BLOCK = {"image", "font", "media"}  # add "stylesheet" too if you only need the HTML and text


def load(browser, block: bool) -> tuple[int, int, int]:
    """Returns (bytes received, requests made, requests blocked)."""
    context = browser.new_context(proxy=playwright_proxy(GATEWAY, session_user(new_session_id())))
    blocked = 0
    if block:
        def handle(route):
            nonlocal blocked
            if route.request.resource_type in BLOCK:
                blocked += 1
                route.abort()  # never leaves the browser, never billed
            else:
                route.continue_()
        context.route("**/*", handle)

    finished = []
    context.on("requestfinished", lambda request: finished.append(request))
    page = context.new_page()
    page.goto(URL, wait_until="load")
    page.wait_for_timeout(1000)  # let late requests finish
    received = 0
    for request in finished:
        sizes = request.sizes()
        received += sizes["responseHeadersSize"] + max(sizes["responseBodySize"], 0)
    context.close()
    return received, len(finished), blocked


check_credentials()
with sync_playwright() as p:
    browser = p.chromium.launch()
    try:
        full, n_full, _ = load(browser, block=False)
        lean, n_lean, n_blocked = load(browser, block=True)
    finally:
        browser.close()

print(URL)
print(f"everything:        {full / 1024:8.0f} KB in {n_full} requests")
print(f"no images/fonts:   {lean / 1024:8.0f} KB in {n_lean} requests ({n_blocked} blocked)")
if full:
    print(f"saved:             {(full - lean) / 1024:8.0f} KB ({(full - lean) / full:.0%} of this page)")
