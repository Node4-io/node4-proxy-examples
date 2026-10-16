"""The smallest working example: one request through the rotating gateway with requests."""
import requests

from _env import proxy_url

proxies = {"http": proxy_url(), "https": proxy_url()}
r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=30)
r.raise_for_status()
print("exit IP:", r.json()["ip"])
