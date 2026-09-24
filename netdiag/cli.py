"""Command line interface: argument parsing and the main() workflow."""

import argparse
import concurrent.futures
import os
import platform
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from netdiag.analysis import build_events, calc_stats, collect_findings, summarize
from netdiag.config import (
    IDLE_BASELINE_SEC,
    IS_WIN,
    RAPID_INTERVAL_SEC,
    SECONDARY_HOST,
    TARGET_HOST,
    TCP_PORT,
    TEST_DURATION_SEC,
)
from netdiag.probes import (
    detect_cgnat,
    drop_trailing_loss,
    get_default_gateway,
    get_ip_info,
    ping_worker,
    run_dns_tests,
    run_traceroute,
    tcp_worker,
)
from netdiag.reporting import print_console_summary, print_progress, write_json, write_report
from netdiag.runner import run_bandwidth_phase, safe_result
from netdiag.utils import resolve_ipv4


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Network stability diagnostic")
    p.add_argument("--duration", type=int, default=TEST_DURATION_SEC, help="stress test length in seconds")
    p.add_argument("--target", default=TARGET_HOST, help="primary ping/TCP target (IP or host name)")
    p.add_argument("--secondary", default=SECONDARY_HOST, help="second ping target ('' to disable)")
    p.add_argument("--port", type=int, default=TCP_PORT, help="TCP port for the connect test")
    p.add_argument("--no-speedtest", action="store_true", help="skip the bandwidth/bufferbloat phase")
    p.add_argument("--no-open", action="store_true", help="don't open the report in a browser")
    p.add_argument("--output-dir", default=".", help="where to save the report (default: current folder)")
    p.add_argument("--json", action="store_true", help="also save the results and raw samples as JSON")
    args = p.parse_args(argv)
    args.duration = max(1, args.duration)
    if not 1 <= args.port <= 65535:
        p.error("--port must be between 1 and 65535")
    return args


def label_for(host, ip):
    return host if host == ip else f"{host} ({ip})"


def main(argv=None):
    try:  # never crash on a console that can't print a character
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    args = parse_args(argv)
    duration, port = args.duration, args.port

    if sys.stdout.isatty():
        os.system("cls" if IS_WIN else "clear")
    print("=" * 60)
    print("    GLOBAL NETWORK DIAGNOSTIC SUITE".center(60))
    print("=" * 60)

    # ---- Pre-flight checks -------------------------------------------------
    if not shutil.which("ping"):
        print("\n[!] The 'ping' command was not found. Install it (Linux: 'sudo apt install iputils-ping') "
              "and run again.")
        return 2
    target = resolve_ipv4(args.target)
    if not target:
        print(f"\n[!] Could not resolve '{args.target}' to an IPv4 address (no internet, or a typo?).")
        return 2
    secondary = None
    if args.secondary:
        secondary = resolve_ipv4(args.secondary)
        if not secondary:
            print(f"[!] Could not resolve secondary target '{args.secondary}'; that test is skipped.")
        elif secondary == target:
            print("[!] Secondary target is the same as the primary; that test is skipped.")
            secondary = None
    out_dir = Path(args.output_dir).expanduser().resolve()
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"\n[!] Cannot use output folder {out_dir}: {exc}")
        return 2

    gateway = get_default_gateway()
    print(f"\n[*] Target: {label_for(args.target, target)}"
          + (f" (secondary {label_for(args.secondary, secondary)})" if secondary else ""))
    print(f"[*] Local Gateway: {gateway or 'NOT DETECTED - local router test will be skipped'}")

    try:
        # Phase 1: bandwidth, with latency sampled while idle and while the link is saturated
        if args.no_speedtest:
            speed = {"down": None, "up": None, "ping": None, "status": "Skipped", "windows": {}, "source": None}
            bloat = []
        else:
            print(f"[*] Phase 1: Idle latency, then bandwidth speedtest + latency under load (~{IDLE_BASELINE_SEC + 40} seconds)...")
            speed, bloat = run_bandwidth_phase(target)
            if speed["status"] != "Success":
                print(f"[!] Speedtest failed: {speed['status']}")
            elif speed["source"] != "speedtest-cli":
                print("[*] speedtest-cli unavailable, used the built-in Cloudflare test instead.")
        print("[*] Testing DNS (your resolver vs. public resolvers)...")
        dns = run_dns_tests()

        # Phase 2: route trace (before the stress test so it can't perturb the measurements)
        print("[*] Phase 2: Tracing route...")
        hops = run_traceroute(target)
        if hops is None:
            print("[!] No traceroute/tracepath found (Linux: 'sudo apt install traceroute'); route checks skipped.")
            hops = []
        cgnat = detect_cgnat(hops)
    except KeyboardInterrupt:
        print("\n[!] Cancelled.")
        return 1

    # Phase 3: concurrent stability stress test
    print(f"[*] Phase 3: Starting {duration}-second stability stress test (Ctrl+C = stop early, keep data)...")
    stop = threading.Event()
    interrupted = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = {}
        if gateway:
            futures["local"] = ex.submit(ping_worker, gateway, 1400, 1.0, duration, stop)
        futures["heavy"] = ex.submit(ping_worker, target, 1400, 1.0, duration, stop)
        futures["rapid"] = ex.submit(ping_worker, target, 32, RAPID_INTERVAL_SEC, duration, stop, 500)
        if secondary:
            futures["secondary"] = ex.submit(ping_worker, secondary, 32, 1.0, duration, stop)
        futures["tcp"] = ex.submit(tcp_worker, target, port, 1.0, duration, stop)

        start = time.monotonic()
        try:
            while time.monotonic() - start < duration and not all(f.done() for f in futures.values()):
                print_progress(time.monotonic() - start, duration)
                time.sleep(0.5)
        except KeyboardInterrupt:
            interrupted = True
            print("\n[!] Interrupted - analysing the data collected so far...")
        stop.set()
        elapsed = time.monotonic() - start
    actual = int(min(duration, elapsed))

    print("\n\n[*] Analyzing data and generating final report...")
    raw = {key: safe_result(f, key) for key, f in futures.items()}
    if interrupted:
        raw = {key: drop_trailing_loss(v) for key, v in raw.items()}
    stats = {key: calc_stats(raw.get(key, [])) for key in ("local", "heavy", "rapid", "secondary", "tcp")}
    ip_info = get_ip_info(cgnat)
    findings = collect_findings(stats, speed, cgnat, dns, bloat, hops, gateway)
    verdict = summarize(findings, stats, speed)

    ctx = {"target": label_for(args.target, target),
           "secondary": label_for(args.secondary, secondary) if secondary else "-",
           "port": port, "gateway": gateway, "duration": actual,
           "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           "platform": f"{platform.system()} {platform.release()} | Python {platform.python_version()}",
           "raw": raw, "stats": stats, "hops": hops, "dns": dns, "speed": speed, "bloat": bloat,
           "ip_info": ip_info, "verdict": verdict, "findings": findings,
           "events": build_events(raw, stats)}
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = write_report(ctx, out_dir, stamp, open_browser=not args.no_open)
    print_console_summary(findings, verdict)
    print(f"\n[*] Complete! Report saved to {path}")
    if args.json:
        json_path = out_dir / f"network_diagnostic_{stamp}.json"
        write_json(ctx, json_path)
        print(f"[*] Raw results saved to {json_path}")
    return 0
