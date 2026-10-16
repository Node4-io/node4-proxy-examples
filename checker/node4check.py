#!/usr/bin/env python3
"""node4check: check Node4 proxies and gateways from the command line.

Standard library only (Python 3.9+). HTTP proxies are tested with a CONNECT
tunnel, SOCKS5 proxies with a built-in SOCKS5 client (RFC 1928 / RFC 1929), so
nothing needs to be installed.

    export NODE4_USER=... NODE4_PASS=...
    python node4check.py 203.0.113.10:4443 203.0.113.11:4443
    python node4check.py -f proxies.txt --protocol both --geo
    python node4check.py --gateway                       # rotation + sticky test
    python node4check.py --gateway gw-residential.node4.io:8082 --json

Exit status: 0 if every check passed, 1 if any failed, 2 on a usage error.
"""
from __future__ import annotations

import argparse
import base64
import csv
import http.client
import ipaddress
import json
import os
import re
import secrets
import socket
import ssl
import struct
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from typing import Iterable, List, Optional, Tuple
from urllib.parse import unquote, urlsplit

__version__ = "1.0.0"

DEFAULT_GATEWAY = "gw-rotating_datacenter.node4.io:8083"
DEFAULT_URL = "https://api.ipify.org"
USER_AGENT = f"node4check/{__version__}"

# The SOCKS5 port that pairs with each HTTP port on Node4.
SOCKS_PAIRS = {4443: 1443, 8082: 1082, 8083: 1083, 8084: 1084}
HTTP_PAIRS = {v: k for k, v in SOCKS_PAIRS.items()}

SCHEMES = {"http": "http", "https": "http", "socks5": "socks5", "socks5h": "socks5h", "socks": "socks5h"}

SOCKS_REPLIES = {
    0x01: "general SOCKS server failure",
    0x02: "connection not allowed by ruleset",
    0x03: "network unreachable",
    0x04: "host unreachable",
    0x05: "connection refused by destination",
    0x06: "TTL expired",
    0x07: "command not supported",
    0x08: "address type not supported",
}

# Status values. Everything except OK counts as a failure.
OK = "ok"
AUTH_FAILED = "auth_failed"
TIMEOUT = "timeout"
REFUSED = "refused"
DNS_ERROR = "dns_error"
PROXY_ERROR = "proxy_error"
TLS_ERROR = "tls_error"
BAD_RESPONSE = "bad_response"
ERROR = "error"


# --------------------------------------------------------------------------- parsing


@dataclass(frozen=True)
class Proxy:
    host: str
    port: int
    scheme: str = "http"  # http, socks5 (local DNS) or socks5h (DNS at the proxy)
    user: str = ""
    password: str = field(default="", repr=False)
    explicit_scheme: bool = False

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def protocol(self) -> str:
        return "http" if self.scheme == "http" else "socks5"


def _port(text: str, original: str) -> int:
    if not text.isdigit() or not 0 < int(text) < 65536:
        raise ValueError(f"bad port in {original!r}")
    return int(text)


def _host(text: str, original: str) -> str:
    if not text or not re.fullmatch(r"[A-Za-z0-9_.\-]+", text):
        raise ValueError(f"bad host in {original!r}")
    return text


