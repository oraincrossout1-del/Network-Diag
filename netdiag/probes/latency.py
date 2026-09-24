"""Active latency probes: ICMP ping and TCP connect, run on a fixed cadence."""

import math
import re
import socket
import time

from netdiag.config import IS_MAC, IS_WIN
from netdiag.utils import run_cmd


PING_RTT_RE = re.compile(r"[=<]\s*([0-9]+(?:[.,][0-9]+)?)\s*ms", re.IGNORECASE)


def build_ping_cmd(target, size, timeout_ms=1000):
    if IS_WIN:
        return ["ping", "-n", "1", "-w", str(timeout_ms), "-l", str(size), target]
    if IS_MAC:  # macOS -W is in MILLISECONDS (Linux's is seconds)
        return ["ping", "-c", "1", "-W", str(timeout_ms), "-s", str(size), target]
    return ["ping", "-c", "1", "-W", str(max(1, math.ceil(timeout_ms / 1000))),
            "-s", str(size), target]


def parse_ping_rtt(output):
    """Locale independent: looks for '=12ms' / '<1ms' / '= 12.3 ms', not the word 'time'."""
    m = PING_RTT_RE.search(output)
    return float(m.group(1).replace(",", ".")) if m else None


def _probe_loop(probe, interval, duration, stop_event):
    """Calls probe() -> rtt_ms|None on a fixed cadence until the duration ends or stop is set."""
    samples = []
    start = time.monotonic()
    next_tick = start
    while not stop_event.is_set() and time.monotonic() - start < duration:
        t0 = time.monotonic()
        samples.append({"time": round(t0 - start, 2), "abs": t0, "rtt": probe()})
        next_tick += interval  # fixed cadence: don't let probe duration stretch the interval
        delay = next_tick - time.monotonic()
        if delay > 0:
            stop_event.wait(delay)
        else:
            next_tick = time.monotonic()
    return samples


def ping_worker(target, size, interval, duration, stop_event, timeout_ms=1000):
    cmd = build_ping_cmd(target, size, timeout_ms)
    return _probe_loop(lambda: parse_ping_rtt(run_cmd(cmd, timeout_ms / 1000 + 3)),
                       interval, duration, stop_event)


def tcp_worker(target, port, interval, duration, stop_event, timeout=1.0):
    def probe():
        # perf_counter, not monotonic: on Windows (Python < 3.13) monotonic() only ticks every
        # ~15.6 ms, which would round every TCP/DNS timing to a multiple of 15.6 ms.
        t0 = time.perf_counter()
        try:
            with socket.create_connection((target, port), timeout=timeout):
                return round((time.perf_counter() - t0) * 1000, 1)
        except OSError:
            return None
    return _probe_loop(probe, interval, duration, stop_event)


def drop_trailing_loss(samples):
    """Ctrl+C also kills any ping process that is mid-flight; its empty output would be
    counted as a fake lost packet at the very end of the series."""
    if samples and samples[-1]["rtt"] is None:
        return samples[:-1]
    return samples
