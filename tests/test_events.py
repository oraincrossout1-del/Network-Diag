import unittest

from netdiag.analysis import build_events, calc_stats, find_spikes
from tests.helpers import samples


class Spikes(unittest.TestCase):
    def test_needs_the_floor_and_three_times_the_median(self):
        s = samples([10.0] * 50 + [90.0] + [10.0] * 50)
        self.assertEqual(find_spikes(s), [])  # 90 ms is under the 100 ms floor
        s = samples([10.0] * 50 + [150.0] + [10.0] * 50)
        self.assertEqual([p["rtt"] for p in find_spikes(s)], [150.0])

    def test_spikes_are_spread_out(self):
        rtts = [10.0] * 60
        rtts[10], rtts[11], rtts[40] = 300.0, 280.0, 250.0
        picked = find_spikes(samples(rtts), min_gap_s=2.0)
        self.assertEqual([p["time"] for p in picked], [10.0, 40.0])  # 11.0 is too close to 10.0

    def test_nothing_without_replies(self):
        self.assertEqual(find_spikes(samples([None] * 5)), [])


class Events(unittest.TestCase):
    def test_outages_and_spikes_are_listed_in_time_order(self):
        rapid = [10.0] * 30 + [None] * 4 + [10.0] * 30
        rapid[50] = 400.0
        raw = {"rapid": samples(rapid, step=1.0)}
        stats = {"rapid": calc_stats(raw["rapid"])}
        ev = build_events(raw, stats)
        self.assertEqual([e["kind"] for e in ev], ["Outage", "Spike"])
        self.assertEqual(ev[0]["source"], "Internet 32B ping")
        self.assertIn("4 probes lost in a row", ev[0]["detail"])
        self.assertEqual(ev[1]["detail"], "400.0 ms")

    def test_router_uses_a_lower_spike_floor(self):
        rtts = [1.0] * 40
        rtts[20] = 60.0
        raw = {"local": samples(rtts)}
        ev = build_events(raw, {"local": calc_stats(raw["local"])})
        self.assertEqual([e["source"] for e in ev], ["Local router"])

    def test_capped(self):
        rtts = ([10.0] * 5 + [None] * 3) * 20
        raw = {"rapid": samples(rtts)}
        self.assertEqual(len(build_events(raw, {"rapid": calc_stats(raw["rapid"])}, max_events=5)), 5)


if __name__ == "__main__":
    unittest.main()
