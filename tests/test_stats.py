import unittest

from netdiag.analysis import calc_stats
from tests.helpers import samples


class Stats(unittest.TestCase):
    def test_empty(self):
        s = calc_stats([])
        self.assertEqual(s["n"], 0)
        self.assertIsNone(s["loss"])
        self.assertIsNone(s["avg"])

    def test_all_lost(self):
        s = calc_stats(samples([None] * 10))
        self.assertEqual((s["loss"], s["received"], s["lost"]), (100.0, 0, 10))
        self.assertIsNone(s["avg"])
        self.assertEqual(s["max_burst"], 10)

    def test_loss_and_burst(self):
        s = calc_stats(samples([10, None, None, 10, None, 10, 10, 10, 10, 10]))
        self.assertEqual(s["loss"], 30.0)
        self.assertEqual(s["lost"], 3)
        self.assertEqual(s["max_burst"], 2)

    def test_jitter_is_mean_difference_of_consecutive_replies(self):
        self.assertEqual(calc_stats(samples([10, 20, 10, 20]))["jitter"], 10.0)

    def test_p99_catches_spikes_but_ignores_a_single_outlier(self):
        self.assertEqual(calc_stats(samples([10] * 90 + [300] * 10))["p99"], 300.0)
        s = calc_stats(samples([10] * 199 + [900]))
        self.assertEqual((s["p99"], s["max"], s["min"]), (10.0, 900.0, 10.0))

    def test_outage_needs_three_consecutive_losses(self):
        self.assertEqual(calc_stats(samples([10, None, None, 10, 10]))["max_outage_s"], 0.0)
        s = calc_stats(samples([10, None, None, None, 10]))
        self.assertEqual(s["outages"], [{"start": 1.0, "probes": 3, "duration": 3.0}])
        self.assertEqual(s["max_outage_s"], 3.0)

    def test_outage_length_uses_real_time_not_sample_count(self):
        # 10 probes/second: 30 lost probes = about 3 seconds
        s = calc_stats(samples([10] * 20 + [None] * 30 + [10] * 20, step=0.1))
        self.assertAlmostEqual(s["max_outage_s"], 3.0, places=1)

    def test_every_outage_is_logged(self):
        s = calc_stats(samples([10, None, None, None, 10, 10, None, None, None, None, 10]))
        self.assertEqual([o["probes"] for o in s["outages"]], [3, 4])


if __name__ == "__main__":
    unittest.main()
