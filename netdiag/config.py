"""Settings and constants shared by every module (defaults, thresholds for probing,
platform flags, chart colours). Depends on nothing else in the project."""

import ipaddress
import os
import sys


TARGET_HOST = "8.8.8.8"
SECONDARY_HOST = "1.1.1.1"
TCP_PORT = 443
TEST_DURATION_SEC = 300  # 5 minutes
RAPID_INTERVAL_SEC = 0.1
DNS_DOMAINS = ["google.com", "cloudflare.com", "steampowered.com", "github.com"]
DNS_RESOLVERS = ["1.1.1.1", "8.8.8.8"]  # queried directly (UDP/53) to compare with your own resolver

IDLE_BASELINE_SEC = 6          # idle latency is measured this long before the speedtest starts
LOAD_PROBE_INTERVAL_SEC = 0.3  # latency probe cadence during the speedtest
LOAD_TRIM_SEC = 1.0            # ignore the ramp-up at the start of each download/upload
MIN_LOAD_SAMPLES = 5           # fewer loaded probes than this -> bufferbloat is not reported
MIN_DEAD_PROBES = 5            # 0 replies out of at least this many probes = "blocked", not "lossy"
MIN_LOSS_EVENTS = 2            # a single dropped probe is noise: loss is only graded from this many losses up

HTTP_SPEED_BASE = "https://speed.cloudflare.com"  # zero-dependency fallback speedtest
HTTP_STREAMS = 4
HTTP_WARMUP_SEC = 1.5
HTTP_MEASURE_SEC = 8.0
HTTP_USER_AGENT = "Mozilla/5.0 (compatible; network_diag.py)"

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"
CGNAT_NET = ipaddress.ip_network("100.64.0.0/10")  # RFC 6598

COLOR_BAD, COLOR_MEDIUM, COLOR_GOOD = "#fca5a5", "#fcd34d", "#86efac"


SERIES_DEFS = [  # (key, legend label, color, short name for the event list)
    ("rapid", "Micro-stutter (32B ICMP, primary target)", "#38bdf8", "Internet 32B ping"),
    ("secondary", "Micro-stutter (32B ICMP, secondary target)", "#a78bfa", "Secondary target"),
    ("tcp", "Game layer (TCP connect)", "#fb923c", "TCP connect"),
    ("local", "Local router (1400B ICMP)", "#22c55e", "Local router"),
]
