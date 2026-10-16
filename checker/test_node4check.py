"""Offline tests for node4check: parsing, the SOCKS5 client, and result classification.

    python -m unittest -v test_node4check.py

Nothing here touches the network: fake proxies listen on 127.0.0.1.
"""
import argparse
import io
import json
import socket
import struct
import threading
import os
import unittest
from unittest import mock

import node4check as nc


class ParseTests(unittest.TestCase):
    def test_host_port_uses_defaults(self):
        p = nc.parse_proxy("203.0.113.10:4443", "alice", "s3cret")
        self.assertEqual((p.host, p.port, p.scheme, p.user, p.password), ("203.0.113.10", 4443, "http", "alice", "s3cret"))
        self.assertFalse(p.explicit_scheme)

    def test_host_port_user_pass(self):
        p = nc.parse_proxy("203.0.113.10:4443:bob:pa:ss", "alice", "x")
        self.assertEqual((p.user, p.password), ("bob", "pa:ss"))

    def test_user_pass_at(self):
        p = nc.parse_proxy("bob:p@ss@203.0.113.10:1443")
        self.assertEqual((p.host, p.port, p.user, p.password), ("203.0.113.10", 1443, "bob", "p@ss"))

    def test_url_percent_decoded(self):
        p = nc.parse_proxy("socks5h://bob:p%40ss%3Aw%2Fd@gw-rotating_datacenter.node4.io:1083")
        self.assertEqual(p.scheme, "socks5h")
        self.assertEqual(p.host, "gw-rotating_datacenter.node4.io")
        self.assertEqual((p.user, p.password), ("bob", "p@ss:w/d"))
        self.assertTrue(p.explicit_scheme)

    def test_url_without_credentials_uses_defaults(self):
        p = nc.parse_proxy("http://203.0.113.10:4443", "alice", "s3cret")
        self.assertEqual((p.user, p.password), ("alice", "s3cret"))

    def test_socks5_means_local_dns(self):
        self.assertEqual(nc.parse_proxy("socks5://1.2.3.4:1443").scheme, "socks5")

    def test_bad_entries(self):
        for bad in ["", "1.2.3.4", "1.2.3.4:0", "1.2.3.4:99999", "1.2.3.4:http", "ftp://1.2.3.4:21",
                    "http://1.2.3.4", "1.2.3.4:80:user", "bad host:80"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                nc.parse_proxy(bad)

    def test_read_entries_skips_comments_and_blanks(self):
        self.assertEqual(nc.read_entries(["# list\n", "\n", "1.2.3.4:4443\n", "  # x\n", " 5.6.7.8:4443 \n"]),
                         ["1.2.3.4:4443", "5.6.7.8:4443"])

    def test_protocol_switch_uses_paired_ports(self):
        p = nc.parse_proxy("gw-rotating_datacenter.node4.io:8083")
        s = nc.with_protocol(p, "socks5")
        self.assertEqual((s.scheme, s.port), ("socks5h", 1083))
        self.assertEqual(nc.with_protocol(s, "http").port, 8083)
        self.assertEqual(nc.with_protocol(nc.parse_proxy("1.2.3.4:4443"), "socks5").port, 1443)
        self.assertEqual(nc.with_protocol(nc.parse_proxy("1.2.3.4:9999"), "socks5").port, 9999)

    def test_extract_ip(self):
        self.assertEqual(nc.extract_ip("203.0.113.9\n"), "203.0.113.9")
        self.assertEqual(nc.extract_ip('{"ip":"203.0.113.9"}'), "203.0.113.9")
        self.assertEqual(nc.extract_ip("2001:db8::1"), "2001:db8::1")
        self.assertIsNone(nc.extract_ip("<html>blocked</html>"))
        self.assertIsNone(nc.extract_ip('{"error": 1}'))


# --------------------------------------------------------------------------- fake servers


class FakeServer:
    """A one-thread TCP server on 127.0.0.1 running handler(conn) for each connection."""

    def __init__(self, handler):
        self.handler = handler
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.seen = []
        self._stop = False
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(5)
                try:
                    self.handler(self, conn)
                except OSError:
                    pass

    def close(self):
        self._stop = True
        self.sock.close()


def recv_exact(conn, n):
    data = b""
    while len(data) < n:
        chunk = conn.recv(n - len(data))
        if not chunk:
            raise OSError("closed")
        data += chunk
    return data


def recv_head(conn):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(4096)
        if not chunk:
            break
        data += chunk
    return data


def http_reply(body: str, status="200 OK") -> bytes:
    return (f"HTTP/1.1 {status}\r\nContent-Type: text/plain\r\nContent-Length: {len(body)}\r\n"
            f"Connection: close\r\n\r\n{body}").encode()


def socks_server(user=b"alice", password=b"s3cret", reply=0, exit_ip="203.0.113.7"):
    """A minimal SOCKS5 server that requires user/pass, then answers one HTTP request itself."""

    def handler(server, conn):
        ver, n = recv_exact(conn, 2)
        methods = recv_exact(conn, n)
        server.seen.append(("methods", methods))
        if 2 not in methods:
            conn.sendall(b"\x05\xff")
            return
        conn.sendall(b"\x05\x02")
        _, ulen = recv_exact(conn, 2)
        u = recv_exact(conn, ulen)
        p = recv_exact(conn, recv_exact(conn, 1)[0])
        server.seen.append(("auth", u, p))
        if (u, p) != (user, password):
            conn.sendall(b"\x01\x01")
            return
        conn.sendall(b"\x01\x00")
        ver, cmd, _, atyp = recv_exact(conn, 4)
        if atyp == 3:
            addr = recv_exact(conn, recv_exact(conn, 1)[0]).decode()
        elif atyp == 1:
            addr = socket.inet_ntoa(recv_exact(conn, 4))
        else:
            addr = recv_exact(conn, 16)
        (port,) = struct.unpack(">H", recv_exact(conn, 2))
        server.seen.append(("connect", cmd, atyp, addr, port))
        conn.sendall(b"\x05" + bytes([reply]) + b"\x00\x01" + socket.inet_aton("0.0.0.0") + b"\x00\x00")
        if reply:
            return
        recv_head(conn)
        conn.sendall(http_reply(exit_ip))

    return FakeServer(handler)


class SocksTests(unittest.TestCase):
    def test_handshake_with_auth_and_remote_dns(self):
        srv = socks_server()
        self.addCleanup(srv.close)
        with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as s:
            nc.socks5_handshake(s, "api.ipify.org", 443, "alice", "s3cret")
        self.assertEqual(srv.seen[0], ("methods", b"\x00\x02"))
        self.assertEqual(srv.seen[1], ("auth", b"alice", b"s3cret"))
        self.assertEqual(srv.seen[2], ("connect", 1, 3, "api.ipify.org", 443))

    def test_ip_target_sent_as_ipv4(self):
        srv = socks_server()
        self.addCleanup(srv.close)
        with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as s:
            nc.socks5_handshake(s, "198.51.100.4", 80, "alice", "s3cret")
        self.assertEqual(srv.seen[2], ("connect", 1, 1, "198.51.100.4", 80))

    def test_full_check_over_socks(self):
        srv = socks_server(exit_ip="203.0.113.7")
        self.addCleanup(srv.close)
        proxy = nc.parse_proxy(f"socks5h://alice:s3cret@127.0.0.1:{srv.port}")
        r = nc.check_one(proxy, "http://example.test/ip", timeout=5)
        self.assertEqual((r.status, r.exit_ip, r.protocol), ("ok", "203.0.113.7", "socks5"))
        self.assertIsNotNone(r.latency_ms)

    def test_wrong_password_is_auth_failed(self):
        srv = socks_server()
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"socks5h://alice:wrong@127.0.0.1:{srv.port}"), "http://x.test/", 5)
        self.assertEqual(r.status, nc.AUTH_FAILED)

    def test_no_credentials_rejected(self):
        srv = socks_server()
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"socks5h://127.0.0.1:{srv.port}"), "http://x.test/", 5)
        self.assertEqual(r.status, nc.AUTH_FAILED)
        self.assertEqual(srv.seen[0], ("methods", b"\x00"))

    def test_connect_failure_reply(self):
        srv = socks_server(reply=5)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"socks5h://alice:s3cret@127.0.0.1:{srv.port}"), "http://x.test/", 5)
        self.assertEqual(r.status, nc.PROXY_ERROR)
        self.assertIn("refused by destination", r.detail)


