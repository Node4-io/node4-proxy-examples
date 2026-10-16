"""httpx, sync and async. httpx takes the proxy on the client, not per request."""
import asyncio

import httpx

from _env import proxy_url

with httpx.Client(proxy=proxy_url(), timeout=30) as client:
    print("sync  exit IP:", client.get("https://api.ipify.org").text)


async def main() -> None:
    async with httpx.AsyncClient(proxy=proxy_url(), timeout=30) as client:
        r = await client.get("https://api.ipify.org")
        print("async exit IP:", r.text)


asyncio.run(main())
