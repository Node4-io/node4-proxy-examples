"""Playwright through one static proxy: every page leaves from that exact IP.

    export NODE4_PROXY=203.0.113.10:4443     # one of the IPs on your Proxies page
    python playwright_static.py
"""
import sys

from playwright.sync_api import sync_playwright

from _env import IP_URL, STATIC, check_credentials, playwright_proxy

if not STATIC:
    sys.exit("Set NODE4_PROXY to one of your static proxies, e.g. 203.0.113.10:4443.")
check_credentials(STATIC)

with sync_playwright() as p:
    browser = p.chromium.launch(proxy=playwright_proxy(STATIC))
    try:
        page = browser.new_page()
        resp = page.goto(IP_URL)
        print(f"proxy {STATIC.rsplit(':', 1)[0]} -> exit IP {resp.json()['ip']}")
    finally:
        browser.close()
