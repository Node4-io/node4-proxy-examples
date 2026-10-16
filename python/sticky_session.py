"""Hold one exit IP across several connections with a session ID in the username.

On the rotating gateways a session holds its exit for up to 30 minutes from first use.
Use a new ID to get a new exit. Residential sessions are best effort with the same ceiling.
"""
import secrets

import requests

from _env import USER, proxy_url

session_id = secrets.token_hex(4)
sticky = proxy_url(user=f"{USER}-session-{session_id}")

seen = set()
for _ in range(3):
    # A new requests call each time means a new connection, yet the exit stays the same.
    ip = requests.get("https://api.ipify.org", proxies={"http": sticky, "https": sticky}, timeout=30).text
    seen.add(ip)
    print("session", session_id, "->", ip)

print("distinct exits:", len(seen), "(expect 1)")
