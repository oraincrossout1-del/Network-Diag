import socket
import unittest
from unittest import mock

from netdiag.probes import build_dns_query, dns_reply_ok, measure_dns_direct, measure_dns_system
from netdiag.utils import format_dns


class DnsPackets(unittest.TestCase):
    def test_query_layout(self):
        q = build_dns_query("google.com", 0x1234)
        self.assertEqual(q[:2], b"\x12\x34")
        self.assertIn(b"\x06google\x03com\x00", q)
        self.assertEqual(q[-4:], b"\x00\x01\x00\x01")  # type A, class IN

    def test_trailing_dot_is_ignored(self):
        self.assertEqual(build_dns_query("google.com.", 1), build_dns_query("google.com", 1))

    def test_reply_checks(self):
        ok = b"\x12\x34\x81\x80" + b"\x00" * 8
        self.assertTrue(dns_reply_ok(ok, 0x1234))
        self.assertFalse(dns_reply_ok(ok, 0x9999))                              # someone else's answer
        self.assertFalse(dns_reply_ok(b"\x12\x34\x81\x83" + b"\x00" * 8, 0x1234))  # NXDOMAIN
        self.assertFalse(dns_reply_ok(b"\x12\x34\x01\x00" + b"\x00" * 8, 0x1234))  # not a response
        self.assertFalse(dns_reply_ok(b"\x12", 0x1234))


class FakeSocket:
    """UDP socket stand-in that answers every query correctly."""
    def __init__(self, *a, **k):
        self.sent = b""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def settimeout(self, t):
        pass

    def sendto(self, packet, addr):
        self.sent = packet

    def recvfrom(self, n):
        return self.sent[:2] + b"\x81\x80" + b"\x00" * 8, ("1.1.1.1", 53)


class DnsMeasurement(unittest.TestCase):
    def test_direct_query_success(self):
        with mock.patch("socket.socket", FakeSocket):
            r = measure_dns_direct("1.1.1.1", ["a.com", "b.com"])
        self.assertEqual((r["failures"], r["total"]), (0, 2))
        self.assertIsNotNone(r["avg"])

    def test_direct_query_timeouts_count_as_failures(self):
        class Silent(FakeSocket):
            def recvfrom(self, n):
                raise socket.timeout()
        with mock.patch("socket.socket", Silent):
            r = measure_dns_direct("1.1.1.1", ["a.com", "b.com"])
        self.assertEqual((r["avg"], r["failures"]), (None, 2))

    def test_system_resolver(self):
        calls = iter([[("x",)], OSError("fail"), [("x",)]])

        def fake(*a, **k):
            v = next(calls)
            if isinstance(v, Exception):
                raise v
            return v
        with mock.patch("socket.getaddrinfo", fake):
            r = measure_dns_system(["a.com", "b.com", "c.com"])
        self.assertEqual((r["failures"], r["total"]), (1, 3))
        self.assertIsNotNone(r["avg"])


class DnsFormatting(unittest.TestCase):
    def test_all_parts(self):
        d = {"avg": 12.0, "failures": 1, "total": 4, "public": {"1.1.1.1": {"avg": 9.0}, "8.8.8.8": {"avg": None}}}
        self.assertEqual(format_dns(d), "12.0 ms (1/4 failed) | public: 1.1.1.1 9.0 ms")

    def test_without_public_and_without_average(self):
        self.assertEqual(format_dns({"avg": None, "failures": 4, "total": 4}), "N/A (4/4 failed)")


if __name__ == "__main__":
    unittest.main()
