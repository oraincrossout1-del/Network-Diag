import threading
import unittest
from unittest import mock

from netdiag.probes import build_ping_cmd, drop_trailing_loss, parse_ping_rtt
from netdiag.probes import latency
from tests.helpers import samples


class PingParsing(unittest.TestCase):
    def test_windows_reply(self):
        self.assertEqual(parse_ping_rtt("Reply from 8.8.8.8: bytes=32 time=12ms TTL=118"), 12.0)

    def test_windows_sub_ms(self):
        self.assertEqual(parse_ping_rtt("Reply from 192.168.1.1: bytes=32 time<1ms TTL=64"), 1.0)

    def test_linux_reply(self):
        self.assertEqual(parse_ping_rtt("64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 time=12.3 ms"), 12.3)

    def test_localized_windows_reply(self):
        # Parsing must not depend on the English word "time" (non-English Windows).
        self.assertEqual(parse_ping_rtt("Antwort von 8.8.8.8: Bytes=32 Zeit=15ms TTL=118"), 15.0)

    def test_comma_decimal(self):
        self.assertEqual(parse_ping_rtt("64 bytes from 8.8.8.8: icmp_seq=1 ttl=118 Zeit=12,5 ms"), 12.5)

    def test_timeouts_are_none(self):
        self.assertIsNone(parse_ping_rtt("Request timed out."))
        self.assertIsNone(parse_ping_rtt("Reply from 192.168.1.1: Destination host unreachable."))
        self.assertIsNone(parse_ping_rtt("1 packets transmitted, 0 received, 100% packet loss, time 0ms"))
        self.assertIsNone(parse_ping_rtt(""))


class PingCommand(unittest.TestCase):
    def cmd(self, win, mac):
        with mock.patch.object(latency, "IS_WIN", win), mock.patch.object(latency, "IS_MAC", mac):
            return build_ping_cmd("8.8.8.8", 1400, 500)

    def test_windows(self):
        cmd = self.cmd(True, False)
        self.assertEqual(cmd[cmd.index("-l") + 1], "1400")
        self.assertEqual(cmd[cmd.index("-w") + 1], "500")

    def test_macos_wait_is_milliseconds(self):
        cmd = self.cmd(False, True)
        self.assertEqual(cmd[cmd.index("-W") + 1], "500")

    def test_linux_wait_is_seconds(self):
        cmd = self.cmd(False, False)
        self.assertEqual(cmd[cmd.index("-W") + 1], "1")


class ProbeLoop(unittest.TestCase):
    def test_runs_on_a_fixed_cadence_and_stops(self):
        stop = threading.Event()
        values = iter([10.0, None, 12.0] + [11.0] * 100)
        out = latency._probe_loop(lambda: next(values), 0.05, 0.4, stop)
        self.assertGreaterEqual(len(out), 5)
        self.assertEqual([s["rtt"] for s in out[:3]], [10.0, None, 12.0])
        self.assertTrue(all(b["time"] >= a["time"] for a, b in zip(out, out[1:])))

    def test_stop_event_ends_the_loop_early(self):
        stop = threading.Event()
        stop.set()
        self.assertEqual(latency._probe_loop(lambda: 1.0, 0.05, 30, stop), [])

    def test_tcp_worker_records_failed_connects_as_lost(self):
        stop = threading.Event()
        with mock.patch("socket.create_connection", side_effect=OSError("refused")):
            out = latency.tcp_worker("203.0.113.9", 443, 0.05, 0.2, stop)
        self.assertTrue(out and all(s["rtt"] is None for s in out))


class TrailingLoss(unittest.TestCase):
    def test_drops_only_a_trailing_lost_probe(self):
        self.assertEqual(len(drop_trailing_loss(samples([1, 2, None]))), 2)
        self.assertEqual(len(drop_trailing_loss(samples([1, None, 3]))), 3)
        self.assertEqual(drop_trailing_loss([]), [])


if __name__ == "__main__":
    unittest.main()