def parse_proxy(text: str, user: str = "", password: str = "", scheme: str = "http") -> Proxy:
    """Parse one proxy in any common format.

    Accepted: HOST:PORT, HOST:PORT:USER:PASS, USER:PASS@HOST:PORT and URLs such as
    http://USER:PASS@HOST:PORT, socks5://..., socks5h://... (credentials in URLs are
    percent-decoded). Credentials in the entry win over the defaults passed in.
    """
    original = text
    text = text.strip()
    if not text:
        raise ValueError("empty proxy entry")
    if "://" in text:
        parts = urlsplit(text)
        name = parts.scheme.lower()
        if name not in SCHEMES:
            raise ValueError(f"unsupported scheme {parts.scheme!r} in {original!r}")
        try:
            port = parts.port
        except ValueError:
            raise ValueError(f"bad port in {original!r}") from None
        if port is None:
            raise ValueError(f"missing port in {original!r}")
        return Proxy(
            host=_host(parts.hostname or "", original),
            port=port,
            scheme=SCHEMES[name],
            user=unquote(parts.username) if parts.username is not None else user,
            password=unquote(parts.password) if parts.password is not None else password,
            explicit_scheme=True,
        )
    if "@" in text:
        creds, _, hostport = text.rpartition("@")
        u, sep, p = creds.partition(":")
        if not sep:
            raise ValueError(f"expected USER:PASS@HOST:PORT in {original!r}")
        host, sep, port = hostport.rpartition(":")
        if not sep:
            raise ValueError(f"missing port in {original!r}")
        return Proxy(_host(host, original), _port(port, original), scheme, u, p)
    fields = text.split(":", 3)  # the password may itself contain ':'
    if len(fields) == 2:
        return Proxy(_host(fields[0], original), _port(fields[1], original), scheme, user, password)
    if len(fields) == 4:
        return Proxy(_host(fields[0], original), _port(fields[1], original), scheme, fields[2], fields[3])
    raise ValueError(f"cannot parse {original!r}: use HOST:PORT, HOST:PORT:USER:PASS or a URL")


def read_entries(lines: Iterable[str]) -> List[str]:
    """Non-empty lines, without comments (# at the start of a line)."""
    return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]


def with_protocol(proxy: Proxy, protocol: str) -> Proxy:
    """The same proxy on another protocol, moving to the paired Node4 port (4443 <-> 1443, ...)."""
    if protocol == "http" and proxy.scheme != "http":
        return replace(proxy, scheme="http", port=HTTP_PAIRS.get(proxy.port, proxy.port))
    if protocol == "socks5" and proxy.scheme == "http":
        return replace(proxy, scheme="socks5h", port=SOCKS_PAIRS.get(proxy.port, proxy.port))
    return proxy


def extract_ip(body: str) -> Optional[str]:
    """The IP address in a plain-text or JSON ({"ip": ...}) response, or None."""
    body = body.strip()
    candidate = body
    if body.startswith("{"):
        try:
            candidate = str(json.loads(body).get("ip", ""))
        except (ValueError, AttributeError):
            return None
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return None


# --------------------------------------------------------------------------- transport