class HttpProxyTests(unittest.TestCase):
    def test_407_on_connect_is_auth_failed(self):
        def handler(server, conn):
            server.seen.append(recv_head(conn))
            conn.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n"
                         b"Proxy-Authenticate: Basic realm=\"proxy\"\r\nContent-Length: 0\r\n\r\n")

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}", "alice", "bad"), "https://api.ipify.org", 5)
        self.assertEqual(r.status, nc.AUTH_FAILED)
        self.assertIn("407", r.detail)
        head = srv.seen[0].decode()
        self.assertTrue(head.startswith("CONNECT api.ipify.org:443 HTTP/1.1"))
        self.assertIn("Proxy-Authorization: Basic YWxpY2U6YmFk", head)  # alice:bad

    def test_bare_407_with_close_is_auth_failed(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}", "a", "b"), "https://x.test", 5)
        self.assertEqual(r.status, nc.AUTH_FAILED)

    def test_407_on_plain_http_is_auth_failed(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(http_reply("", "407 Proxy Authentication Required"))

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}", "a", "b"), "http://x.test/", 5)
        self.assertEqual(r.status, nc.AUTH_FAILED)

    def test_plain_http_ok_sends_absolute_uri(self):
        def handler(server, conn):
            server.seen.append(recv_head(conn))
            conn.sendall(http_reply('{"ip":"198.51.100.20"}'))

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}", "a", "b"), "http://x.test/ip?format=json", 5)
        self.assertEqual((r.status, r.exit_ip), ("ok", "198.51.100.20"))
        self.assertTrue(srv.seen[0].startswith(b"GET http://x.test/ip?format=json HTTP/1.1"))

    def test_static_exit_mismatch_is_noted(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(http_reply("198.51.100.20"))

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}", "a", "b"), "http://x.test/", 5, expect_exit=True)
        self.assertEqual(r.status, "ok")
        self.assertIn("differs", r.detail)

    def test_non_ip_body_is_bad_response(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(http_reply("<html>captcha</html>"))

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}"), "http://x.test/", 5)
        self.assertEqual(r.status, nc.BAD_RESPONSE)

    def test_502_on_connect_is_proxy_error(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}"), "https://x.test", 5)
        self.assertEqual(r.status, nc.PROXY_ERROR)
        self.assertIn("502", r.detail)


