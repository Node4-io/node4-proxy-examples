"""Tests for node4_forwarder.py. Standard library only.

    python -m unittest -v test_forwarder.py

The offline tests run against a fake upstream proxy on localhost. The live test runs
only when NODE4_USER and NODE4_PASS are set and NODE4_LIVE=1, and makes one request
through your real Node4 endpoint.
"""
import asyncio
import base64
import json
import os
import socket
import unittest
import urllib.request

from node4_forwarder import Forwarder, build_username


class FakeUpstream:
    """A tiny HTTP proxy that records what it receives.

    CONNECT: answers `connect_status`; on 200, echoes the tunnel bytes back upper-cased.
    Plain HTTP: answers 200 with body "plain-ok".
    """

    def __init__(self, connect_status="200 Connection established"):
        self.connect_status = connect_status
        self.heads = []
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def handle(self, reader, writer):
        head = (await reader.readuntil(b"\r\n\r\n")).decode("latin-1")
        self.heads.append(head)
        if head.startswith("CONNECT"):
            writer.write(f"HTTP/1.1 {self.connect_status}\r\n\r\n".encode())
            await writer.drain()
            if self.connect_status.startswith("200"):
                data = await reader.read(1024)
                writer.write(data.upper())
                await writer.drain()
        else:
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\nplain-ok")
            await writer.drain()
        writer.close()


def auth_header(user, password):
    return "Proxy-Authorization: Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


class ForwarderTests(unittest.IsolatedAsyncioTestCase):
    async def start_pair(self, connect_status="200 Connection established", **kw):
        upstream = FakeUpstream(connect_status)
        up_port = await upstream.start()
        fwd = Forwarder("alice", "s3cret", upstream=f"127.0.0.1:{up_port}", **kw)
        await fwd.serve()
        self.addAsyncCleanup(self.close, upstream, fwd)
        return upstream, fwd

    async def close(self, upstream, fwd):
        upstream.server.close()
        fwd._server.close()

    async def roundtrip(self, port, payload, tail=b""):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(payload)
        await writer.drain()
        reply = await reader.readuntil(b"\r\n\r\n")
        if tail:
            writer.write(tail)
            await writer.drain()
        rest = await asyncio.wait_for(reader.read(), 5)
        writer.close()
        return reply.decode("latin-1"), rest

    def test_username_options(self):
        self.assertEqual(build_username("bob"), "bob")
        self.assertEqual(build_username("bob", session="abc"), "bob-session-abc")
        self.assertEqual(build_username("bob", session="abc", country="US"), "bob-country-us-session-abc")

    async def test_connect_adds_credentials_and_tunnels(self):
        upstream, fwd = await self.start_pair(session="s1")
        reply, rest = await self.roundtrip(
            fwd.port, b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n\r\n", tail=b"hello")
        self.assertTrue(reply.startswith("HTTP/1.1 200"))
        self.assertEqual(rest, b"HELLO")
        head = upstream.heads[0]
        self.assertTrue(head.startswith("CONNECT example.com:443 HTTP/1.1"))
        self.assertIn(auth_header("alice-session-s1", "s3cret"), head)
        self.assertEqual((fwd.bytes_up, fwd.bytes_down), (5, 5))

    async def test_plain_http_replaces_client_auth_and_closes(self):
        upstream, fwd = await self.start_pair()
        reply, rest = await self.roundtrip(
            fwd.port,
            b"GET http://example.com/ HTTP/1.1\r\nHost: example.com\r\n"
            b"Proxy-Authorization: Basic d3Jvbmc=\r\nProxy-Connection: keep-alive\r\n\r\n")
        self.assertTrue(reply.startswith("HTTP/1.1 200"))
        self.assertEqual(rest, b"plain-ok")
        head = upstream.heads[0]
        self.assertIn(auth_header("alice", "s3cret"), head)
        self.assertNotIn("d3Jvbmc=", head)
        self.assertNotIn("Proxy-Connection", head)
        self.assertIn("Connection: close", head)

    async def test_upstream_407_is_passed_back(self):
        _, fwd = await self.start_pair("407 Proxy Authentication Required")
        reply, _ = await self.roundtrip(fwd.port, b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        self.assertTrue(reply.startswith("HTTP/1.1 407"))

    async def test_unreachable_upstream_gives_502(self):
        with socket.socket() as s:  # find a port with nothing listening
            s.bind(("127.0.0.1", 0))
            dead = s.getsockname()[1]
        fwd = Forwarder("alice", "s3cret", upstream=f"127.0.0.1:{dead}")
        await fwd.serve()
        self.addCleanup(fwd._server.close)
        reply, _ = await self.roundtrip(fwd.port, b"CONNECT example.com:443 HTTP/1.1\r\n\r\n")
        self.assertTrue(reply.startswith("HTTP/1.1 502"))


class ThreadModeTest(unittest.TestCase):
    def test_start_and_stop_in_background(self):
        fwd = Forwarder("alice", "s3cret", upstream="127.0.0.1:9")
        port = fwd.start()
        self.assertGreater(port, 0)
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            pass
        fwd.stop()


@unittest.skipUnless(os.environ.get("NODE4_LIVE") == "1" and os.environ.get("NODE4_USER"),
                     "set NODE4_LIVE=1 with NODE4_USER/NODE4_PASS to run against Node4")
class LiveTest(unittest.TestCase):
    def test_exit_ip_through_node4(self):
        upstream = os.environ.get("NODE4_GATEWAY", "gw-rotating_datacenter.node4.io:8083")
        fwd = Forwarder(os.environ["NODE4_USER"], os.environ["NODE4_PASS"], upstream=upstream)
        port = fwd.start()
        try:
            proxy = f"http://127.0.0.1:{port}"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
            with opener.open("https://api.ipify.org?format=json", timeout=30) as resp:
                ip = json.load(resp)["ip"]
            print(f"\nexit IP via forwarder: {ip}")
            self.assertTrue(ip)
        finally:
            fwd.stop()


if __name__ == "__main__":
    unittest.main()