class CheckError(Exception):
    def __init__(self, status: str, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise CheckError(PROXY_ERROR, "proxy closed the connection during the handshake")
        data += chunk
    return data


def socks5_handshake(sock: socket.socket, host: str, port: int, user: str = "", password: str = "",
                     remote_dns: bool = True) -> None:
    """Open a SOCKS5 CONNECT to host:port on an already connected socket.

    Offers username/password auth (RFC 1929) when credentials are given, and sends the
    hostname to the proxy (socks5h behaviour) unless remote_dns is False.
    """
    methods = b"\x00\x02" if user else b"\x00"
    sock.sendall(b"\x05" + bytes([len(methods)]) + methods)
    version, method = _recv_exact(sock, 2)
    if version != 5:
        raise CheckError(PROXY_ERROR, "not a SOCKS5 proxy (bad greeting)")
    if method == 0xFF:
        hint = "check the credentials" if user else "set NODE4_USER and NODE4_PASS"
        raise CheckError(AUTH_FAILED, f"SOCKS5 proxy accepted none of the offered auth methods ({hint})")
    if method == 0x02:
        u, p = user.encode(), password.encode()
        if len(u) > 255 or len(p) > 255:
            raise CheckError(ERROR, "SOCKS5 username and password are limited to 255 bytes each")
        sock.sendall(b"\x01" + bytes([len(u)]) + u + bytes([len(p)]) + p)
        _, auth_status = _recv_exact(sock, 2)
        if auth_status != 0:
            raise CheckError(AUTH_FAILED, "SOCKS5 username/password rejected (or the plan has no SOCKS5)")
    elif method != 0x00:
        raise CheckError(PROXY_ERROR, f"SOCKS5 proxy chose unsupported auth method {method:#x}")

    try:
        ip = ipaddress.ip_address(host)
        addr = (b"\x01" if ip.version == 4 else b"\x04") + ip.packed
    except ValueError:
        if remote_dns:
            name = host.encode("idna")
            addr = b"\x03" + bytes([len(name)]) + name
        else:
            try:
                addr = b"\x01" + socket.inet_aton(socket.gethostbyname(host))
            except OSError:
                raise CheckError(DNS_ERROR, f"cannot resolve target {host} locally (try socks5h://)") from None
    sock.sendall(b"\x05\x01\x00" + addr + struct.pack(">H", port))

    version, reply, _, atyp = _recv_exact(sock, 4)
    if version != 5:
        raise CheckError(PROXY_ERROR, "bad SOCKS5 reply")
    if reply != 0:
        raise CheckError(PROXY_ERROR, f"SOCKS5: {SOCKS_REPLIES.get(reply, f'error {reply:#x}')}")
    # Drain the bound address the server reports.
    if atyp == 0x01:
        _recv_exact(sock, 4 + 2)
    elif atyp == 0x04:
        _recv_exact(sock, 16 + 2)
    elif atyp == 0x03:
        _recv_exact(sock, _recv_exact(sock, 1)[0] + 2)
    else:
        raise CheckError(PROXY_ERROR, f"bad SOCKS5 address type {atyp:#x}")


def _basic_auth(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def http_connect(sock: socket.socket, host: str, port: int, user: str = "", password: str = "") -> None:
    """Open an HTTP CONNECT tunnel to host:port on an already connected socket."""
    lines = [f"CONNECT {host}:{port} HTTP/1.1", f"Host: {host}:{port}", f"User-Agent: {USER_AGENT}"]
    if user:
        lines.append(f"Proxy-Authorization: {_basic_auth(user, password)}")
    sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = sock.recv(4096)
        if not chunk:
            if not head:
                raise CheckError(PROXY_ERROR, "proxy closed the connection without answering CONNECT")
            break
        head += chunk
        if len(head) > 65536:
            raise CheckError(PROXY_ERROR, "CONNECT response headers too large")
    status_line = head.split(b"\r\n", 1)[0].decode("latin-1")
    match = re.match(r"HTTP/\d(?:\.\d)?\s+(\d{3})\s*(.*)", status_line)
    if not match:
        raise CheckError(PROXY_ERROR, f"not an HTTP proxy (got {status_line[:40]!r})")
    code, reason = int(match.group(1)), match.group(2).strip()
    if code == 407:
        raise CheckError(AUTH_FAILED, "407 Proxy Authentication Required")
    if code != 200:
        raise CheckError(PROXY_ERROR, f"CONNECT answered {code} {reason}".strip())


def _classify(exc: BaseException, phase: str) -> CheckError:
    if isinstance(exc, CheckError):
        return exc
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return CheckError(TIMEOUT, f"timed out ({phase})")
    if isinstance(exc, ConnectionRefusedError):
        return CheckError(REFUSED, f"connection refused ({phase})")
    if isinstance(exc, socket.gaierror):
        return CheckError(DNS_ERROR, "cannot resolve the proxy host")
    if isinstance(exc, ssl.SSLError):
        return CheckError(TLS_ERROR, f"TLS failed: {getattr(exc, 'reason', None) or exc}")
    if isinstance(exc, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError,
                        http.client.RemoteDisconnected)):
        return CheckError(PROXY_ERROR, f"connection closed ({phase})")
    if isinstance(exc, http.client.HTTPException):
        return CheckError(BAD_RESPONSE, f"bad HTTP response ({type(exc).__name__})")
    return CheckError(ERROR, f"{type(exc).__name__}: {exc} ({phase})")


def fetch(proxy: Proxy, url: str, timeout: float) -> Tuple[int, str]:
    """GET url through proxy on a fresh connection; returns (HTTP status, body)."""
    target = urlsplit(url)
    if target.scheme not in ("http", "https") or not target.hostname:
        raise ValueError(f"--url must be http(s)://...: {url!r}")
    tport = target.port or (443 if target.scheme == "https" else 80)
    path = (target.path or "/") + (f"?{target.query}" if target.query else "")
    headers = {"Host": target.netloc, "User-Agent": USER_AGENT, "Accept": "*/*", "Connection": "close"}
    phase = "connecting to proxy"
    sock = None
    try:
        sock = socket.create_connection((proxy.host, proxy.port), timeout=timeout)
        phase = "proxy handshake"
        if proxy.scheme == "http" and target.scheme == "http":
            # Plain HTTP through an HTTP proxy: absolute-form request, no tunnel.
            if proxy.user:
                headers["Proxy-Authorization"] = _basic_auth(proxy.user, proxy.password)
            path = url
        elif proxy.scheme == "http":
            http_connect(sock, target.hostname, tport, proxy.user, proxy.password)
        else:
            socks5_handshake(sock, target.hostname, tport, proxy.user, proxy.password,
                             remote_dns=proxy.scheme == "socks5h")
        if target.scheme == "https":
            phase = "TLS"
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=target.hostname)
        phase = "waiting for response"
        conn = http.client.HTTPConnection(target.hostname, tport, timeout=timeout)
        conn.sock = sock
        conn.request("GET", path, headers=headers)
        resp = conn.getresponse()
        body = resp.read(65536).decode("utf-8", "replace")
        if resp.status == 407 and proxy.scheme == "http" and target.scheme == "http":
            raise CheckError(AUTH_FAILED, "407 Proxy Authentication Required")
        return resp.status, body
    except Exception as exc:  # noqa: BLE001 - every failure becomes a classified result
        raise _classify(exc, phase) from None
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


