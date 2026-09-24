"""Bandwidth test: speedtest-cli when installed, otherwise a built-in Cloudflare HTTP test."""

import http.client
import os
import threading
import time
import urllib.parse

from netdiag.config import (
    HTTP_MEASURE_SEC,
    HTTP_SPEED_BASE,
    HTTP_STREAMS,
    HTTP_USER_AGENT,
    HTTP_WARMUP_SEC,
)


def _speedtest_cli():
    import speedtest  # pip install speedtest-cli  (ImportError is handled by the caller)
    st = speedtest.Speedtest(secure=True)
    st.get_best_server()
    t0 = time.monotonic()
    down = st.download()
    t1 = time.monotonic()
    up = st.upload()
    t2 = time.monotonic()
    return {"down": round(down / 1_000_000, 2), "up": round(up / 1_000_000, 2),
            "ping": round(st.results.ping, 1), "windows": {"down": (t0, t1), "up": (t1, t2)},
            "source": "speedtest-cli"}


def _http_connection(parts):
    cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    return cls(parts.netloc, timeout=10)


def _download_stream(base, stop, state, lock):
    parts = urllib.parse.urlsplit(base)
    while not stop.is_set():
        conn = None
        try:
            conn = _http_connection(parts)
            conn.request("GET", "/__down?bytes=25000000", headers={"User-Agent": HTTP_USER_AGENT})
            resp = conn.getresponse()
            if resp.status != 200:
                raise OSError(f"HTTP {resp.status}")
            while not stop.is_set():
                chunk = resp.read(65536)
                if not chunk:
                    break
                with lock:
                    state["bytes"] += len(chunk)
        except (OSError, http.client.HTTPException) as exc:
            with lock:
                state["error"] = str(exc)[:60]
            stop.wait(0.3)
        finally:
            if conn is not None:
                conn.close()


def _upload_stream(base, stop, state, lock):
    parts = urllib.parse.urlsplit(base)
    block = os.urandom(65536)
    total = 4_000_000  # bytes per request; counted as they are sent, not when the request ends
    while not stop.is_set():
        conn = None
        try:
            conn = _http_connection(parts)
            conn.putrequest("POST", "/__up")
            conn.putheader("User-Agent", HTTP_USER_AGENT)
            conn.putheader("Content-Type", "application/octet-stream")
            conn.putheader("Content-Length", str(total))
            conn.endheaders()
            sent = 0
            while sent < total and not stop.is_set():
                n = min(len(block), total - sent)
                conn.send(block[:n])
                sent += n
                with lock:
                    state["bytes"] += n
            if sent >= total:
                resp = conn.getresponse()
                resp.read()
                if resp.status >= 400:
                    raise OSError(f"HTTP {resp.status}")
        except (OSError, http.client.HTTPException) as exc:
            with lock:
                state["error"] = str(exc)[:60]
            stop.wait(0.3)
        finally:
            if conn is not None:
                conn.close()


def _measure_http(worker, base):
    """Runs several parallel streams; throughput is measured after the TCP ramp-up.
    Returns (Mbps, (t_start, t_end)) where the window is in time.monotonic() terms."""
    stop = threading.Event()
    lock = threading.Lock()
    state = {"bytes": 0, "error": None}
    threads = [threading.Thread(target=worker, args=(base, stop, state, lock), daemon=True)
               for _ in range(HTTP_STREAMS)]
    t_begin = time.monotonic()
    try:
        for t in threads:
            t.start()
        stop.wait(HTTP_WARMUP_SEC)
        with lock:
            b0 = state["bytes"]
            if b0 == 0 and state["error"]:  # nothing moved and requests are failing: don't wait it out
                raise RuntimeError(state["error"])
        t0 = time.monotonic()
        stop.wait(HTTP_MEASURE_SEC)
        with lock:
            b1 = state["bytes"]
        t1 = time.monotonic()
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=3)
    if b1 - b0 <= 0:
        raise RuntimeError(state["error"] or "no data transferred")
    return (b1 - b0) * 8 / (t1 - t0) / 1_000_000, (t_begin, t1)


def _speedtest_http(base=HTTP_SPEED_BASE):
    down, down_win = _measure_http(_download_stream, base)
    up, up_win = _measure_http(_upload_stream, base)
    return {"down": round(down, 2), "up": round(up, 2), "ping": None,
            "windows": {"down": down_win, "up": up_win}, "source": "Cloudflare (built-in)"}


def run_speedtest():
    """Returns speed data plus the (monotonic) time windows in which the link was saturated.
    Tries speedtest-cli first, then the built-in HTTP test."""
    result = {"down": None, "up": None, "ping": None, "status": "Failed", "windows": {}, "source": None}
    errors = []
    for name, fn in (("speedtest-cli", _speedtest_cli), ("Cloudflare", _speedtest_http)):
        try:
            data = fn()
        except ImportError:
            errors.append(f"{name} not installed")
        except Exception as exc:
            errors.append(f"{name}: {str(exc)[:50]}")
        else:
            result.update(data, status="Success")
            return result
    result["status"] = "Failed (" + "; ".join(errors) + ")"
    return result
