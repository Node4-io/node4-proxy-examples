"""Why a reused client keeps one IP, and how to get a new exit per request.

Rotation is per CONNECTION. An HTTPS request travels inside a CONNECT tunnel, and every
request sent down that tunnel leaves from the same exit. requests.Session keeps the
tunnel open (keep-alive), so the first loop below usually reports one IP. The second
loop opens a fresh connection per request, so each one can get a different exit.
"""
import requests

from _env import proxy_url

proxies = {"http": proxy_url(), "https": proxy_url()}
URL = "https://api.ipify.org"

with requests.Session() as s:
    reused = {s.get(URL, proxies=proxies, timeout=30).text for _ in range(5)}
print("one Session, 5 requests  ->", len(reused), "distinct exit(s)")

fresh = set()
for _ in range(5):
    with requests.Session() as s:  # new session = new connection = new exit
        fresh.add(s.get(URL, proxies=proxies, timeout=30, headers={"Connection": "close"}).text)
print("new connection each time ->", len(fresh), "distinct exit(s)")
