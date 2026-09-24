import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from netdiag import cli
from tests.helpers import DNS_OK, SPEED_OK, make_bloat, samples

HOPS = [{"hop": 1, "ip": "192.168.0.1", "avg_ms": 0.9}, {"hop": 2, "ip": "72.14.1.1", "avg_ms": 9.7}]
IP_INFO = {"ipv4": "203.0.113.5", "ipv6": "Not detected", "type": "Public"}


def fake_worker(rtts):
    def worker(target, size_or_port, interval, duration, stop, *rest):
        return samples(rtts)
    return worker


def blocking_worker(target, size_or_port, interval, duration, stop, *rest):
    stop.wait(10)  # like the real workers: runs until the duration ends or `stop` is set
    return samples([12.0] * 10 + [None])


def run_main(*argv, **overrides):
    """Runs main() with the network layer faked. Returns (exit_code, stdout, output_dir_files)."""
    patches = dict(get_default_gateway=lambda: "192.168.0.1", run_traceroute=lambda t: HOPS,
                   run_dns_tests=lambda: DNS_OK, get_ip_info=lambda cgnat: IP_INFO,
                   ping_worker=fake_worker([12.0] * 30), tcp_worker=fake_worker([20.0] * 30))
    patches.update(overrides)
    out = io.StringIO()
    with tempfile.TemporaryDirectory() as d, contextlib.ExitStack() as stack:
        stack.enter_context(mock.patch("shutil.which", return_value="/bin/ping"))
        for name, value in patches.items():
            stack.enter_context(mock.patch.object(cli, name, value))
        with contextlib.redirect_stdout(out):
            code = cli.main(["--duration", "1", "--no-open", "--output-dir", d, *argv])
        files = sorted(p.name for p in Path(d).iterdir())
    return code, out.getvalue(), files


class Arguments(unittest.TestCase):
    def test_defaults(self):
        a = cli.parse_args([])
        self.assertEqual((a.duration, a.target, a.secondary, a.port), (300, "8.8.8.8", "1.1.1.1", 443))
        self.assertFalse(a.no_speedtest or a.no_open or a.json)

    def test_duration_is_at_least_one_second(self):
        self.assertEqual(cli.parse_args(["--duration", "0"]).duration, 1)

    def test_port_is_validated(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.parse_args(["--port", "70000"])

    def test_label_for(self):
        self.assertEqual(cli.label_for("8.8.8.8", "8.8.8.8"), "8.8.8.8")
        self.assertEqual(cli.label_for("dns.google", "8.8.8.8"), "dns.google (8.8.8.8)")


class MainWorkflow(unittest.TestCase):
    def test_full_run_writes_the_report_and_json(self):
        code, out, files = run_main("--no-speedtest", "--json")
        self.assertEqual(code, 0)
        self.assertEqual([f.rsplit(".", 1)[1] for f in files], ["html", "json"])
        self.assertIn("Verdict: GOOD", out)
        self.assertIn("Complete! Report saved to", out)

    def test_bandwidth_phase_results_reach_the_verdict(self):
        code, out, _ = run_main(run_bandwidth_phase=lambda target: (SPEED_OK, [make_bloat("upload", increase=150.0)]))
        self.assertEqual(code, 0)
        self.assertIn("Verdict: BAD", out)
        self.assertIn("Latency during upload", out)

    def test_failed_speedtest_is_reported_but_does_not_stop_the_run(self):
        failed = {"down": None, "up": None, "ping": None, "status": "Failed (x)", "windows": {}, "source": None}
        code, out, _ = run_main(run_bandwidth_phase=lambda target: (failed, []))
        self.assertEqual(code, 0)
        self.assertIn("Speedtest failed: Failed (x)", out)

    def test_ctrl_c_during_the_stress_test_still_produces_a_report(self):
        code, out, files = run_main("--no-speedtest", ping_worker=blocking_worker, tcp_worker=blocking_worker,
                                    print_progress=mock.Mock(side_effect=KeyboardInterrupt))
        self.assertEqual(code, 0)
        self.assertIn("Interrupted - analysing the data collected so far", out)
        self.assertEqual(len(files), 1)

    def test_ctrl_c_before_the_stress_test_cancels(self):
        code, out, files = run_main("--no-speedtest", run_dns_tests=mock.Mock(side_effect=KeyboardInterrupt))
        self.assertEqual((code, files), (1, []))
        self.assertIn("Cancelled", out)

    def test_undetected_gateway_skips_only_the_router_test(self):
        code, out, _ = run_main("--no-speedtest", get_default_gateway=lambda: None)
        self.assertEqual(code, 0)
        self.assertIn("NOT DETECTED", out)
        self.assertRegex(out, r"Local router loss\s+n/a")

    def test_missing_traceroute_is_explained(self):
        code, out, _ = run_main("--no-speedtest", run_traceroute=lambda t: None)
        self.assertEqual(code, 0)
        self.assertIn("route checks skipped", out)

    def test_secondary_same_as_primary_is_skipped(self):
        _, out, _ = run_main("--no-speedtest", "--secondary", "8.8.8.8")
        self.assertIn("Secondary target is the same as the primary", out)

    def test_crashed_probe_is_skipped_not_fatal(self):
        def crashing(*a, **k):
            raise RuntimeError("boom")
        code, out, _ = run_main("--no-speedtest", tcp_worker=crashing)
        self.assertEqual(code, 0)
        self.assertIn("The 'tcp' probe crashed and was skipped: boom", out)


class PreflightChecks(unittest.TestCase):
    def run_preflight(self, which, **overrides):
        out = io.StringIO()
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch("shutil.which", return_value=which))
            for name, value in overrides.items():
                stack.enter_context(mock.patch.object(cli, name, value))
            with contextlib.redirect_stdout(out):
                code = cli.main(["--no-speedtest", "--no-open"])
        return code, out.getvalue()

    def test_missing_ping_command(self):
        code, out = self.run_preflight(None)
        self.assertEqual(code, 2)
        self.assertIn("'ping' command was not found", out)

    def test_unresolvable_target(self):
        code, out = self.run_preflight("/bin/ping", resolve_ipv4=lambda host: None)
        self.assertEqual(code, 2)
        self.assertIn("Could not resolve", out)

    def test_unusable_output_folder(self):
        with tempfile.NamedTemporaryFile() as f:
            out = io.StringIO()
            with mock.patch("shutil.which", return_value="/bin/ping"), contextlib.redirect_stdout(out):
                code = cli.main(["--output-dir", str(Path(f.name) / "sub")])
        self.assertEqual(code, 2)
        self.assertIn("Cannot use output folder", out.getvalue())


if __name__ == "__main__":
    unittest.main()
