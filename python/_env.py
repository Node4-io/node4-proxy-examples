"""Shared settings for the examples: credentials and endpoints from the environment."""
import os
import sys
from urllib.parse import quote

USER = os.environ.get("NODE4_USER", "")
PASS = os.environ.get("NODE4_PASS", "")
GATEWAY = os.environ.get("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083")
STATIC = os.environ.get("NODE4_PROXY", "")  # one of your static proxies, e.g. 203.0.113.10:4443

if not USER or not PASS:
    sys.exit("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).")


def proxy_url(endpoint: str = GATEWAY, user: str = USER, scheme: str = "http") -> str:
    """Build scheme://user:pass@host:port, percent-encoding the credentials."""
    return f"{scheme}://{quote(user, safe='')}:{quote(PASS, safe='')}@{endpoint}"


def socks_endpoint(endpoint: str) -> str:
    """The SOCKS5 port that pairs with an HTTP endpoint (8083->1083, 4443->1443, ...)."""
    host, port = endpoint.rsplit(":", 1)
    pairs = {"8082": "1082", "8083": "1083", "8084": "1084", "4443": "1443"}
    return f"{host}:{pairs.get(port, port)}"