# --------------------------------------------------------------------------- checks


@dataclass
class Result:
    check: str
    proxy: str
    protocol: str
    status: str
    exit_ip: str = ""
    latency_ms: Optional[int] = None
    country: str = ""
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == OK


def check_one(proxy: Proxy, url: str, timeout: float, check: str = "proxy", expect_exit: bool = False) -> Result:
    result = Result(check=check, proxy=proxy.endpoint, protocol=proxy.protocol, status=OK)
    start = time.monotonic()
    try:
        status, body = fetch(proxy, url, timeout)
    except CheckError as exc:
        result.status, result.detail = exc.status, exc.detail
        return result
    result.latency_ms = round((time.monotonic() - start) * 1000)
    ip = extract_ip(body)
    if status != 200:
        result.status, result.detail = BAD_RESPONSE, f"target answered HTTP {status}"
    elif ip is None:
        result.status, result.detail = BAD_RESPONSE, f"no IP address in response: {body.strip()[:40]!r}"
    else:
        result.exit_ip = ip
        if expect_exit and _is_ip(proxy.host) and ip != proxy.host:
            result.detail = "exit IP differs from the proxy IP"
    return result


def _is_ip(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


_country_cache: dict = {}


def lookup_country(ip: str, timeout: float = 6.0) -> str:
    """Two-letter country for an IP, looked up directly (not through the proxy). Empty on failure."""
    if ip in _country_cache:
        return _country_cache[ip]
    country = ""
    for url in (f"https://ipinfo.io/{ip}/country", f"http://ip-api.com/line/{ip}?fields=countryCode"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read(64).decode().strip().upper()
            if re.fullmatch(r"[A-Z]{2}", text):
                country = text
                break
        except Exception:  # noqa: BLE001 - geo is best effort
            continue
    _country_cache[ip] = country
    return country


@dataclass
class GatewayTest:
    name: str
    passed: bool
    summary: str
    connections: int
    distinct_exits: int
    session: str = ""


def rotation_summary(results: List[Result]) -> GatewayTest:
    good = [r.exit_ip for r in results if r.ok]
    distinct = len(set(good))
    n = len(results)
    if not good:
        return GatewayTest("rotation", False, f"{n} new connections, none succeeded", n, 0)
    passed = distinct > 1 or len(good) == 1
    note = "" if passed else " (expected more than one; rotation may be off for this login)"
    failed = n - len(good)
    extra = f", {failed} failed" if failed else ""
    return GatewayTest("rotation", passed and not failed,
                       f"{n} new connections -> {distinct} distinct exit{'s' if distinct != 1 else ''}{extra}{note}",
                       n, distinct)


def sticky_summary(results: List[Result], session: str) -> GatewayTest:
    good = [r.exit_ip for r in results if r.ok]
    distinct = sorted(set(good))
    n = len(results)
    if not good:
        return GatewayTest("sticky", False, f"session {session}: {n} connections, none succeeded", n, 0, session)
    passed = len(distinct) == 1 and len(good) == n
    if passed:
        text = f"session {session}: {n} connections -> 1 exit ({distinct[0]})"
    else:
        text = f"session {session}: {n} connections -> {len(distinct)} exits, {n - len(good)} failed"
    return GatewayTest("sticky", passed, text, n, len(distinct), session)


def run(args: argparse.Namespace, out=sys.stdout) -> int:
    user = os.environ.get("NODE4_USER", "")
    password = os.environ.get("NODE4_PASS", "")

    entries: List[str] = list(args.proxies)
    if args.file:
        if args.file == "-":
            entries += read_entries(sys.stdin)
        else:
            with open(args.file, encoding="utf-8") as fh:
                entries += read_entries(fh)
    gateway = None
    if args.gateway is not None:
        gateway = args.gateway or os.environ.get("NODE4_GATEWAY") or DEFAULT_GATEWAY
    if not entries and gateway is None:
        if os.environ.get("NODE4_PROXY"):
            entries = [os.environ["NODE4_PROXY"]]
        else:
            print("Nothing to check: pass proxies, -f FILE, or --gateway (or set NODE4_PROXY).", file=sys.stderr)
            return 2

    protocols = ["http", "socks5"] if args.protocol == "both" else [args.protocol] if args.protocol else []
    try:
        parsed = [parse_proxy(e, user, password) for e in entries]
        gw = parse_proxy(gateway, user, password) if gateway else None
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if gw and gw.port in (4443, 1443):
        print(f"error: {gw.endpoint} is a static proxy, not a gateway: it does not rotate or take session IDs. "
              "Check it without --gateway.", file=sys.stderr)
        return 2

    jobs: List[Tuple[Proxy, str]] = []
    for p in parsed:
        if p.explicit_scheme and not args.protocol:
            jobs.append((p, "proxy"))
        else:
            for proto in protocols or ["http"]:
                jobs.append((with_protocol(p, proto), "proxy"))
    if any(not p.user for p, _ in jobs) or (gw and not gw.user):
        print("warning: no credentials for some entries (set NODE4_USER and NODE4_PASS); "
              "only IP-whitelisted connections will pass", file=sys.stderr)

    results: List[Result] = []
    tests: List[GatewayTest] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        results += pool.map(lambda job: check_one(job[0], args.url, args.timeout, job[1], expect_exit=True), jobs)

        if gw:
            for proto in protocols or [gw.protocol]:
                g = with_protocol(gw, proto)
                base = check_one(g, args.url, args.timeout, "gateway")
                results.append(base)
                if not base.ok:
                    continue  # no point testing rotation through a gateway that does not answer
                if args.rotation > 0:
                    rot = list(pool.map(lambda _: check_one(g, args.url, args.timeout, "rotation"),
                                        range(args.rotation)))
                    results += rot
                    t = rotation_summary(rot)
                    t.name = f"rotation/{g.protocol}"
                    tests.append(t)
                if args.sticky > 0:
                    session = "n4c" + secrets.token_hex(5)
                    sg = replace(g, user=f"{g.user}-session-{session}")
                    # Sequential: the session is pinned on its first connection.
                    sticky = [check_one(sg, args.url, args.timeout, "sticky") for _ in range(args.sticky)]
                    for r in sticky:
                        r.detail = r.detail or f"session {session}"
                    results += sticky
                    t = sticky_summary(sticky, session)
                    t.name = f"sticky/{g.protocol}"
                    tests.append(t)

        if args.geo:
            ips = sorted({r.exit_ip for r in results if r.exit_ip})
            countries = dict(zip(ips, pool.map(lookup_country, ips)))
            for r in results:
                r.country = countries.get(r.exit_ip, "")

    failed = [r for r in results if not r.ok] + [t for t in tests if not t.passed]
    if args.json:
        payload = {
            "results": [asdict(r) for r in results],
            "gateway_tests": [asdict(t) for t in tests],
            "summary": {"checks": len(results), "ok": sum(r.ok for r in results),
                        "failed": sum(not r.ok for r in results),
                        "gateway_tests_failed": sum(not t.passed for t in tests)},
        }
        json.dump(payload, out, indent=2)
        out.write("\n")
    elif args.csv:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["check", "proxy", "protocol", "status", "exit_ip", "latency_ms", "country", "detail"])
        for r in results:
            writer.writerow([r.check, r.proxy, r.protocol, r.status, r.exit_ip,
                             "" if r.latency_ms is None else r.latency_ms, r.country, r.detail])
        for t in tests:
            writer.writerow([t.name, gw.endpoint if gw else "", t.name.split("/")[-1],
                             OK if t.passed else "failed", "", "", "", t.summary])
    else:
        print_table(results, tests, args.geo, out)
    return 1 if failed else 0


def print_table(results: List[Result], tests: List[GatewayTest], geo: bool, out) -> None:
    headers = ["CHECK", "PROXY", "PROTO", "STATUS", "EXIT IP", "MS"] + (["CC"] if geo else []) + ["DETAIL"]
    rows = []
    for r in results:
        row = [r.check, r.proxy, r.protocol, r.status.upper() if not r.ok else "ok", r.exit_ip or "-",
               "-" if r.latency_ms is None else str(r.latency_ms)]
        if geo:
            row.append(r.country or "-")
        row.append(r.detail)
        rows.append(row)
    widths = [max(len(h), *(len(row[i]) for row in rows)) if rows else len(h) for i, h in enumerate(headers)]
    widths[-1] = 0  # the last column is not padded
    for row in [headers] + rows:
        out.write("  ".join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip() + "\n")
    if tests:
        out.write("\n")
        for t in tests:
            out.write(f"{t.name:<16} {'PASS' if t.passed else 'FAIL'}  {t.summary}\n")
    ok = sum(r.ok for r in results)
    lat = sorted(r.latency_ms for r in results if r.ok and r.latency_ms is not None)
    median = f", median {lat[len(lat) // 2]} ms" if lat else ""
    out.write(f"\n{ok}/{len(results)} checks ok{median}\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="node4check",
        description="Check Node4 proxies and gateways: status, exit IP, latency, rotation and sticky sessions.",
        epilog="Credentials come from NODE4_USER and NODE4_PASS unless an entry carries its own. "
               "Formats: HOST:PORT, HOST:PORT:USER:PASS, USER:PASS@HOST:PORT, http://, socks5://, socks5h:// URLs.",
    )
    p.add_argument("proxies", nargs="*", help="proxies to check")
    p.add_argument("-f", "--file", help="file with one proxy per line ('-' for stdin); # starts a comment")
    p.add_argument("-g", "--gateway", nargs="?", const="", default=None, metavar="HOST:PORT",
                   help=f"check a rotating or residential gateway (default: $NODE4_GATEWAY or {DEFAULT_GATEWAY})")
    p.add_argument("-p", "--protocol", choices=["http", "socks5", "both"],
                   help="protocol for entries without a scheme (default http). socks5 and both use the paired "
                        "Node4 port: 4443->1443, 8083->1083, 8084->1084, 8082->1082")
    p.add_argument("-c", "--concurrency", type=int, default=10, help="connections at once (default 10)")
    p.add_argument("-t", "--timeout", type=float, default=15.0, help="seconds per connection step (default 15)")
    p.add_argument("--url", default=DEFAULT_URL, help=f"URL that returns the caller's IP (default {DEFAULT_URL})")
    p.add_argument("--rotation", type=int, default=5, metavar="N",
                   help="gateway: N new connections, expect more than one exit (default 5, 0 to skip)")
    p.add_argument("--sticky", type=int, default=3, metavar="N",
                   help="gateway: N connections on one session ID, expect one exit (default 3, 0 to skip)")
    p.add_argument("--geo", action="store_true", help="look up each exit IP's country (ipinfo.io, direct)")
    fmt = p.add_mutually_exclusive_group()
    fmt.add_argument("--json", action="store_true", help="print JSON")
    fmt.add_argument("--csv", action="store_true", help="print CSV")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
