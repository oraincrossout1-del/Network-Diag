"""Orchestration helpers for the test phases (probes + analysis glued together)."""

import concurrent.futures
import threading
import time

from netdiag.analysis import calc_stats, compute_bufferbloat, slice_window
from netdiag.config import IDLE_BASELINE_SEC, LOAD_PROBE_INTERVAL_SEC
from netdiag.probes import ping_worker, run_speedtest


def safe_result(future, name=""):
    try:
        return future.result()
    except Exception as exc:
        print(f"\n[!] The '{name}' probe crashed and was skipped: {exc}")
        return []


def run_bandwidth_phase(target):
    """Speedtest with a latency probe running the whole time: the first seconds give the
    idle baseline, the download/upload windows give the loaded latency."""
    stop = threading.Event()
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        future = ex.submit(ping_worker, target, 32, LOAD_PROBE_INTERVAL_SEC, 900, stop, 1000)
        try:  # finally: makes sure Ctrl+C can never leave the probe thread running
            stop.wait(IDLE_BASELINE_SEC)
            idle_end = time.monotonic()
            speed = run_speedtest()
        finally:
            stop.set()
        samples = safe_result(future, "load latency")
    idle = calc_stats([s for s in samples if s["abs"] <= idle_end])
    bloat = []
    for direction, key in (("download", "down"), ("upload", "up")):
        window = speed["windows"].get(key)
        if window:
            b = compute_bufferbloat(idle, calc_stats(slice_window(samples, *window)), direction)
            if b:
                bloat.append(b)
    return speed, bloat
