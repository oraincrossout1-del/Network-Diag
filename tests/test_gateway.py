import unittest

from netdiag.probes import parse_gateway_linux, parse_gateway_macos, parse_gateway_windows


class GatewayParsing(unittest.TestCase):
    def test_windows_picks_lowest_metric_and_skips_onlink(self):
        out = """
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0         On-link      10.0.0.5      5
          0.0.0.0          0.0.0.0      192.168.1.254   192.168.1.9    50
          0.0.0.0          0.0.0.0      192.168.1.1   192.168.1.50    25
"""
        self.assertEqual(parse_gateway_windows(out), "192.168.1.1")

    def test_windows_no_default_route(self):
        self.assertIsNone(parse_gateway_windows("nothing useful here"))

    def test_linux(self):
        self.assertEqual(parse_gateway_linux("default via 192.168.0.1 dev wlan0 proto dhcp metric 600"), "192.168.0.1")
        self.assertIsNone(parse_gateway_linux(""))

    def test_macos(self):
        out = "   route to: default\ndestination: default\n    gateway: 192.168.1.1\n  interface: en0"
        self.assertEqual(parse_gateway_macos(out), "192.168.1.1")
        self.assertIsNone(parse_gateway_macos("    gateway: link#5"))


if __name__ == "__main__":
    unittest.main()
