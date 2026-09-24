import http.server
import threading
import unittest
from unittest import mock

from netdiag.analysis import calc_stats, compute_bufferbloat, slice_window
from netdiag.probes import bandwidth, run_speedtest
from tests.helpers import samples


class SpeedtestFallbacks(unittest.TestCase):
    GOOD = {"down": 100.0, "up": 20.0, "ping": 9.0, "windows": {}, "source": "x"}

    def test_first_method_wins(self):
        with mock.patch.object(bandwidth, "_speedtest_cli", return_value=self.GOOD):
            r = run_speedtest()
        self.assertEqual((r["status"], r["down"]), ("Success", 100.0))

    def test_falls_back_when_speedtest_cli_is_not_installed(self):
        with mock.patch.object(bandwidth, "_speedtest_cli", side_effect=ImportError), \
                mock.patch.object(bandwidth, "_speedtest_http", return_value=dict(self.GOOD, down=55.0)):
            r = run_speedtest()
        self.assertEqual((r["status"], r["down"]), ("Success", 55.0))

    def test_both_failing_reports_both_reasons(self):
        with mock.patch.object(bandwidth, "_speedtest_cli", side_effect=ImportError), \
                mock.patch.object(bandwidth, "_speedtest_http", side_effect=RuntimeError("HTTP 403")):
            r = run_speedtest()
        self.assertTrue(r["status"].startswith("Failed ("))
        self.assertIn("not installed", r["status"])
        self.assertIn("HTTP 403", r["status"])
        self.assertIsNone(r["down"])


class _SpeedHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):  # download: stream until the client hangs up
        self.send_response(200)
        self.send_header("Content-Length", "25000000")
        self.end_headers()
        try:
            for _ in range(400):
                self.wfile.write(b"x" * 65536)
        except OSError:
            pass

    def do_POST(self):  # upload: swallow the body
        left = int(self.headers.get("Content-Length", 0))
        while left > 0:
            left -= len(self.rfile.read(min(65536, left)))
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


class BuiltInHttpSpeedtest(unittest.TestCase):
    def test_measures_download_and_upload_against_a_local_server(self):
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _SpeedHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with mock.patch.object(bandwidth, "HTTP_WARMUP_SEC", 0.3), \
                    mock.patch.object(bandwidth, "HTTP_MEASURE_SEC", 0.6):
                r = bandwidth._speedtest_http(f"http://127.0.0.1:{server.server_address[1]}")
        finally:
            server.shutdown()
        self.assertGreater(r["down"], 0)
        self.assertGreater(r["up"], 0)
        for key in ("down", "up"):
            w0, w1 = r["windows"][key]
            self.assertLess(w0, w1)
        self.assertEqual(r["source"], "Cloudflare (built-in)")

    def test_unreachable_server_raises_instead_of_reporting_zero(self):
        with mock.patch.object(bandwidth, "HTTP_WARMUP_SEC", 0.2), \
                mock.patch.object(bandwidth, "HTTP_MEASURE_SEC", 0.2):
            with self.assertRaises(RuntimeError):
                bandwidth._speedtest_http("http://127.0.0.1:9")  # nothing listens on the discard port


class Bufferbloat(unittest.TestCase):
    def stats(self, rtts):
        return calc_stats(samples(rtts))

    def test_needs_enough_samples(self):
        idle = self.stats([20.0] * 10)
        self.assertIsNone(compute_bufferbloat(idle, self.stats([90.0] * 3), "download"))
        self.assertIsNone(compute_bufferbloat(self.stats([20.0, 20.0]), self.stats([90.0] * 10), "download"))
        self.assertIsNone(compute_bufferbloat(idle, calc_stats([]), "download"))

    def test_grades(self):
        idle = self.stats([20.0] * 10)
        for loaded, grade in ((30.0, "Excellent"), (80.0, "Fair"), (200.0, "Poor")):
            b = compute_bufferbloat(idle, self.stats([loaded] * 10), "upload")
            self.assertEqual((b["grade"], b["direction"]), (grade, "upload"))
        self.assertEqual(compute_bufferbloat(idle, self.stats([80.0] * 10), "upload")["increase"], 60.0)

    def test_negative_increase_is_clamped(self):
        b = compute_bufferbloat(self.stats([50.0] * 10), self.stats([20.0] * 10), "download")
        self.assertEqual(b["increase"], 0.0)

    def test_loss_under_load_is_reported(self):
        b = compute_bufferbloat(self.stats([20.0] * 10), self.stats([20.0] * 8 + [None] * 2), "download")
        self.assertEqual((b["loaded_lost"], b["loaded_loss"]), (2, 20.0))

    def test_slice_window_skips_the_ramp_up(self):
        s = samples(list(range(30)), step=1.0)  # abs = 1000 .. 1029
        kept = slice_window(s, 1000, 1020, trim=1.0)
        self.assertEqual(kept[0]["abs"], 1001)
        self.assertEqual(kept[-1]["abs"], 1020)
        # a very short window only loses a quarter of itself
        self.assertEqual(slice_window(s, 1000, 1002, trim=1.0)[0]["abs"], 1001)


if __name__ == "__main__":
    unittest.main()
