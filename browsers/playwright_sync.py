"""Playwright (sync): one browser, one context per identity, one sticky session per context.

A browser keeps connections open, so a whole page load leaves from one or a few exits
even on a rotating gateway. Give each context its own -session- ID and it keeps one
exit IP throughout; open a new context with a new ID to change IP.

    pip install playwright && playwright install chromium
    python playwright_sync.py
"""
from playwright.sync_api import sync_playwright

from _env import GATEWAY, IP_URL, check_credentials, new_session_id, playwright_proxy, session_user

CONTEXTS = 3
check_credentials()  # a wrong password otherwise shows up as a page-load timeout

with sync_playwright() as p:
    browser = p.chromium.launch()  # headless; the proxy is set per context below
    try:
        for n in range(1, CONTEXTS + 1):
            session = new_session_id()
            context = browser.new_context(proxy=playwright_proxy(GATEWAY, session_user(session)))
            page = context.new_page()
            ip1 = page.goto(IP_URL).json()["ip"]
            ip2 = page.goto(IP_URL).json()["ip"]  # same context, same session: same exit
            print(f"context {n} (session {session}): {ip1}, reload {ip2}")
            context.close()  # done with this identity; a new context gets a new exit
    finally:
        browser.close()
