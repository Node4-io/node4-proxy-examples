"""Route every request through Node4.

Scrapy's built-in HttpProxyMiddleware reads request.meta["proxy"] and turns the
credentials in that URL into a Proxy-Authorization header, so all this middleware
does is set it. Give a request meta["node4_session"] to hold one exit for a
multi-step flow (a login, a cart); requests without one rotate freely.
"""
import os
from urllib.parse import quote


class Node4ProxyMiddleware:
    def __init__(self, user: str, password: str, gateway: str):
        if not user or not password:
            raise ValueError("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).")
        self.user, self.password, self.gateway = user, password, gateway

    @classmethod
    def from_crawler(cls, crawler):
        s = crawler.settings
        return cls(
            s.get("NODE4_USER") or os.environ.get("NODE4_USER", ""),
            s.get("NODE4_PASS") or os.environ.get("NODE4_PASS", ""),
            s.get("NODE4_GATEWAY") or os.environ.get("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083"),
        )

    def process_request(self, request, spider=None):
        if "proxy" in request.meta:
            return None
        user = self.user
        session = request.meta.get("node4_session")
        if session:
            user = f"{user}-session-{session}"
        request.meta["proxy"] = f"http://{quote(user, safe='')}:{quote(self.password, safe='')}@{self.gateway}"
        return None
