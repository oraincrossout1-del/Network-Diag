"""
Global Network Diagnostic Suite

Phases
  1. Bandwidth speedtest. Latency is sampled while the line is idle and again during the
     download and the upload separately (bufferbloat). Uses speedtest-cli when installed and
     falls back to a built-in Cloudflare HTTP test, so it works with zero dependencies.
     Also checks DNS: your own resolver vs. public resolvers queried directly.
  2. Route trace          (also used for CG-NAT detection and to grade the first ISP hop)
  3. Stability stress test, run concurrently:
       - local router ping   (1400 B)
       - ISP/internet ping   (1400 B)
       - rapid ping          (32 B, ~10/s)  -> micro-stutter, jitter
       - second-target ping  (32 B)         -> rules out a single bad target
       - TCP connect         (port 443)     -> game/web layer
  Analysis: loss %, longest loss streak, avg/min/max/P99, jitter, outage log, spike log,
  DNS, bufferbloat, blocked-probe / MTU hints. The report is one self-contained HTML file
  (no CDN, no libraries; a small inline script draws the interactive chart), so it renders
  even when the internet is down.

Usage:
  python network_diag.py [--duration 300] [--target 8.8.8.8] [--secondary 1.1.1.1]
                         [--port 443] [--no-speedtest] [--no-open]
                         [--output-dir DIR] [--json]
Optional dependency (recommended for the speedtest):  pip install speedtest-cli
"""
import sys
import traceback

from netdiag.cli import main


def run():
    """Runs main().

    A console .exe that is double-clicked (no arguments) closes its window the instant it
    finishes, so the verdict and any error would vanish before they can be read. In that one
    case the window is kept open until Enter is pressed. Everywhere else (python network_diag.py,
    a terminal, scripts) this is exactly main() and nothing more.
    """
    double_clicked = getattr(sys, "frozen", False) and len(sys.argv) == 1
    if not double_clicked:
        return main()
    try:
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\nPress Enter to close this window...")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    sys.exit(run())