class NetworkFailureTests(unittest.TestCase):
    def test_refused(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()  # nothing listens here now
        # Windows retries a refused SYN for about 2 s, so leave room before the timeout.
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{port}"), "https://x.test", 6)
        self.assertEqual(r.status, nc.REFUSED)

    def test_timeout(self):
        hold = threading.Event()

        def handler(server, conn):
            hold.wait(3)  # accept, then never answer

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        self.addCleanup(hold.set)
        r = nc.check_one(nc.parse_proxy(f"127.0.0.1:{srv.port}"), "https://x.test", 0.5)
        self.assertEqual(r.status, nc.TIMEOUT)
        self.assertIn("handshake", r.detail)


class SummaryTests(unittest.TestCase):
    def _r(self, ip, status="ok"):
        return nc.Result("rotation", "gw:8083", "http", status, exit_ip=ip)

    def test_rotation(self):
        self.assertTrue(nc.rotation_summary([self._r("1.1.1.1"), self._r("2.2.2.2"), self._r("1.1.1.1")]).passed)
        self.assertFalse(nc.rotation_summary([self._r("1.1.1.1")] * 3).passed)
        self.assertFalse(nc.rotation_summary([self._r("", "timeout")] * 3).passed)

    def test_sticky(self):
        self.assertTrue(nc.sticky_summary([self._r("1.1.1.1")] * 3, "s1").passed)
        self.assertFalse(nc.sticky_summary([self._r("1.1.1.1"), self._r("2.2.2.2")], "s1").passed)
        self.assertFalse(nc.sticky_summary([self._r("1.1.1.1"), self._r("", "timeout")], "s1").passed)


@mock.patch.dict(os.environ, {"NODE4_USER": "alice", "NODE4_PASS": "s3cret"})
class CliTests(unittest.TestCase):
    def test_json_output_and_exit_code(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(http_reply("203.0.113.50"))

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        args = nc.build_parser().parse_args([f"127.0.0.1:{srv.port}", "--url", "http://x.test/", "--json"])
        out = io.StringIO()
        self.assertEqual(nc.run(args, out), 0)
        data = json.loads(out.getvalue())
        self.assertEqual(data["summary"], {"checks": 1, "ok": 1, "failed": 0, "gateway_tests_failed": 0})
        self.assertEqual(data["results"][0]["exit_ip"], "203.0.113.50")

    def test_failure_exit_code_and_csv(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        args = nc.build_parser().parse_args([f"127.0.0.1:{port}", "--csv", "-t", "6"])
        out = io.StringIO()
        self.assertEqual(nc.run(args, out), 1)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "check,proxy,protocol,status,exit_ip,latency_ms,country,detail")
        self.assertIn(",refused,", lines[1])

    def test_password_never_printed(self):
        def handler(server, conn):
            recv_head(conn)
            conn.sendall(http_reply("203.0.113.50"))

        srv = FakeServer(handler)
        self.addCleanup(srv.close)
        for fmt in ([], ["--json"], ["--csv"]):
            args = nc.build_parser().parse_args(
                [f"127.0.0.1:{srv.port}:alice:Hunter2Secret", "--url", "http://x.test/"] + fmt)
            out = io.StringIO()
            nc.run(args, out)
            self.assertNotIn("Hunter2Secret", out.getvalue())

    def test_static_proxy_as_gateway_is_refused(self):
        args = nc.build_parser().parse_args(["--gateway", "203.0.113.10:4443"])
        self.assertEqual(nc.run(args, io.StringIO()), 2)

    def test_usage_error(self):
        args = nc.build_parser().parse_args(["not-a-proxy"])
        self.assertEqual(nc.run(args, io.StringIO()), 2)


if __name__ == "__main__":
    unittest.main()
