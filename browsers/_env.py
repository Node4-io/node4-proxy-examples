"""Shared settings for the browser examples: credentials and endpoints from the environment."""
import os
import secrets
import sys

USER = os.environ.get("NODE4_USER", "")
PASS = os.environ.get("NODE4_PASS", "")
GATEWAY = os.environ.get("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083")
STATIC = os.environ.get("NODE4_PROXY", "")  # one of your static proxies, e.g. 203.0.113.10:4443

if not USER or not PASS:
    sys.exit("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).")

# Small pages, so the examples use little data on per-GB plans.
IP_URL = "https://api.ipify.org?format=json"


def new_session_id() -> str:
    """A fresh sticky-session ID: letters and digits, up to 32 characters."""
    return secrets.token_hex(6)


def session_user(session: str, user: str = USER) -> str:
    """USER-session-ID: the gateway holds one exit IP for this ID (up to 30 minutes)."""
    return f"{user}-session-{session}"


def check_credentials(endpoint: str = GATEWAY, user: str = USER) -> None:
    """Exit early if the proxy rejects the username or password.

    Browsers do not report a rejected proxy password well: Chrome answers the 407
    challenge again on its own and the page load times out instead of failing. One
    CONNECT handshake (no page load, no data) tells you up front.
    """
    import base64
    import socket

    host, port = endpoint.rsplit(":", 1)
    token = base64.b64encode(f"{user}:{PASS}".encode()).decode()
    with socket.create_connection((host, int(port)), timeout=15) as s:
        s.sendall(f"CONNECT api.ipify.org:443 HTTP/1.1\r\nHost: api.ipify.org:443\r\n"
                  f"Proxy-Authorization: Basic {token}\r\n\r\n".encode())
        status = s.recv(1024).split(b"\r\n", 1)[0].decode("latin-1")
    if " 407" in status:
        sys.exit(f"407 from {endpoint}: wrong NODE4_USER / NODE4_PASS, or your plan does not "
                 "include this product. Retrying will not help.")


def playwright_proxy(endpoint: str = GATEWAY, user: str = USER) -> dict:
    """Playwright's proxy option. Credentials go in their own fields, never in the URL."""
    return {"server": f"http://{endpoint}", "username": user, "password": PASS}
