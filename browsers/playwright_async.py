"""Playwright (async): several contexts at once, each with its own exit IP.

Each context is an isolated browser profile (cookies, storage) with its own sticky
session, so they run side by side as separate identities.

    pip install playwright && playwright install chromium
    python playwright_async.py
"""
import asyncio

from playwright.async_api import async_playwright

from _env import GATEWAY, IP_URL, check_credentials, new_session_id, playwright_proxy, session_user

CONTEXTS = 3  # each one holds at least one connection open while it runs


async def visit(browser, n: int) -> None:
    session = new_session_id()
    context = await browser.new_context(proxy=playwright_proxy(GATEWAY, session_user(session)))
    try:
        page = await context.new_page()
        resp = await page.goto(IP_URL)
        print(f"context {n} (session {session}): {(await resp.json())['ip']}")
    finally:
        await context.close()


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        try:
            await asyncio.gather(*(visit(browser, n) for n in range(1, CONTEXTS + 1)))
        finally:
            await browser.close()


check_credentials()  # a wrong password otherwise shows up as a page-load timeout
asyncio.run(main())
