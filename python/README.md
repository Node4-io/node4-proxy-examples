# Python

```sh
pip install -r requirements.txt
export NODE4_USER='your-username' NODE4_PASS='your-password'
python basic_requests.py
```

| File | What it shows |
|---|---|
| `basic_requests.py` | one request through the rotating gateway |
| `socks5.py` | SOCKS5 with `socks5h://` (paid plans) |
| `sticky_session.py` | one exit IP across several connections with `-session-ID` |
| `rotate_per_request.py` | why a reused `Session` keeps one IP, and how to get a new one per request |
| `retries.py` | backoff that retries from a new exit each time |
| `httpx_example.py` | httpx, sync and async |
| `async_aiohttp.py` | many requests at once, capped to your connection count |
| `check_static_proxies.py` | test a list of static proxies in parallel |

Set `NODE4_GATEWAY` to `gw-rotating_unmetered.node4.io:8084` or `gw-residential.node4.io:8082` to run the same examples on another product, or `NODE4_PROXY=IP:4443` for the static checker.
