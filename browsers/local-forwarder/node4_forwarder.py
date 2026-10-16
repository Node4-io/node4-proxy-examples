#!/usr/bin/env python3
"""Local proxy forwarder for Node4: no auth on 127.0.0.1, credentials added upstream.

Some tools cannot send a proxy username and password: Chrome's --proxy-server flag,
Selenium with Chrome, many desktop apps, anything that only takes host:port. Point
them at this forwarder instead. It listens on localhost without auth and forwards
every request to your Node4 endpoint with a Proxy-Authorization header added.

    python node4_forwarder.py                      # 127.0.0.1:8899 -> NODE4_GATEWAY
    python node4_forwarder.py --session job42      # hold one exit IP (sticky session)
    python node4_forwarder.py --sessions 3         # ports 8899-8901, one exit IP each
    python node4_forwarder.py --upstream "$NODE4_PROXY"   # a static proxy (IP:4443)

    chrome --proxy-server=http://127.0.0.1:8899

Python 3.8+, standard library only. Handles HTTPS (CONNECT tunnels) and plain HTTP.
Import it to run one inside your own script: see Forwarder below.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import secrets
import sys
import threading

DEFAULT_GATEWAY = "gw-rotating_datacenter.node4.io:8083"
MAX_HEAD = 64 * 1024
CONNECT_TIMEOUT = 15
HOP_HEADERS = {"proxy-authorization", "proxy-connection", "connection", "keep-alive"}


def build_username(user: str, session: str | None = None, country: str | None = None) -> str:
    """USER plus the gateway options: USER-country-us-session-abc123."""
    if country:
        user += f"-country-{country.lower()}"
    if session:
        user += f"-session-{session}"
    return user


def _split_hostport(value: str, default_port: int) -> tuple[str, int]:
    host, sep, port = value.rpartition(":")
    if not sep or not port.isdigit():
        return value, default_port
    return host.strip("[]"), int(port)


async def _read_head(reader: asyncio.StreamReader) -> bytes:
    try:
        return await reader.readuntil(b"\r\n\r\n")
    except asyncio.LimitOverrunError:
        raise ValueError("request head too large")


def _simple_response(status: str, note: str = "") -> bytes:
    body = (note + "\n").encode() if note else b""
    return (
        f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode() + body


class Forwarder:
    """One local listener that forwards to one Node4 endpoint with one username.

    Run it in the background of your own script:

        fwd = Forwarder(user, password, upstream="gw-rotating_datacenter.node4.io:8083",
                        session="abc123")
        port = fwd.start()          # background thread; returns the local port
        ...  use http://127.0.0.1:{port} as a proxy with no credentials ...
        fwd.stop()
    """

    def __init__(self, user: str, password: str, upstream: str = DEFAULT_GATEWAY,
                 session: str | None = None, country: str | None = None,
                 host: str = "127.0.0.1", port: int = 0, verbose: bool = False):
        self.username = build_username(user, session, country)
        token = base64.b64encode(f"{self.username}:{password}".encode()).decode()
        self._auth = f"Proxy-Authorization: Basic {token}\r\n".encode()
        self.upstream = _split_hostport(upstream, 8083)
        self.host, self.port = host, port
        self.verbose = verbose
        self.bytes_up = 0
        self.bytes_down = 0
        self._server: asyncio.AbstractServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def log(self, msg: str) -> None:
        print(f"[:{self.port}] {msg}", file=sys.stderr, flush=True)

    # ---- server lifecycle -------------------------------------------------
    async def serve(self) -> asyncio.AbstractServer:
        """Bind the listener on the running loop. Sets self.port if it was 0."""
        self._server = await asyncio.start_server(self._handle, self.host, self.port, limit=MAX_HEAD)
        self.port = self._server.sockets[0].getsockname()[1]
        return self._server

    def start(self) -> int:
        """Run the forwarder on a background thread. Returns the local port."""
        ready = threading.Event()
        failure: list[BaseException] = []

        def run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self.serve())
            except BaseException as exc:  # report bind errors to the caller
                failure.append(exc)
                ready.set()
                return
            ready.set()
            self._loop.run_forever()
            self._loop.close()

        self._thread = threading.Thread(target=run, name="node4-forwarder", daemon=True)
        self._thread.start()
        ready.wait()
        if failure:
            raise failure[0]
        return self.port

    def stop(self) -> None:
        if self._loop and self._server:
            async def shutdown() -> None:
                self._server.close()
                await self._server.wait_closed()
            asyncio.run_coroutine_threadsafe(shutdown(), self._loop).result(5)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(5)

    # ---- per connection ---------------------------------------------------
    async def _handle(self, c_reader: asyncio.StreamReader, c_writer: asyncio.StreamWriter) -> None:
        u_writer = None
        try:
            head = await asyncio.wait_for(_read_head(c_reader), 30)
            lines = head.decode("latin-1").split("\r\n")
            method, target, _version = lines[0].split(" ", 2)
            try:
                u_reader, u_writer = await asyncio.wait_for(
                    asyncio.open_connection(*self.upstream, limit=MAX_HEAD), CONNECT_TIMEOUT)
            except (OSError, asyncio.TimeoutError) as exc:
                self.log(f"cannot reach {self.upstream[0]}:{self.upstream[1]}: {exc!r}")
                c_writer.write(_simple_response("502 Bad Gateway", "forwarder: upstream unreachable"))
                return

            if method.upper() == "CONNECT":
                await self._tunnel(target, c_reader, c_writer, u_reader, u_writer)
            else:
                await self._plain(lines, c_reader, c_writer, u_reader, u_writer)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ValueError, ConnectionError):
            pass  # client went away or sent garbage
        finally:
            for w in (c_writer, u_writer):
                if w is not None:
                    w.close()

    async def _tunnel(self, target, c_reader, c_writer, u_reader, u_writer) -> None:
        u_writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n".encode()
                       + self._auth + b"\r\n")
        await u_writer.drain()
        reply = await asyncio.wait_for(_read_head(u_reader), 30)
        status = reply.split(b"\r\n", 1)[0].decode("latin-1")
        code = status.split(" ", 2)[1] if " " in status else "?"
        if code != "200":
            if code == "407":
                self.log(f"407 from Node4 for {target}: check NODE4_USER / NODE4_PASS and that "
                         "your plan includes this port. Not retrying.")
            elif self.verbose:
                self.log(f"CONNECT {target} -> {status}")
            reason = status.split(" ", 1)[1] if " " in status else "502 Bad Gateway"
            c_writer.write(_simple_response(reason, f"forwarder: upstream answered {status}"))
            await c_writer.drain()
            return
        c_writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await c_writer.drain()
        up, down = await self._pipe_both(c_reader, c_writer, u_reader, u_writer)
        if self.verbose:
            self.log(f"CONNECT {target} up={up} down={down} bytes")

    async def _plain(self, lines, c_reader, c_writer, u_reader, u_writer) -> None:
        # Plain-HTTP request with an absolute URL. The upstream reads the Proxy-Authorization
        # on each request, so force one request per connection: Connection: close.
        kept = [l for l in lines[1:] if l and l.split(":", 1)[0].strip().lower() not in HOP_HEADERS]
        head = "\r\n".join([lines[0], *kept]).encode("latin-1") + b"\r\n"
        u_writer.write(head + self._auth + b"Connection: close\r\n\r\n")
        await u_writer.drain()
        up, down = await self._pipe_both(c_reader, c_writer, u_reader, u_writer)
        if self.verbose:
            self.log(f"{lines[0].rsplit(' ', 1)[0]} up={up} down={down} bytes")

    async def _pipe_both(self, c_reader, c_writer, u_reader, u_writer) -> tuple[int, int]:
        async def pipe(reader, writer, direction: str) -> int:
            total = 0
            try:
                while True:
                    chunk = await reader.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if direction == "up":
                        self.bytes_up += len(chunk)
                    else:
                        self.bytes_down += len(chunk)
                    writer.write(chunk)
                    await writer.drain()
            except (ConnectionError, OSError):
                pass
            finally:
                try:
                    if writer.can_write_eof():
                        writer.write_eof()
                except (OSError, RuntimeError):
                    pass
            return total

        up, down = await asyncio.gather(pipe(c_reader, u_writer, "up"),
                                        pipe(u_reader, c_writer, "down"))
        return up, down


# ---- command line ---------------------------------------------------------
async def _main(args: argparse.Namespace, user: str, password: str) -> None:
    count = max(1, args.sessions or 1)
    forwarders = []
    for i in range(count):
        session = args.session
        if args.sessions:
            session = secrets.token_hex(6)
        fwd = Forwarder(user, password, upstream=args.upstream, session=session,
                        country=args.country, host=args.host, port=args.port + i,
                        verbose=args.verbose)
        await fwd.serve()
        forwarders.append(fwd)
        note = f"session {session}" if session else "rotating per connection"
        if args.country:
            note += f", country {args.country.lower()}"
        print(f"http://{args.host}:{fwd.port} -> {args.upstream} ({note})", flush=True)
    print("No credentials needed on these ports. Ctrl+C to stop.", flush=True)
    try:
        await asyncio.Event().wait()
    finally:
        up = sum(f.bytes_up for f in forwarders)
        down = sum(f.bytes_down for f in forwarders)
        print(f"\nforwarded {up:,} bytes up, {down:,} bytes down", flush=True)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Local no-auth proxy that forwards to Node4 with your credentials.")
    p.add_argument("--upstream", default=os.environ.get("NODE4_GATEWAY", DEFAULT_GATEWAY),
                   help="Node4 HTTP endpoint (default: NODE4_GATEWAY or %(default)s); a static IP:4443 works too")
    p.add_argument("--host", default="127.0.0.1", help="listen address (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=8899, help="first listen port (default: 8899)")
    p.add_argument("--session", help="sticky session ID: hold one exit IP (rotating, residential)")
    p.add_argument("--sessions", type=int, help="open N ports in a row, each with its own random session")
    p.add_argument("--country", help="exit country, e.g. us (rotating: us, it, es; residential: 170+)")
    p.add_argument("-v", "--verbose", action="store_true", help="log every tunnel with byte counts")
    args = p.parse_args(argv)

    user, password = os.environ.get("NODE4_USER", ""), os.environ.get("NODE4_PASS", "")
    if not user or not password:
        sys.exit("Set NODE4_USER and NODE4_PASS (from https://node4.io/proxies).")
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"WARNING: listening on {args.host} lets anyone who can reach it use your Node4 "
              "account. Keep it behind a firewall.", file=sys.stderr)
    try:
        asyncio.run(_main(args, user, password))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
