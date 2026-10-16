"""Many requests at once with aiohttp, capped by a semaphore.

On Rotating Unmetered you buy concurrent connections, so set CONCURRENCY at or below
your plan's connection count. Each new connection can leave from a different exit.
"""
import asyncio
import os

import aiohttp

from _env import proxy_url

CONCURRENCY = int(os.environ.get("CONCURRENCY", "10"))
URLS = ["https://api.ipify.org"] * 40


async def fetch(session: aiohttp.ClientSession, sem: asyncio.Semaphore, url: str) -> str:
    async with sem:
        async with session.get(url, proxy=proxy_url(), timeout=aiohttp.ClientTimeout(total=30)) as r:
            return await r.text()


async def main() -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    # force_close: no keep-alive, so each request opens its own connection (and exit).
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, force_close=True)
    async with aiohttp.ClientSession(connector=connector) as session:
        ips = await asyncio.gather(*(fetch(session, sem, u) for u in URLS), return_exceptions=True)
    ok = [i for i in ips if isinstance(i, str)]
    print(f"{len(ok)}/{len(URLS)} ok, {len(set(ok))} distinct exits, concurrency {CONCURRENCY}")


asyncio.run(main())
