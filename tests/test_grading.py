import unittest
from unittest import mock

from netdiag.analysis import calc_stats, collect_findings, grading, rate_high, rate_loss, rate_low
from netdiag.config import COLOR_BAD, COLOR_GOOD, COLOR_MEDIUM
from tests.helpers import DNS_OK, SPEED_OK, SPEED_SKIPPED, make_bloat, make_stats, verdict

SLOW_HOP = [{"hop": 1, "ip": "192.168.0.1", "avg_ms": 1.0}, {"hop": 2, "ip": "100.64.0.7", "avg_ms": 150.0}]


class Rating(unittest.TestCase):
    def test_rate_high(self):
        self.assertEqual([rate_high(v, "jitter_ms") for v in (None, 0, 14.9, 15, 39.9, 40)], [None, 0, 0, 1, 1, 2])

    def test_rate_low(self):
        self.assertEqual([rate_low(v, "download_mbps_below") for v in (None, 100, 25, 24.9, 5, 4.9)],
                         [None, 0, 0, 1, 1, 2])

    def test_a_single_lost_probe_is_noise_not_loss(self):
        self.assertEqual(rate_loss(3.3, 1, "loss_pct"), 0)  # 1 of 30 probes would read as "3.3% = BAD"
        self.assertEqual(rate_loss(3.3, 2, "loss_pct"), 2)
        self.assertIsNone(rate_loss(None, 0, "loss_pct"))


