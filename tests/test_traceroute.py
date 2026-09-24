import unittest
from unittest import mock

from netdiag.probes import build_trace_cmd, detect_cgnat, parse_traceroute
from netdiag.probes import traceroute

WINDOWS = """
Tracing route to 8.8.8.8 over a maximum of 15 hops

  1    <1 ms    <1 ms    <1 ms  192.168.1.1
  2     8 ms     7 ms     9 ms  100.64.0.1
  3     *        *        *     Request timed out.
  4    12 ms    11 ms     *     10.20.30.40

Trace complete.
"""
LINUX = """traceroute to 8.8.8.8 (8.8.8.8), 15 hops max, 60 byte packets
 1  192.168.1.1  0.512 ms  0.483 ms  0.470 ms
 2  10.1.2.3  8.1 ms  8.3 ms  8.0 ms
 3  * * *
 4  72.14.1.1  9.1 ms  9.5 ms  9.9 ms
"""
TRACEPATH = """ 1?: [LOCALHOST]                      pmtu 1500
 1:  192.168.1.1                                           0.9ms
 1:  192.168.1.1                                           0.8ms
 2:  100.64.0.1                                            9.9ms
 3:  no reply
     Resume: pmtu 1500
"""


class TracerouteParsing(unittest.TestCase):
    def test_windows_layout(self):
        hops = parse_traceroute(WINDOWS)
        self.assertEqual([h["hop"] for h in hops], [1, 2, 3, 4])
        self.assertEqual(hops[0]["ip"], "192.168.1.1")
        self.assertEqual(hops[1]["avg_ms"], 8.0)
        self.assertIsNone(hops[2]["ip"])
        self.assertEqual(hops[3]["avg_ms"], 11.5)  # the '*' probe is ignored

    def test_linux_layout_ip_comes_first(self):
        hops = parse_traceroute(LINUX)
        self.assertEqual([h["ip"] for h in hops], ["192.168.1.1", "10.1.2.3", None, "72.14.1.1"])
        self.assertAlmostEqual(hops[0]["avg_ms"], 0.5, places=1)

    def test_tracepath_repeated_hop_lines_are_merged(self):
        hops = parse_traceroute(TRACEPATH)
        self.assertEqual([h["hop"] for h in hops], [1, 2, 3])
        self.assertEqual(hops[0]["ip"], "192.168.1.1")
        self.assertAlmostEqual(hops[0]["avg_ms"], 0.9, places=1)
        self.assertIsNone(hops[2]["ip"])

    def test_empty_output(self):
        self.assertEqual(parse_traceroute(""), [])


class TraceCommand(unittest.TestCase):
    def test_windows_uses_tracert(self):
        with mock.patch.object(traceroute, "IS_WIN", True):
            self.assertEqual(build_trace_cmd("8.8.8.8")[0], "tracert")

    def test_none_when_no_tool_is_installed(self):
        with mock.patch.object(traceroute, "IS_WIN", False), mock.patch("shutil.which", return_value=None):
            self.assertIsNone(build_trace_cmd("8.8.8.8"))

    def test_run_traceroute_reports_missing_tool_as_none(self):
        with mock.patch.object(traceroute, "build_trace_cmd", return_value=None):
            self.assertIsNone(traceroute.run_traceroute("8.8.8.8"))


class CgnatDetection(unittest.TestCase):
    hop = staticmethod(lambda ip: [{"hop": 1, "ip": ip, "avg_ms": 1}])

    def test_detects_range(self):
        for ip in ("100.64.0.1", "100.100.5.5", "100.127.255.254"):
            self.assertTrue(detect_cgnat(self.hop(ip)), ip)

    def test_ignores_outside_range(self):
        for ip in ("100.63.255.255", "100.128.0.1", "10.0.0.1", "192.168.1.1", None):
            self.assertFalse(detect_cgnat(self.hop(ip)), ip)

    def test_no_hops(self):
        self.assertFalse(detect_cgnat([]))
        self.assertFalse(detect_cgnat(None))


if __name__ == "__main__":
    unittest.main()
