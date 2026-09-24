"""Default-gateway detection (Windows / macOS / Linux)."""

import re

from netdiag.config import IS_MAC, IS_WIN
from netdiag.utils import is_ipv4, run_cmd


def parse_gateway_windows(route_output):
    """`route -4 print 0.0.0.0` -> default gateway with the lowest metric.
    Language independent (unlike parsing the words 'Default Gateway')."""
    best = None
    for line in route_output.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "0.0.0.0" and parts[1] == "0.0.0.0":
            if not is_ipv4(parts[2]):  # "On-link"
                continue
            try:
                metric = int(parts[4])
            except ValueError:
                continue
            if best is None or metric < best[0]:
                best = (metric, parts[2])
    return best[1] if best else None


def parse_gateway_linux(output):
    for line in output.splitlines():
        parts = line.split()
        if parts and parts[0] == "default" and "via" in parts:
            gw = parts[parts.index("via") + 1]
            if is_ipv4(gw):
                return gw
    return None


def parse_gateway_macos(output):
    m = re.search(r"gateway:\s*(\S+)", output)
    return m.group(1) if m and is_ipv4(m.group(1)) else None


def get_default_gateway():
    """Returns the gateway IP or None if it can't be detected (the local test is
    then skipped rather than pinging a guessed address)."""
    if IS_WIN:
        return parse_gateway_windows(run_cmd(["route", "-4", "print", "0.0.0.0"], 10))
    if IS_MAC:
        return parse_gateway_macos(run_cmd(["route", "-n", "get", "default"], 10))
    return parse_gateway_linux(run_cmd(["ip", "route", "show", "default"], 10))