class OverallGrade(unittest.TestCase):
    def test_healthy_network_is_good(self):
        q, color, text = verdict()
        self.assertEqual((q, color), ("GOOD", COLOR_GOOD))
        self.assertIn("0.0% packet loss", text)

    def test_one_severe_result_forces_bad(self):
        """Everything else perfect, exactly ONE severe problem -> overall BAD."""
        cases = {
            "download": dict(speed=dict(SPEED_OK, down=3.0)),
            "upload": dict(speed=dict(SPEED_OK, up=1.0)),
            "bufferbloat download": dict(bloat=[make_bloat("download", increase=150.0)]),
            "bufferbloat upload": dict(bloat=[make_bloat("upload", increase=150.0)]),
            "loss under load": dict(bloat=[make_bloat(lost=6)]),
            "internet loss": dict(stats=make_stats(heavy=[20.0] * 90 + [None] * 10)),
            "tcp loss": dict(stats=make_stats(tcp=[20.0] * 90 + [None] * 10)),
            "local loss": dict(stats=make_stats(local=[1.0] * 95 + [None] * 5)),
            "local latency": dict(stats=make_stats(local=[80.0] * 100)),
            "avg latency": dict(stats=make_stats(rapid=[250.0] * 100)),
            "latency spikes": dict(stats=make_stats(rapid=[20.0] * 90 + [300.0] * 10)),
            "jitter": dict(stats=make_stats(rapid=[20.0, 80.0] * 50)),
            "dropout": dict(stats=make_stats(rapid=[20.0] * 297 + [None] * 3)),
            "first hop": dict(hops=SLOW_HOP, gateway="192.168.0.1"),
            "dns down": dict(dns={"avg": None, "failures": 4, "total": 4, "public": {}}),
            "dns very slow": dict(dns={"avg": 500.0, "failures": 0, "total": 4, "public": {}}),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                self.assertEqual(verdict(**kwargs)[0], "BAD")

    def test_mild_problems_are_medium(self):
        cases = {
            "download": dict(speed=dict(SPEED_OK, down=10.0)),
            "upload": dict(speed=dict(SPEED_OK, up=5.0)),
            "bufferbloat": dict(bloat=[make_bloat(increase=80.0)]),
            "internet loss": dict(stats=make_stats(rapid=[20.0] * 98 + [None] * 2)),
            "local loss": dict(stats=make_stats(local=[1.0] * 398 + [None] * 2)),
            "avg latency": dict(stats=make_stats(rapid=[120.0] * 100)),
            "latency spikes": dict(stats=make_stats(rapid=[20.0] * 90 + [150.0] * 10)),
            "jitter": dict(stats=make_stats(rapid=[20.0, 45.0] * 50)),
            "dns partly failing": dict(dns={"avg": 20.0, "failures": 1, "total": 4, "public": {}}),
            "dns slow": dict(dns={"avg": 150.0, "failures": 0, "total": 4, "public": {}}),
            "cg-nat": dict(cgnat=True),
            "tcp blocked": dict(stats=make_stats(tcp=[None] * 100)),
            "large pings blocked": dict(stats=make_stats(heavy=[None] * 100)),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                self.assertEqual(verdict(**kwargs)[0], "MEDIUM")

    def test_bad_beats_medium_but_medium_findings_are_still_listed(self):
        q, color, text = verdict(stats=make_stats(heavy=[20.0] * 90 + [None] * 10), speed=dict(SPEED_OK, down=10.0))
        self.assertEqual((q, color), ("BAD", COLOR_BAD))
        self.assertTrue(text.startswith("At least one test shows a severe problem."))
        self.assertIn("packet loss", text)
        self.assertIn("Download speed", text)

    def test_medium_colour(self):
        self.assertEqual(verdict(cgnat=True)[1], COLOR_MEDIUM)


class SpecificBehaviours(unittest.TestCase):
    def test_bufferbloat_message_names_the_direction(self):
        _, _, text = verdict(bloat=[make_bloat("upload", increase=150.0)])
        self.assertIn("during an upload", text)
        self.assertIn("SQM", text)

    def test_a_lone_dropped_probe_is_ignored(self):
        self.assertEqual(verdict(stats=make_stats(rapid=[20.0] * 99 + [None]))[0], "GOOD")

    def test_probe_types_that_get_no_reply_are_filtered_not_lossy(self):
        q, _, text = verdict(stats=make_stats(heavy=[None] * 100))
        self.assertEqual(q, "MEDIUM")
        self.assertIn("1400-byte pings get no reply", text)
        self.assertNotIn("100.0%", text)

    def test_router_ignoring_ping_is_not_a_failure(self):
        self.assertEqual(verdict(stats=make_stats(local=[None] * 100))[0], "GOOD")

    def test_local_test_skipped_is_not_a_failure(self):
        stats = make_stats()
        stats["local"] = calc_stats([])
        self.assertEqual(verdict(stats=stats)[0], "GOOD")

    def test_total_outage(self):
        dead = [None] * 50
        q, _, text = verdict(stats=make_stats(heavy=dead, rapid=dead, secondary=dead, tcp=dead))
        self.assertEqual(q, "BAD")
        self.assertIn("router answers", text)

    def test_skipped_speedtest_is_not_penalised_but_noted(self):
        q, _, text = verdict(speed=SPEED_SKIPPED)
        self.assertEqual(q, "GOOD")
        self.assertIn("not tested", text)

    def test_cgnat_can_be_switched_off(self):
        with mock.patch.object(grading, "CGNAT_AFFECTS_GRADE", False):
            self.assertEqual(verdict(cgnat=True)[0], "GOOD")

    def test_dns_suggests_a_faster_public_resolver(self):
        slow = {"avg": 150.0, "failures": 0, "total": 4, "public": {"1.1.1.1": {"avg": 10.0, "failures": 0, "total": 4}}}
        _, _, text = verdict(dns=slow)
        self.assertIn("1.1.1.1 answers in 10.0 ms", text)

    def test_slow_first_isp_hop_is_found_beyond_the_gateway(self):
        _, _, text = verdict(hops=SLOW_HOP, gateway="192.168.0.1")
        self.assertIn("100.64.0.7", text)


class Findings(unittest.TestCase):
    def test_one_row_per_test_with_valid_levels(self):
        rows = collect_findings(make_stats(), SPEED_OK, False, DNS_OK)
        names = [r["test"] for r in rows]
        for expected in ("Download speed", "Upload speed", "Internet packet loss", "Jitter", "DNS", "IP type"):
            self.assertIn(expected, names)
        for r in rows:
            self.assertIn(r["level"], (None, 0, 1, 2))
            if not r["level"]:
                self.assertEqual(r["message"], "")

    def test_tests_that_did_not_run_have_no_level(self):
        by_name = {r["test"]: r for r in collect_findings(make_stats(), SPEED_SKIPPED, False, None)}
        self.assertIsNone(by_name["Download speed"]["level"])
        self.assertIsNone(by_name["DNS"]["level"])
        self.assertIsNone(by_name["First ISP hop latency"]["level"])


if __name__ == "__main__":
    unittest.main()
