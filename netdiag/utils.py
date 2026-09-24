"""Small helpers used by several modules (running commands, IP helpers, number/DNS formatting).
Depends only on `config`."""

import ipaddress
import math
import socket
import subprocess

from netdiag.config import CGNAT_NET


def run_cmd(args, timeout):
    """Run a command (no shell). Returns stdout, or '' on failure. On a timeout whatever
    was printed so far is returned (useful for a slow traceroute).
    errors='ignore' matters: localized Windows output can contain bytes that
    the console code page can't decode."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True,
                              errors="ignore", timeout=timeout)
        return proc.stdout or ""
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout
        if isinstance(out, bytes):
            out = out.decode(errors="ignore")
        return out or ""
    except OSError:
        return ""


def is_ipv4(text):
    try:
        ipaddress.IPv4Address(text)
        return True
    except ValueError:
        return False


def resolve_ipv4(host):
    """IPv4 address for a host name (resolved once so DNS time never pollutes the probes)."""
    if is_ipv4(host):
        return host
    try:
        return socket.getaddrinfo(host, None, socket.AF_INET)[0][4][0]
    except OSError:
        return None


def fmt(value, suffix=""):
    return "N/A" if value is None else f"{value}{suffix}"


def percentile(ordered, q):
    """Nearest-rank percentile (q in 0..1) of an already sorted list."""
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, max(0, math.ceil(q * len(ordered)) - 1))]


def in_cgnat(ip):
    try:
        return ipaddress.ip_address(ip) in CGNAT_NET
    except ValueError:
        return False


def format_dns(dns):
    text = fmt(dns["avg"], " ms")
    if dns["failures"]:
        text += f" ({dns['failures']}/{dns['total']} failed)"
    public = ", ".join(f"{r} {d['avg']} ms" for r, d in (dns.get("public") or {}).items()
                       if d and d["avg"] is not None)
    return f"{text} | public: {public}" if public else text
