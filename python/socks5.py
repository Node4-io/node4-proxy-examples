"""SOCKS5 with requests (pip install "requests[socks]"). SOCKS5 is on paid plans.

socks5h:// makes the proxy resolve hostnames, so DNS lookups do not leave your machine.
"""
import requests

from _env import GATEWAY, proxy_url, socks_endpoint

url = proxy_url(socks_endpoint(GATEWAY), scheme="socks5h")
r = requests.get("https://api.ipify.org", proxies={"http": url, "https": url}, timeout=30)
print("exit IP over SOCKS5:", r.text)
