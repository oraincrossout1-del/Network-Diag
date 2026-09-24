"""Measurement: everything that talks to the network or the OS.
May depend on: config, utils. Must not import analysis or reporting.

Public API of the package: other packages import from here, never from the files inside."""

from netdiag.probes.gateway import (
    get_default_gateway,
    parse_gateway_linux,
    parse_gateway_macos,
    parse_gateway_windows,
)
from netdiag.probes.latency import (
    PING_RTT_RE,
    build_ping_cmd,
    drop_trailing_loss,
    parse_ping_rtt,
    ping_worker,
    tcp_worker,
)
from netdiag.probes.traceroute import (
    build_trace_cmd,
    detect_cgnat,
    parse_traceroute,
    run_traceroute,
)
from netdiag.probes.ipinfo import fetch_ip, get_ip_info
from netdiag.probes.dns import (
    build_dns_query,
    dns_reply_ok,
    measure_dns_direct,
    measure_dns_system,
    run_dns_tests,
)
from netdiag.probes.bandwidth import run_speedtest

__all__ = [
    "parse_gateway_windows",
    "parse_gateway_linux",
    "parse_gateway_macos",
    "get_default_gateway",
    "PING_RTT_RE",
    "build_ping_cmd",
    "parse_ping_rtt",
    "ping_worker",
    "tcp_worker",
    "drop_trailing_loss",
    "build_trace_cmd",
    "parse_traceroute",
    "run_traceroute",
    "detect_cgnat",
    "fetch_ip",
    "get_ip_info",
    "measure_dns_system",
    "build_dns_query",
    "dns_reply_ok",
    "measure_dns_direct",
    "run_dns_tests",
    "run_speedtest",
]
