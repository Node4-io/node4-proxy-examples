# Scrapy

A minimal project that sends every request through Node4, with an optional held session per request.

```sh
pip install scrapy
export NODE4_USER='your-username' NODE4_PASS='your-password'
scrapy crawl exit_ip -O exits.json
```

To use it in your own project, copy `node4demo/middlewares.py` and add to `settings.py`:

```python
DOWNLOADER_MIDDLEWARES = {"node4demo.middlewares.Node4ProxyMiddleware": 350}
```

- Requests rotate freely by default.
- `meta={"node4_session": "abc123"}` holds one exit across those requests (up to 30 minutes on the rotating gateways), for logins and other multi-step flows.
- Set `NODE4_GATEWAY` (environment or setting) to use Rotating Unmetered (`gw-rotating_unmetered.node4.io:8084`) or residential (`gw-residential.node4.io:8082`).
- On Rotating Unmetered, keep `CONCURRENT_REQUESTS` at or below your plan's connection count.

The spider defines both `async def start()` (Scrapy 2.13+) and `start_requests()` (older versions).
