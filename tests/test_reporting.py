import contextlib
import io
import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from netdiag.analysis import build_events, calc_stats, collect_findings, summarize
from netdiag.reporting import (build_report_html, hop_table_html, print_console_summary, print_progress,
                               timeline_data, write_json, write_report)
from tests.helpers import DNS_OK, SPEED_OK, samples

HOPS = [{"hop": 1, "ip": "192.168.0.1", "avg_ms": 1.0}, {"hop": 2, "ip": "100.64.0.7", "avg_ms": 9.7},
        {"hop": 3, "ip": None, "avg_ms": None}]


def make_ctx(with_data=True, speed=SPEED_OK):
    raw = {"rapid": samples([10, None, 12, 11]), "tcp": samples([20, 21, None]), "local": samples([1, 1, 1])}
    if not with_data:
        raw = {}
    stats = {k: calc_stats(raw.get(k, [])) for k in ("local", "heavy", "rapid", "secondary", "tcp")}
    findings = collect_findings(stats, speed, False, DNS_OK, [], HOPS, "192.168.0.1")
    return {"target": "8.8.8.8", "secondary": "1.1.1.1", "port": 443, "gateway": "192.168.0.1", "duration": 4,
            "generated": "2026-09-24 12:00:00", "platform": "Test | Python 3", "raw": raw, "stats": stats,
            "hops": HOPS, "dns": DNS_OK, "speed": speed, "bloat": [],
            "ip_info": {"ipv4": "203.0.113.5", "ipv6": "Not detected", "type": "Public"},
            "verdict": summarize(findings, stats, speed), "findings": findings, "events": build_events(raw, stats)}


def embedded_data(page):
    return json.loads(re.search(r"var D = (\{.*?\});\n", page, re.S).group(1))


class HtmlReport(unittest.TestCase):
    def test_is_self_contained(self):
        page = build_report_html(make_ctx())
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link", page)
        self.assertNotIn("cdn.", page)

    def test_scorecard_lists_every_test_and_the_verdict(self):
        page = build_report_html(make_ctx())
        for name in ("Scorecard", "Download speed", "Upload speed", "Jitter", "Connection dropouts", "DNS"):
            self.assertIn(name, page)
        self.assertIn("Network Quality:", page)

    def test_untrusted_text_is_escaped(self):
        page = build_report_html(make_ctx(speed=dict(SPEED_OK, status="Failed <x>", source="<b>")))
        self.assertNotIn("Failed <x>", page)
        self.assertNotIn("<b>speedtest", page)

    def test_lost_probes_are_real_nulls_and_each_series_keeps_its_own_time_axis(self):
        data = embedded_data(build_report_html(make_ctx()))
        by_key = {s["key"]: s for s in data["series"]}
        self.assertIsNone(by_key["rapid"]["pts"][1][1])
        self.assertEqual([p[0] for p in by_key["tcp"]["pts"]], [0.0, 1.0, 2.0])

    def test_renders_without_any_samples(self):
        ctx = make_ctx(with_data=False)
        page = build_report_html(ctx)
        self.assertIn("No samples were collected.", page)
        self.assertIsNone(timeline_data(ctx["raw"], 4, ctx["stats"]))

    def test_hop_table_marks_router_and_cgnat(self):
        table = hop_table_html(HOPS, "192.168.0.1")
        self.assertIn("(your router)", table)
        self.assertIn("CG-NAT range", table)
        self.assertIn("no reply", table)
        self.assertIn("No route data", hop_table_html([], None))


class Files(unittest.TestCase):
    def test_write_report_saves_a_timestamped_file_and_opens_it_on_request(self):
        with tempfile.TemporaryDirectory() as d, mock.patch("webbrowser.open") as opened:
            path = write_report(make_ctx(), Path(d), "20260924_120000", open_browser=True)
            self.assertEqual(path.name, "network_diagnostic_20260924_120000.html")
            self.assertIn("Network Quality", path.read_text(encoding="utf-8"))
            opened.assert_called_once()
            opened.reset_mock()
            write_report(make_ctx(), Path(d), "20260924_120001", open_browser=False)
            opened.assert_not_called()

    def test_json_export(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "r.json"
            write_json(make_ctx(), p)
            j = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(j["verdict"]["grade"], "GOOD")
        self.assertNotIn("windows", j["speed"])  # monotonic timestamps mean nothing outside the run
        self.assertEqual(j["samples"]["tcp"], [[0.0, 20], [1.0, 21], [2.0, None]])
        self.assertEqual({"generated", "findings", "stats", "hops", "events"} - set(j), set())


class Console(unittest.TestCase):
    def test_summary_shows_every_test_and_the_verdict(self):
        ctx = make_ctx()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_console_summary(ctx["findings"], ctx["verdict"])
        out = buf.getvalue()
        self.assertIn("Verdict: GOOD", out)
        self.assertIn("Download speed", out)
        self.assertIn("n/a", out)  # tests that did not run

    def test_progress_bar(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_progress(50, 100)
        self.assertIn("50%", buf.getvalue())
        self.assertIn("50/100s", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
